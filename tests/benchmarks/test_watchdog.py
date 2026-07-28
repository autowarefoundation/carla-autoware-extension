"""clock_watchdog: file-polling detection of a frozen sim clock."""

from __future__ import annotations

from pathlib import Path

from benchmarks.scripts import clock_watchdog as cw

S = 1_000_000_000  # ns per second


def _clock_csv(path: Path, arrivals_ns: list[int]) -> Path:
    lines = ["clock_ns,arrival_system_ns"]
    lines += [f"{i * 50_000_000},{a}" for i, a in enumerate(arrivals_ns)]
    path.write_text("\n".join(lines) + "\n")
    return path


class _FakeClock:
    """Monotonic ns source advanced by the injected sleep, so a 60 s watch
    costs no wall time."""

    def __init__(self, start_ns: int):
        self.now = start_ns

    def now_ns(self) -> int:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += int(seconds * S)


def test_newest_arrival_reads_the_last_row(tmp_path):
    path = _clock_csv(tmp_path / "clock.csv", [10 * S, 11 * S, 12 * S])
    assert cw.newest_arrival_ns(path) == 12 * S


def test_newest_arrival_is_none_for_missing_or_header_only(tmp_path):
    assert cw.newest_arrival_ns(tmp_path / "absent.csv") is None
    header_only = tmp_path / "clock.csv"
    header_only.write_text("clock_ns,arrival_system_ns\n")
    assert cw.newest_arrival_ns(header_only) is None


def test_newest_arrival_skips_a_torn_final_row(tmp_path):
    """The observer flushes per row, but a poll can still catch a partial
    write; the previous complete row is the honest answer, not a crash."""
    path = tmp_path / "clock.csv"
    path.write_text("clock_ns,arrival_system_ns\n0,1000\n50000000,")
    assert cw.newest_arrival_ns(path) == 1000


def test_stall_reason_is_silent_during_grace():
    # Nothing has arrived at all, but we are 5 s into a 30 s grace.
    assert cw.stall_reason(None, 5 * S, 0, stall_s=5.0, grace_s=30.0) is None


def test_stall_reason_flags_a_clock_that_never_started():
    detail = cw.stall_reason(None, 31 * S, 0, stall_s=5.0, grace_s=30.0)
    assert detail is not None and "no /clock rows at all" in detail


def test_stall_reason_flags_an_aged_arrival():
    detail = cw.stall_reason(40 * S, 47 * S, 0, stall_s=5.0, grace_s=30.0)
    assert detail is not None and "7.0 s old" in detail


def test_stall_reason_accepts_a_fresh_arrival():
    assert cw.stall_reason(46 * S, 47 * S, 0, stall_s=5.0, grace_s=30.0) is None


def test_watch_marks_a_csv_that_stops_growing(tmp_path):
    """The load-bearing case: rows exist, then stop. The newest arrival ages
    past --stall-s and the run is indictable under exclusion criterion 4."""
    clock = _clock_csv(tmp_path / "clock.csv", [100 * S, 100 * S + 50_000_000])
    marker = tmp_path / "clock_stall.marker"
    clock_source = _FakeClock(100 * S)

    rc = cw.watch(
        clock,
        marker,
        stall_s=5.0,
        grace_s=30.0,
        poll_s=1.0,
        now_ns=clock_source.now_ns,
        sleep=clock_source.sleep,
        max_polls=120,
    )

    assert rc == cw.EXIT_STALLED
    assert marker.exists()
    assert "old" in marker.read_text()


def test_watch_leaves_a_growing_csv_alone(tmp_path):
    """A healthy run: every poll sees a fresh arrival, so no marker is ever
    written and the watchdog only stops when the caller stops it."""
    clock = tmp_path / "clock.csv"
    marker = tmp_path / "clock_stall.marker"
    clock_source = _FakeClock(100 * S)
    _clock_csv(clock, [clock_source.now])

    def growing_sleep(seconds: float) -> None:
        clock_source.sleep(seconds)
        _clock_csv(clock, [clock_source.now])

    rc = cw.watch(
        clock,
        marker,
        stall_s=5.0,
        grace_s=30.0,
        poll_s=1.0,
        now_ns=clock_source.now_ns,
        sleep=growing_sleep,
        max_polls=90,
    )

    assert rc == cw.EXIT_TERMINATED
    assert not marker.exists()


def test_watch_creates_the_marker_directory(tmp_path):
    clock = _clock_csv(tmp_path / "clock.csv", [100 * S])
    marker = tmp_path / "nested" / "run-001" / "clock_stall.marker"
    clock_source = _FakeClock(100 * S)
    rc = cw.watch(
        clock,
        marker,
        stall_s=5.0,
        grace_s=1.0,
        poll_s=1.0,
        now_ns=clock_source.now_ns,
        sleep=clock_source.sleep,
        max_polls=10,
    )
    assert rc == cw.EXIT_STALLED
    assert marker.is_file()


def test_watch_stops_when_the_caller_asks(tmp_path):
    """SIGTERM path: run.sh kills the watchdog at teardown, and that is a
    successful watch, not a stall."""
    clock = _clock_csv(tmp_path / "clock.csv", [100 * S])
    marker = tmp_path / "clock_stall.marker"
    rc = cw.watch(
        clock,
        marker,
        stall_s=5.0,
        grace_s=30.0,
        now_ns=lambda: 100 * S,
        sleep=lambda _s: None,
        should_stop=lambda: True,
    )
    assert rc == cw.EXIT_TERMINATED
    assert not marker.exists()
