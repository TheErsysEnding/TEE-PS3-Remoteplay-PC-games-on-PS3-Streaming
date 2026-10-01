"""The display lock: which rate a PACE report may move the stream to, and how each kind of capture follows it.

A portal/pipe capture follows the console's refresh picture by picture. A capture that ffmpeg paces itself
(ddagrab and gdigrab on Windows, x11grab) cannot, so its encoder is started once more at the television's
rate. And a rate chosen to differ from the television's (50 on a 59.94 set) is left alone.
"""

import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from fractions import Fraction

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
_TMP = tempfile.mkdtemp(prefix="tee-cst-displaylock-")
os.environ.setdefault("TEE_CST_SETTINGS_PATH", os.path.join(_TMP, "settings.json"))
os.environ.setdefault("TEE_CST_LOG_PATH", os.path.join(_TMP, "server.log"))

from teecellstream import encoders, log, protocol   # noqa: E402
from teecellstream.capture_base import ScreenCapture   # noqa: E402
from teecellstream.capture_windows import TestPatternCapture   # noqa: E402
from teecellstream.live_streamer import LiveStreamer, _Session   # noqa: E402

FFMPEG = shutil.which("ffmpeg")
NTSC = 1001 / 60000          # the refresh interval of a 59.94 Hz television


class DisplayLockRuleTests(unittest.TestCase):
    def test_sixty_locks_to_the_television(self):
        self.assertEqual((1, Fraction(60000, 1001)), protocol.display_lock(60, NTSC))

    def test_the_consoles_own_clock_snaps_to_the_standard_rate(self):
        # measured on the test console for a 59.94 set: 59.937 Hz on its clock
        self.assertEqual((1, Fraction(60000, 1001)), protocol.display_lock(60, 1 / 59.937))

    def test_thirty_locks_to_every_other_refresh(self):
        self.assertEqual((2, Fraction(30000, 1001)), protocol.display_lock(30, NTSC))

    def test_a_rate_chosen_to_differ_is_left_alone(self):
        for chosen in (50, 55):
            self.assertIsNone(protocol.display_lock(chosen, NTSC), chosen)

    def test_a_fifty_hertz_set(self):
        self.assertEqual((1, Fraction(50)), protocol.display_lock(50, 1 / 50))
        self.assertIsNone(protocol.display_lock(60, 1 / 50))

    def test_fps_fraction_knows_the_ntsc_family(self):
        self.assertEqual((60000, 1001), protocol.fps_fraction(60000 / 1001))
        self.assertEqual((30000, 1001), protocol.fps_fraction(30000 / 1001))
        self.assertEqual((24000, 1001), protocol.fps_fraction(24000 / 1001))
        self.assertEqual((60, 1), protocol.fps_fraction(60))


class _PacingCapture(ScreenCapture):
    """Stands in for the portal pipe: records what the lock asked of it."""

    def __init__(self):
        super().__init__()
        self.clock = []

    def set_display_clock(self, period_s, nudge_s):
        self.clock.append((period_s, nudge_s))
        return True


