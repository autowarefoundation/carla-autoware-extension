// bench_observer: passive per-message recorder for the benchmark harness.
// CSV contracts: benchmarks/README.md. Single-threaded executor, so the
// ofstreams need no locking. All subscriptions are best-effort volatile
// (compatible with both the natives' best-effort and the bridge's
// reliable publishers); depth 1000 so a burst cannot evict unrecorded
// messages (spec M2: reader queues pinned).
#include <chrono>
#include <cstring>
#include <fstream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp/serialized_message.hpp>
#include <rosgraph_msgs/msg/clock.hpp>
#include <nav_msgs/msg/odometry.hpp>
// NOTE: on the pinned universe-devel-cuda base, PublishedTime lives in
// autoware_internal_msgs, not autoware_internal_debug_msgs -- verified by
// a live build attempt (autoware_internal_debug_msgs is found but lacks
// the message on that image). See CMakeLists.txt for the same note.
#if defined(BENCH_PT_AUTOWARE_INTERNAL)
#include <autoware_internal_msgs/msg/published_time.hpp>
using PublishedTimeMsg = autoware_internal_msgs::msg::PublishedTime;
#elif defined(BENCH_PT_TIER4)
#include <tier4_debug_msgs/msg/published_time.hpp>
using PublishedTimeMsg = tier4_debug_msgs::msg::PublishedTime;
#endif

using std::chrono::steady_clock;
using std::chrono::system_clock;

namespace
{

int64_t now_system_ns()
{
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
    system_clock::now().time_since_epoch()).count();
}

int64_t now_steady_ns()
{
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
    steady_clock::now().time_since_epoch()).count();
}

// Header stamp of a serialized message whose FIRST field is a
// std_msgs/Header: 4-byte CDR encapsulation, then stamp.sec (int32 LE)
// + stamp.nanosec (uint32 LE). Returns -1 (recorded, excluded from
// latency analysis) on non-LE or short buffers rather than mis-parsing.
int64_t stamp_from_cdr(const rcl_serialized_message_t & m)
{
  if (m.buffer_length < 12) {return -1;}
  const uint8_t * b = m.buffer;
  if (b[1] != 0x01) {return -1;}  // 0x0001 = CDR_LE (XCDR1 plain)
  int32_t sec;
  uint32_t nsec;
  std::memcpy(&sec, b + 4, 4);
  std::memcpy(&nsec, b + 8, 4);
  return static_cast<int64_t>(sec) * 1000000000LL + nsec;
}

int64_t stamp_ns(const builtin_interfaces::msg::Time & t)
{
  return static_cast<int64_t>(t.sec) * 1000000000LL + t.nanosec;
}

// Opens `f` at `path` and throws if the stream isn't usable afterwards
// (bad bind-mount, permissions problem -- both realistic when this runs
// in a container against a host-mounted run directory). Without this
// check, every subsequent `<<` is a silent no-op: the node subscribes
// and spins looking healthy while recording nothing, the worst failure
// shape for the campaign's single instrument. Failing loudly here means
// std::make_shared<BenchObserver>() throws, main() never catches it, and
// the process exits non-zero instead of running blind.
void open_or_throw(std::ofstream & f, const std::string & path)
{
  f.open(path);
  if (!f.is_open() || f.fail()) {
    throw std::runtime_error("bench_observer: cannot open output file: " + path);
  }
}

// Parses "<topic>|<type>|<kind>" into its three fields. Throws, naming
// the offending spec, unless all three are present and non-empty --
// otherwise a spec missing a field (e.g. no "|kind" at all) silently
// yields type="" and falls through to the generic-subscription branch,
// which aborts deep inside create_generic_subscription with an opaque
// rosidl typesupport error instead of a clear message at startup.
void parse_topic_spec(
  const std::string & spec, std::string & topic, std::string & type, std::string & kind)
{
  std::stringstream ss(spec);
  const bool ok =
    static_cast<bool>(std::getline(ss, topic, '|')) &&
    static_cast<bool>(std::getline(ss, type, '|')) &&
    static_cast<bool>(std::getline(ss, kind, '|'));
  if (!ok || topic.empty() || type.empty() || kind.empty()) {
    throw std::runtime_error(
      "bench_observer: malformed topic spec (expected "
      "\"<topic>|<type>|<kind>\"): \"" + spec + "\"");
  }
}

}  // namespace

