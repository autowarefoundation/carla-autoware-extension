"""Unit tests for the pure interop-gate verdict logic.

The subprocess runner is injected, so every check path runs without ROS,
CARLA, or Docker. The dump fixtures mirror `ros2 topic info --verbose`
output shape (Humble)."""

import json
import pathlib

import yaml

import interop_lib

INFO_PUB_AND_SUB = """\
Type: sensor_msgs/msg/PointCloud2

Publisher count: 1

Node name: carla_ros2
Node namespace: /
Topic type: sensor_msgs/msg/PointCloud2
Endpoint type: PUBLISHER
GID: 01.0f.aa.bb
QoS profile:
  Reliability: BEST_EFFORT
  History (Depth): UNKNOWN
  Durability: VOLATILE
  Lifespan: Infinite

Subscription count: 1

Node name: rviz
Node namespace: /
Topic type: sensor_msgs/msg/PointCloud2
Endpoint type: SUBSCRIPTION
GID: 01.0f.cc.dd
QoS profile:
  Reliability: RELIABLE
  Durability: TRANSIENT_LOCAL
"""

INFO_NO_PUBLISHER = """\
Type: std_msgs/msg/String

Publisher count: 0

Subscription count: 1

Endpoint type: SUBSCRIPTION
QoS profile:
  Reliability: RELIABLE
  Durability: VOLATILE
"""

INFO_LATCHED = """\
Type: std_msgs/msg/String

Publisher count: 1

Endpoint type: PUBLISHER
QoS profile:
  Reliability: RELIABLE
  Durability: TRANSIENT_LOCAL
"""


def make_runner(responses):
    """runner(cmd, timeout) that matches `responses` keys as cmd substrings."""

    def runner(cmd, timeout):
        for key, value in responses.items():
            if key in cmd:
                return value
        raise AssertionError(f"unexpected command: {cmd}")

    return runner


def test_parse_publisher_qos_ignores_subscriber_block():
    assert interop_lib.parse_publisher_qos(INFO_PUB_AND_SUB) == ("BEST_EFFORT", "VOLATILE")


def test_parse_publisher_qos_none_without_publisher():
    assert interop_lib.parse_publisher_qos(INFO_NO_PUBLISHER) == (None, None)


def test_presence_fails_on_zero_publishers():
    spec = {"name": "/carla/map", "type": "std_msgs/msg/String"}
    runner = make_runner({"topic info": (0, INFO_NO_PUBLISHER)})
    result = interop_lib.evaluate_topic(spec, runner)
    assert not result["ok"]
    assert result["checks"]["presence"].startswith("FAIL")


def test_presence_fails_on_missing_topic():
    spec = {"name": "/nope", "type": "std_msgs/msg/String"}
    runner = make_runner({"topic info": (1, "Unknown topic '/nope'")})
    result = interop_lib.evaluate_topic(spec, runner)
    assert not result["ok"]
    assert "Unknown topic" in result["checks"]["presence"]


def test_type_mismatch_fails():
    spec = {"name": "/pc", "type": "sensor_msgs/msg/LaserScan"}
    runner = make_runner({"topic info": (0, INFO_PUB_AND_SUB)})
    result = interop_lib.evaluate_topic(spec, runner)
    assert result["checks"]["presence"] == "ok"
    assert "got sensor_msgs/msg/PointCloud2" in result["checks"]["type"]
    assert not result["ok"]


def test_qos_pins_pass_and_fail():
    ok_spec = {
        "name": "/map",
        "type": "std_msgs/msg/String",
        "reliability": "RELIABLE",
        "durability": "TRANSIENT_LOCAL",
    }
    bad_spec = {"name": "/map", "type": "std_msgs/msg/String", "durability": "VOLATILE"}
    runner = make_runner({"topic info": (0, INFO_LATCHED)})
    assert interop_lib.evaluate_topic(ok_spec, runner)["ok"]
    result = interop_lib.evaluate_topic(bad_spec, runner)
    assert not result["ok"]
    assert "offers TRANSIENT_LOCAL" in result["checks"]["durability"]


def test_echo_success_timeout_and_error():
    spec = {"name": "/pc", "type": "sensor_msgs/msg/PointCloud2", "echo": True}
    base = {"topic info": (0, INFO_PUB_AND_SUB)}
    ok = interop_lib.evaluate_topic(spec, make_runner({**base, "topic echo": (0, "data: ...")}))
    assert ok["checks"]["echo"] == "ok" and ok["ok"]
    timed_out = interop_lib.evaluate_topic(spec, make_runner({**base, "topic echo": (124, "")}))
    assert "timeout" in timed_out["checks"]["echo"] and not timed_out["ok"]
    errored = interop_lib.evaluate_topic(
        spec, make_runner({**base, "topic echo": (1, "boom\nlast line")})
    )
    assert "last line" in errored["checks"]["echo"] and not errored["ok"]


def test_min_hz_pass_and_fail():
    spec = {"name": "/pc", "type": "sensor_msgs/msg/PointCloud2", "min_hz": 15.0}
    base = {"topic info": (0, INFO_PUB_AND_SUB)}
    fast = interop_lib.evaluate_topic(
        spec, make_runner({**base, "topic hz": (0, "average rate: 19.998\n")})
    )
    assert fast["checks"]["rate"] == "19.998 Hz" and fast["ok"]
    slow = interop_lib.evaluate_topic(
        spec, make_runner({**base, "topic hz": (0, "average rate: 3.2\n")})
    )
    assert "want >= 15.0" in slow["checks"]["rate"] and not slow["ok"]


def test_render_table_and_summarize():
    results = [
        {"name": "/a", "checks": {"presence": "ok", "type": "ok"}, "ok": True},
        {"name": "/b", "checks": {"presence": "FAIL: gone"}, "ok": False},
    ]
    table = interop_lib.render_table(results)
    assert table.splitlines()[0].startswith("| topic |")
    assert "| /b | FAIL: gone |" in table
    assert interop_lib.summarize(results) == "1/2 topics passed"


def test_expected_topics_contract_schema():
    spec_path = pathlib.Path(__file__).parent.parent / "scripts" / "expected_topics.yaml"
    topics = yaml.safe_load(spec_path.read_text())["topics"]
    assert len(topics) == 8
    for topic in topics:
        assert topic["name"].startswith("/")
        assert "/msg/" in topic["type"]


def test_spike_stack_schema():
    stack_path = pathlib.Path(__file__).parent.parent / "scripts" / "spike_stack.json"
    stack = json.loads(stack_path.read_text())
    assert stack["id"] == "ego"
    sensor_ids = {sensor["id"] for sensor in stack["sensors"]}
    assert sensor_ids == {"lidar_top", "imu", "gnss"}