class PaceRoutingTests(unittest.TestCase):
    def _streamer(self, fps):
        streamer = LiveStreamer(None, "ffmpeg", fps, protocol.KBPS, 1280, 720, protocol.SEND_RATE_KBPS,
                                lambda: None, lambda: [], lambda: "intra", lambda reason: None)
        streamer._pace_reports = 0
        session = _Session(("127.0.0.1", 9), True, 1280, 720)
        return streamer, session

    def test_a_pacing_capture_gets_the_refresh_times_the_pictures_per_refresh(self):
        streamer, session = self._streamer(30)
        session.capture = _PacingCapture()
        streamer._session = session
        streamer.pace(NTSC, 0.001)
        self.assertEqual(1, len(session.capture.clock))
        period, nudge = session.capture.clock[0]
        self.assertAlmostEqual(2 * NTSC, period, places=9)   # 29.97, not 59.94 - the 1.1.0 bug
        self.assertAlmostEqual(protocol.PACE_GAIN * 0.001, nudge)
        self.assertIsNone(session.fps_override)

    def test_a_chosen_fifty_is_not_touched(self):
        streamer, session = self._streamer(50)
        session.capture = _PacingCapture()
        streamer._session = session
        streamer.pace(NTSC, 0.001)
        self.assertEqual([], session.capture.clock)

    def test_a_capture_ffmpeg_paces_is_restarted_once(self):
        streamer, session = self._streamer(60)
        session.capture = ScreenCapture()      # the base: cannot follow the lock itself
        streamer._session = session
        streamer.pace(NTSC, 0.004)
        self.assertTrue(session.restart_for_rate)
        self.assertAlmostEqual(60000 / 1001, session.fps_override)
        session.restart_for_rate = False       # what _run_pump does when it starts the next encoder
        streamer.pace(NTSC, 0.004)
        self.assertFalse(session.restart_for_rate, "one restart per session, never a second")

    def test_no_restart_when_the_rate_already_matches(self):
        streamer, session = self._streamer(60000 / 1001)
        session.capture = ScreenCapture()
        streamer._session = session
        streamer.pace(NTSC, 0.004)
        self.assertFalse(session.restart_for_rate)
        self.assertIsNone(session.fps_override)


class _RecordingTestPattern(TestPatternCapture):
    starts = []

    def start(self, width, height, fps):
        _RecordingTestPattern.starts.append(fps)
        return super().start(width, height, fps)


@unittest.skipUnless(FFMPEG, "ffmpeg wird gebraucht")
class RestartAtTheTelevisionsRateTests(unittest.TestCase):
    """The real thing: an ffmpeg-paced source streaming x264, a PACE report, and the stream carrying on."""

    def test_the_stream_restarts_at_the_new_rate_and_carries_on(self):
        x264 = next((encoder for encoder in encoders.LADDER if encoder.kind == "x264"), None)
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receiver.bind(("127.0.0.1", 0))
        receiver.settimeout(0.2)
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        failures, lines = [], []
        _RecordingTestPattern.starts = []
        saved_write = log.write
        log.write = lambda text: (lines.append(text), saved_write(text))
        streamer = LiveStreamer(sender, FFMPEG, 60, 4000, 640, 360, protocol.SEND_RATE_KBPS,
                                _RecordingTestPattern, lambda: [x264], lambda: "intra", failures.append,
                                stream_size=lambda: (640, 360))
        frames_before = frames_after = 0
        try:
            streamer.start(receiver.getsockname())
            deadline = time.monotonic() + 5
            while frames_before < 30 and time.monotonic() < deadline:
                frames_before += self._count_frames(receiver)
            self.assertGreaterEqual(frames_before, 30, "no stream before the report")
            streamer.pace(NTSC, 0.0)
            deadline = time.monotonic() + 6
            while frames_after < 60 and time.monotonic() < deadline:
                frames_after += self._count_frames(receiver)
        finally:
            streamer.stop()
            log.write = saved_write
            receiver.close()
            sender.close()
        self.assertEqual(2, len(_RecordingTestPattern.starts), _RecordingTestPattern.starts)
        self.assertEqual(60, _RecordingTestPattern.starts[0])
        self.assertAlmostEqual(60000 / 1001, _RecordingTestPattern.starts[1])
        self.assertGreaterEqual(frames_after, 60, "the stream did not carry on after the restart")
        self.assertEqual([], failures)
        self.assertFalse([line for line in lines if "exited by itself" in line], "a restart is not a crash")

    @staticmethod
    def _count_frames(receiver) -> int:
        """Frames whose first fragment arrived (fragment index 0 at bytes 6..7 of a VF packet)."""
        try:
            packet = receiver.recv(2048)
        except socket.timeout:
            return 0
        return 1 if packet[:2] == b"VF" and packet[6:8] == b"\x00\x00" else 0


if __name__ == "__main__":
    unittest.main()
