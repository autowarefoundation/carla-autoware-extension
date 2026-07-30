// bench_observer: passive per-message recorder for the benchmark harness.
// CSV contracts: benchmarks/README.md. Single-threaded executor, so the
// ofstreams need no locking. All subscriptions are best-effort volatile
// (compatible with both the natives' best-effort and the bridge's
// reliable publishers); depth 1000 so a burst cannot evict unrecorded
// messages (spec M2: reader queues pinned).
#include <algorithm>
#include <chrono>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#include <rclcpp/rclcpp.hpp>
#include <rclcpp/serialized_message.hpp>
#include <rosgraph_msgs/msg/clock.hpp>
#include <geometry_msgs/msg/pose_with_covariance_stamped.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <tf2_msgs/msg/tf_message.hpp>
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

// Parses "<topic>|<type>|<kind>[|<arg>]" into its fields. Throws, naming
// the offending spec, unless topic/type/kind are all present and
// non-empty -- otherwise a spec missing a field (e.g. no "|kind" at all)
// silently yields type="" and falls through to the generic-subscription
// branch, which aborts deep inside create_generic_subscription with an
// opaque rosidl typesupport error instead of a clear message at startup.
//
// `arg` is the OPTIONAL fourth field, empty when the spec has three. Only
// the `tf` kind uses it (the child_frame_id to filter on): /tf carries every
// broadcaster's transforms at once, so a kind that records the topic
// wholesale would report an AGGREGATE rate that can look healthy while the
// one frame pair under test is dead. A present-but-empty fourth field and a
// FIFTH field are both refused rather than ignored: silently dropping the
// tail is how a typo'd filter becomes an unfiltered recording.
void parse_topic_spec(
  const std::string & spec, std::string & topic, std::string & type, std::string & kind,
  std::string & arg)
{
  std::stringstream ss(spec);
  const bool ok =
    static_cast<bool>(std::getline(ss, topic, '|')) &&
    static_cast<bool>(std::getline(ss, type, '|')) &&
    static_cast<bool>(std::getline(ss, kind, '|'));
  arg.clear();
  const bool has_arg = static_cast<bool>(std::getline(ss, arg, '|'));
  std::string extra;
  const bool too_many = static_cast<bool>(std::getline(ss, extra, '|'));
  if (!ok || topic.empty() || type.empty() || kind.empty() || too_many ||
    (has_arg && arg.empty()))
  {
    throw std::runtime_error(
      "bench_observer: malformed topic spec (expected "
      "\"<topic>|<type>|<kind>\" or \"<topic>|<type>|<kind>|<arg>\"): \"" + spec + "\"");
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
    open_or_throw(pose_, out + "/pose.csv");
    pose_ << "topic,header_stamp_ns,x_m,y_m\n";
    open_or_throw(tf_, out + "/tf.csv");
    tf_ << "topic,frame_id,child_frame_id,header_stamp_ns\n";

    // Positions are written at gt.csv's OWN resolution (collect_gt.py writes
    // f"{x:.4f}"), because M5's pose_error differences the two files and a
    // metric may not be quantized by its recorder. std::ostream's default is
    // 6 SIGNIFICANT digits, which is ~1 mm on Town10's +/-150 m coordinates
    // but only ~0.1 m on Nishi-Shinjuku's (routes/NishishinjukuMap.yaml's
    // polyline starts at 81371.133, 49912.721) -- half the 0.2 m no-drift
    // threshold and a third of the 0.3 m spread threshold, on the very cells
    // (C/D) whose map has the large coordinates. Fixed notation keeps the
    // resolution absolute instead of magnitude-dependent.
    odom_ << std::fixed << std::setprecision(4);
    pose_ << std::fixed << std::setprecision(4);

    const auto qos =
      rclcpp::QoS(rclcpp::KeepLast(1000)).best_effort().durability_volatile();

    // clock.csv is FLUSHED PER ROW, and only clock.csv. It is not merely an
    // output file: scripts/clock_watchdog.py polls it once a second as the
    // run's liveness signal, and exclusions.md criterion 4 excludes the run
    // once its newest arrival stamp ages past 5 s. A block-buffered ofstream
    // breaks that contract -- at ~33 bytes per row and 20 Hz the default 8 KiB
    // buffer only reaches the file every ~12 s, so the watchdog sees a file
    // frozen for longer than the threshold on a PERFECTLY HEALTHY run and
    // condemns it under a legitimate-looking pre-registered reason. Measured
    // 2026-07-29 (Task 10): results/E/run-006 was excluded stall:clock while
    // its own clock.csv holds 1280 rows at 19.94 Hz with a largest gap between
    // consecutive arrival stamps of 0.055 s -- no stall existed. Unfixed, this
    // would have excluded every P3 run of every cell that has a sim clock.
    //
    // The cost is one <=33-byte write(2) per /clock message, 20 per second, on
    // the executor thread. The other three streams stay buffered on purpose:
    // none of them is a liveness signal, and observer.csv carries the very
    // arrival stamps M1/M2 are computed from, so a per-row syscall there would
    // land inside the hop being measured.
    clock_sub_ = create_subscription<rosgraph_msgs::msg::Clock>(
      "/clock", qos,
      [this](const rosgraph_msgs::msg::Clock & msg) {
        latest_clock_ns_ = stamp_ns(msg.clock);
        clock_csv_ << latest_clock_ns_ << ',' << now_system_ns() << '\n'
                   << std::flush;
      });

    for (const auto & spec : topics) {
      std::string topic, type, kind, arg;
      parse_topic_spec(spec, topic, type, kind, arg);
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
      } else if (kind == "pose") {
        // The NDT pose (geometry_msgs/PoseWithCovarianceStamped). TYPED, not
        // generic: M5's pose_error is "NDT pose minus CARLA ground truth", and
        // a generic subscription records only stamp+size, so nothing in the
        // campaign carried the NDT x/y at all. It is deliberately a DIFFERENT
        // file from odometry.csv: /localization/kinematic_state is the
        // EKF-fused pose, a different quantity, and scoring pose_error against
        // it would hide NDT error behind IMU/odometry fusion.
        pose_subs_.push_back(
          create_subscription<geometry_msgs::msg::PoseWithCovarianceStamped>(
            topic, qos,
            [this, topic](const geometry_msgs::msg::PoseWithCovarianceStamped & m) {
              const auto s = stamp_ns(m.header.stamp);
              pose_ << topic << ',' << s << ','
                    << m.pose.pose.position.x << ','
                    << m.pose.pose.position.y << '\n';
              row(topic, s, 0);  // size unknown for typed subs: 0 sentinel
            }));
      } else if (kind == "tf") {
        // /tf (tf2_msgs/TFMessage) filtered to ONE child_frame_id, the
        // spec's fourth field. Two reasons this cannot be a `generic` line,
        // both measured rather than argued: (1) stamp_from_cdr reads
        // stamp.sec at CDR byte 4, but TFMessage is a TransformStamped
        // SEQUENCE, so byte 4 holds the sequence LENGTH and byte 8 the first
        // transform's stamp.sec -- rows would carry valid arrival stamps and
        // silently nonsense header stamps; (2) there is no frame filter, so
        // the recorded rate would be the aggregate across every broadcaster,
        // which stays healthy while the one pair under test is dead. Each
        // MATCHING transform emits its own row, so the recorded stamp is the
        // per-transform header stamp and not the message's first one.
        if (arg.empty()) {
          throw std::runtime_error(
            "bench_observer: the `tf` kind needs a child_frame_id as its "
            "fourth field (\"<topic>|tf2_msgs/msg/TFMessage|tf|<child_frame_id>\"): "
            "\"" + spec + "\"");
        }
        // One tf spec per topic. A second one would interleave two frames'
        // rows in observer.csv under the same `topic` key with nothing to
        // separate them, so a rate computed there would silently be the sum
        // of two series -- the aggregate this kind exists to avoid.
        if (std::find(tf_topics_.begin(), tf_topics_.end(), topic) != tf_topics_.end()) {
          throw std::runtime_error(
            "bench_observer: two `tf` specs for topic \"" + topic +
            "\"; observer.csv cannot separate their rows -- register one "
            "child_frame_id per topic");
        }
        tf_topics_.push_back(topic);
        tf_subs_.push_back(create_subscription<tf2_msgs::msg::TFMessage>(
          topic, qos,
          [this, topic, child = arg](const tf2_msgs::msg::TFMessage & m) {
            for (const auto & t : m.transforms) {
              if (t.child_frame_id != child) {continue;}
              const auto s = stamp_ns(t.header.stamp);
              tf_ << topic << ',' << t.header.frame_id << ',' << child << ','
                  << s << '\n';
              row(topic, s, 0);  // size unknown for typed subs: 0 sentinel
            }
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
    pose_.flush(); tf_.flush();
  }

private:
  void row(const std::string & topic, int64_t stamp, size_t size)
  {
    observer_ << topic << ',' << stamp << ',' << now_system_ns() << ','
              << now_steady_ns() << ',' << latest_clock_ns_ << ','
              << size << '\n';
  }

  std::ofstream observer_, clock_csv_, published_, odom_, pose_, tf_;
  int64_t latest_clock_ns_{-1};
  rclcpp::Subscription<rosgraph_msgs::msg::Clock>::SharedPtr clock_sub_;
  std::vector<rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr> odom_subs_;
  std::vector<
    rclcpp::Subscription<geometry_msgs::msg::PoseWithCovarianceStamped>::SharedPtr> pose_subs_;
  std::vector<rclcpp::Subscription<tf2_msgs::msg::TFMessage>::SharedPtr> tf_subs_;
  std::vector<std::string> tf_topics_;
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
