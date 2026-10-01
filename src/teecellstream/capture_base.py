"""What every screen-capture backend offers LiveStreamer, on any platform.

This lives in its own module for one reason: capture.py imports fcntl and speaks to PipeWire, so it
cannot even be IMPORTED on Windows. The contract itself is platform-neutral, and the Windows backends
need it as much as the Linux ones do - so the contract moved out and the two implementations sit beside
each other, neither importing the other.
"""


class ScreenCapture:
    """The base itself captures nothing."""

    name = "none"
    needs_scale = False        # True when ffmpeg must scale the input itself (x11grab delivers the full desktop)

    def __init__(self):
        self.captured_fps = 0  # frames the source delivered in the last second (statistics only)

    def start(self, width: int, height: int, fps: float) -> bool:
        return False

    @classmethod
    def unavailable_reason(cls) -> str:
        """Empty while this backend could run here; otherwise the one thing that stops it. Asked before a
        backend is picked, so an impossible one never becomes the source of a stream that then fails."""
        return ""

    def ffmpeg_input_args(self) -> list[str]:
        return []

    def feed(self, ffmpeg_stdin) -> None:
        """Blocks until stop(); raw-pipe backends write frames to ffmpeg_stdin here."""

    def stop(self) -> None:
        pass

    def set_display_clock(self, period_s: float, nudge_s: float) -> bool:
        """The console's display lock (protocol.PACE_GAIN): run the frame grid at period_s and move it by nudge_s
        once. True when this backend follows it - only one that paces the pictures itself can. False here:
        ffmpeg paces the others, and LiveStreamer starts their encoder again at the display's rate instead."""
        return False

    def transient_failure(self, ffmpeg_error: str) -> bool:
        """True when a start that produced no frames looks like a source that was merely BUSY, so the same
        attempt is worth repeating. A wrong resolution or a missing device must answer False: retrying
        that only delays the honest error. Windows needs this (see capture_windows); Linux does not."""
        return False
