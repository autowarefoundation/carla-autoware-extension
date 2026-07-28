// bench_pub: CAL-rmw synthetic PointCloud2 source. Payload layout mirrors
// the natives' 32-byte point step by default; stamp is system now() so
// the CAL analysis (cal_report.py) is a same-host wall-clock difference.
#include <chrono>
#include <string>

#include <rclcpp/rclcpp.hpp>
#include <sensor_msgs/msg/point_cloud2.hpp>

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<rclcpp::Node>("bench_pub");
  const auto topic = node->declare_parameter<std::string>("topic", "/bench/cloud");
  const auto rate_hz = node->declare_parameter<double>("rate_hz", 10.0);
  const auto points = node->declare_parameter<int>("points_per_msg", 28800);
  const auto step = node->declare_parameter<int>("point_step", 32);

  auto qos = rclcpp::QoS(rclcpp::KeepLast(5)).best_effort().durability_volatile();
  auto pub = node->create_publisher<sensor_msgs::msg::PointCloud2>(topic, qos);

  sensor_msgs::msg::PointCloud2 msg;
  msg.header.frame_id = "bench";
  msg.height = 1;
  msg.width = points;
  msg.point_step = step;
  msg.row_step = points * step;
  msg.is_dense = true;
  msg.data.assign(static_cast<size_t>(points) * step, 0u);

  auto timer = node->create_wall_timer(
    std::chrono::duration<double>(1.0 / rate_hz),
    [&]() {
      msg.header.stamp = node->get_clock()->now();
      pub->publish(msg);
    });
  rclcpp::spin(node);
  rclcpp::shutdown();
  return 0;
}