class BenchObserver : public rclcpp::Node
{
public:
  BenchObserver()
  : Node("bench_observer")
  {
    const auto out = declare_parameter<std::string>("out_dir");
    const auto topics = declare_parameter<std::vector<std::string>>(
      "topics", std::vector<std::string>{});

    open_or_throw(observer_, out + "/observer.csv");
    observer_ << "topic,header_stamp_ns,arrival_system_ns,"
              << "arrival_steady_ns,clock_ns,size_bytes\n";
    open_or_throw(clock_csv_, out + "/clock.csv");
    clock_csv_ << "clock_ns,arrival_system_ns\n";
    open_or_throw(published_, out + "/published_time.csv");
    published_ << "topic,source_header_ns,published_ns\n";
    open_or_throw(odom_, out + "/odometry.csv");
    odom_ << "topic,header_stamp_ns,x_m,y_m\n";

    const auto qos =
      rclcpp::QoS(rclcpp::KeepLast(1000)).best_effort().durability_volatile();

    clock_sub_ = create_subscription<rosgraph_msgs::msg::Clock>(
      "/clock", qos,
      [this](const rosgraph_msgs::msg::Clock & msg) {
        latest_clock_ns_ = stamp_ns(msg.clock);
        clock_csv_ << latest_clock_ns_ << ',' << now_system_ns() << '\n';
      });

    for (const auto & spec : topics) {
      std::string topic, type, kind;
      parse_topic_spec(spec, topic, type, kind);
      if (kind == "odometry") {
        odom_subs_.push_back(create_subscription<nav_msgs::msg::Odometry>(
          topic, qos,
          [this, topic](const nav_msgs::msg::Odometry & m) {
            const auto s = stamp_ns(m.header.stamp);
            odom_ << topic << ',' << s << ','
                  << m.pose.pose.position.x << ','
                  << m.pose.pose.position.y << '\n';
            row(topic, s, 0);  // size unknown for typed subs: 0 sentinel
          }));
#if defined(BENCH_PT_AUTOWARE_INTERNAL) || defined(BENCH_PT_TIER4)
      } else if (kind == "published_time") {
        pt_subs_.push_back(create_subscription<PublishedTimeMsg>(
          topic, qos,
          [this, topic](const PublishedTimeMsg & m) {
            published_ << topic << ',' << stamp_ns(m.header.stamp) << ','
                       << stamp_ns(m.published_stamp) << '\n';
          }));
#endif
      } else {
        generic_subs_.push_back(create_generic_subscription(
          topic, type, qos,
          [this, topic](std::shared_ptr<rclcpp::SerializedMessage> m) {
            row(topic, stamp_from_cdr(m->get_rcl_serialized_message()),
              m->size());
          }));
      }
    }
  }

  ~BenchObserver() override
  {
    observer_.flush(); clock_csv_.flush();
    published_.flush(); odom_.flush();
  }

private:
  void row(const std::string & topic, int64_t stamp, size_t size)
  {
    observer_ << topic << ',' << stamp << ',' << now_system_ns() << ','
              << now_steady_ns() << ',' << latest_clock_ns_ << ','
              << size << '\n';
  }

  std::ofstream observer_, clock_csv_, published_, odom_;
  int64_t latest_clock_ns_{-1};
  rclcpp::Subscription<rosgraph_msgs::msg::Clock>::SharedPtr clock_sub_;
  std::vector<rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr> odom_subs_;
#if defined(BENCH_PT_AUTOWARE_INTERNAL) || defined(BENCH_PT_TIER4)
  std::vector<rclcpp::Subscription<PublishedTimeMsg>::SharedPtr> pt_subs_;
#endif
  std::vector<rclcpp::GenericSubscription::SharedPtr> generic_subs_;
};

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  rclcpp::spin(std::make_shared<BenchObserver>());
  rclcpp::shutdown();
  return 0;
}
