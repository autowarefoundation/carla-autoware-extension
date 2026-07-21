"""Pure verdict logic for the CARLA/Autoware native-DDS interop gate.

Everything here is side-effect-free: the subprocess runner is injected
(`runner(cmd, timeout) -> (returncode, combined_output)`), so the rules are
unit-testable without ROS. The CLI wiring lives in interop_check.py."""

import re

# Columns rendered in the results table, in order. "topic" is prepended
# separately; these are the per-check columns.
CHECK_COLUMNS = ["presence", "type", "durability", "reliability", "echo", "rate"]


def _last_line(text):
    lines = text.strip().splitlines()
    return lines[-1] if lines else ""


def parse_publisher_qos(out):
    """Extract (reliability, durability) from the first PUBLISHER endpoint.

    `ros2 topic info --verbose` prints one block per endpoint, each starting
    with an `Endpoint type:` line and containing a `QoS profile:` section with
    `Reliability:` and `Durability:` lines. We only read the QoS lines that
    fall inside a PUBLISHER block, so a subscriber's profile can't be mistaken
    for the publisher's. Values are upper-cased for comparison. Returns
    (None, None) if no publisher block is present."""
    reliability = None
    durability = None
    endpoint_type = None
    for line in out.splitlines():
        stripped = line.strip()
        m = re.match(r"Endpoint type:\s*(\S+)", stripped)
        if m:
            endpoint_type = m.group(1).upper()
            continue
        if endpoint_type == "PUBLISHER":
            mr = re.match(r"Reliability:\s*(\S+)", stripped)
            if mr and reliability is None:
                reliability = mr.group(1).upper()
            md = re.match(r"Durability:\s*(\S+)", stripped)
            if md and durability is None:
                durability = md.group(1).upper()
    return reliability, durability


def evaluate_topic(spec, runner):
    """Check one topic spec, in order: presence (published, with at least one
    publisher), type match, publisher QoS (durability and/or reliability when
    pinned), one successful echo (deserialization proof), and an optional
    minimum rate."""
    name = spec["name"]
    want_type = spec["type"]
    result = {"name": name, "checks": {}, "ok": True}

    def fail(key, msg):
        result["checks"][key] = f"FAIL: {msg}"
        result["ok"] = False

    def ok(key, msg="ok"):
        result["checks"][key] = msg

    rc, out = runner(f"ros2 topic info --verbose {name}", 20)

    # Presence. `ros2 topic info --verbose` can exit 0 even for a topic that is
    # not actually published, so exit code alone is not a presence proof. Two
    # things must hold: the dump has a top-level `Type:` line, and there is at
    # least one publisher. A topic with `Publisher count: 0` is discoverable but
    # not published, which must FAIL presence.
    type_match = re.search(r"^Type:\s*(\S+)", out, re.MULTILINE)
    pub_match = re.search(r"Publisher count:\s*(\d+)", out)
    pub_count = int(pub_match.group(1)) if pub_match else 0
    if rc != 0 or type_match is None:
        fail("presence", _last_line(out) or "topic not found")
        return result
    if pub_count < 1:
        fail("presence", "publisher count 0 (topic not published)")
        return result
    ok("presence")

    # Type.
    got_type = type_match.group(1)
    if got_type == want_type:
        ok("type")
    else:
        fail("type", f"got {got_type} want {want_type}")

    pub_reliability, pub_durability = parse_publisher_qos(out)

    # Durability (only when the spec pins it).
    if "durability" in spec:
        want = spec["durability"].upper()
        if pub_durability == want:
            ok("durability", pub_durability)
        else:
            fail("durability", f"publisher offers {pub_durability or 'none'}, want {want}")

    # Reliability (only when the spec pins it).
    if "reliability" in spec:
        want = spec["reliability"].upper()
        if pub_reliability == want:
            ok("reliability", pub_reliability)
        else:
            fail("reliability", f"publisher offers {pub_reliability or 'none'}, want {want}")

    # Echo: one message deserialized proves the type is wire-compatible.
    if spec.get("echo"):
        rc, out = runner(f"timeout 20 ros2 topic echo --once {name} {want_type}", 25)
        if rc == 0:
            ok("echo")
        elif rc == 124:
            fail("echo", "timeout (no data or deserialization failure)")
        else:
            fail("echo", _last_line(out))

    # Rate: optional minimum publish frequency.
    if "min_hz" in spec:
        rc, out = runner(f"timeout 15 ros2 topic hz --window 50 {name}", 20)
        m = re.search(r"average rate:\s*([\d.]+)", out)
        if m and float(m.group(1)) >= spec["min_hz"]:
            ok("rate", f"{m.group(1)} Hz")
        else:
            got = m.group(1) if m else "none"
            fail("rate", f"got {got}, want >= {spec['min_hz']}")

    return result


def render_table(results):
    header = "| topic | " + " | ".join(CHECK_COLUMNS) + " |"
    separator = "|" + "---|" * (len(CHECK_COLUMNS) + 1)
    lines = [header, separator]
    for r in results:
        cells = [r["checks"].get(k, "-") for k in CHECK_COLUMNS]
        lines.append(f"| {r['name']} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def summarize(results):
    n_bad = sum(not r["ok"] for r in results)
    return f"{len(results) - n_bad}/{len(results)} topics passed"
