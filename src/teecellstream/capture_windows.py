"""Screen capture on Windows: Desktop Duplication first, GDI as the fallback.

Measured on the test machine (Ryzen 7 7840HS / Radeon 780M, Windows 11 26200), 5 second runs at 1080p:

    ddagrab   284 frames   56.8 fps
    gdigrab   161 frames   32.2 fps

and, before an HDMI dummy plug was fitted, with the desktop living on a virtual display driver:

    ddagrab     0 frames    - no output at all
    gdigrab    32 frames    6.4 fps

That second table is the one worth remembering. A headless PC whose desktop sits on an indirect display
driver has no duplicable output: ddagrab gets nothing, and GDI reads the virtual surface so slowly that
the resolution stops mattering - 6.4 fps at 1080p and 6.6 at 720p, because the cost is per FRAME, not per
pixel. Giving the GPU a real output (a dummy plug will do) is what fixes it, and no amount of tuning here
substitutes for that. unavailable_reason() therefore says so rather than letting somebody chase encoders.
"""

import os
import subprocess

from . import log, protocol
from .capture_base import ScreenCapture
from .i18n import _


def _scale_chain(width: int, height: int) -> str:
    """The same scaling and colour conversion the Linux side applies, kept identical on purpose.

    bt709 and limited range are what the PS3's decoder is fed on Linux; a different matrix here would
    make the same stream look different depending on which server sent it.
    """
    return ("scale=%d:%d:flags=lanczos:out_color_matrix=bt709:out_range=tv,format=yuv420p"
            % (width, height))


class DdaCapture(ScreenCapture):
    """ffmpeg's ddagrab filter: the Desktop Duplication API, which is what everything fast on Windows uses.

    Note it is a FILTER, not an input - there is no `-i`. That is why this backend reports
    needs_scale = False and does its own scaling: -filter_complex and -vf cannot both feed one output, so
    the scale has to live inside the same chain rather than being appended by encoders.build_ffmpeg_args.
    """

    name = "ddagrab"
    needs_scale = False        # scales inside its own filter chain, see above

    # What ffmpeg prints when the duplication is not refused but merely not free yet. The desktop having
    # just changed resolution is the ordinary cause (display_windows waits that out), a UAC prompt or the
    # lock screen the other one - all of them pass, none of them a reason to give up on the stream.
    BUSY_MARKERS = ("desktop duplication access denied", "operation not permitted")

    def __init__(self):
        super().__init__()
        self.width = self.height = 0
        self.fps = 0.0

    @classmethod
    def unavailable_reason(cls) -> str:
        if os.name != "nt":
            return _("Desktop Duplication only exists on Windows")
        return ""

    def start(self, width: int, height: int, fps: float) -> bool:
        self.width, self.height, self.fps = width, height, fps
        self.captured_fps = int(fps)   # nominal: ffmpeg pulls at this rate, we never see the frames
        log.write(_("capture: ddagrab on output %d (%g fps, scaled to %dx%d)")
                  % (output_index(), fps, width, height))
        return True

    def ffmpeg_input_args(self) -> list[str]:
        numerator, denominator = protocol.fps_fraction(self.fps)
        chain = ("ddagrab=output_idx=%d:framerate=%d/%d:draw_mouse=1,hwdownload,format=bgra,%s"
                 % (output_index(), numerator, denominator, _scale_chain(self.width, self.height)))
        return ["-init_hw_device", "d3d11va", "-filter_complex", chain]

    def feed(self, ffmpeg_stdin) -> None:
        return   # ffmpeg reads the desktop itself

    def stop(self) -> None:
        self.captured_fps = 0


    def transient_failure(self, ffmpeg_error: str) -> bool:
        text = (ffmpeg_error or "").lower()
        return any(marker in text for marker in self.BUSY_MARKERS)


class GdiCapture(ScreenCapture):
    """GDI's BitBlt via ffmpeg's gdigrab. Half the rate of ddagrab at best, and far worse off a virtual
    display - but it needs no D3D device and works where Desktop Duplication refuses."""

    name = "gdigrab"
    needs_scale = True         # delivers the whole desktop at its own size; encoders.py scales

    def __init__(self):
        super().__init__()
        self.fps = 0.0

    @classmethod
    def unavailable_reason(cls) -> str:
        return "" if os.name == "nt" else _("gdigrab only exists on Windows")

    def start(self, width: int, height: int, fps: float) -> bool:
        self.fps = fps
        self.captured_fps = int(fps)
        log.write(_("capture: gdigrab (%g fps, scaled to %dx%d)") % (fps, width, height))
        return True

    def ffmpeg_input_args(self) -> list[str]:
        return ["-f", "gdigrab", "-framerate", "%d/%d" % protocol.fps_fraction(self.fps),
                "-draw_mouse", "1", "-i", "desktop"]

    def feed(self, ffmpeg_stdin) -> None:
        return

    def stop(self) -> None:
        self.captured_fps = 0


class TestPatternCapture(ScreenCapture):
    """ffmpeg's own test picture instead of the desktop (TEE_CST_TEST_SOURCE=1, as on Linux): for a server
    that runs where there is no desktop to duplicate - an ssh session, a build VM, the integration test.
    -re makes ffmpeg hand the frames out in real time, as a real capture would."""

    name = "testsrc"
    needs_scale = False

    def __init__(self):
        super().__init__()
        self.width = self.height = 0
        self.fps = 0.0

    def start(self, width: int, height: int, fps: float) -> bool:
        self.width, self.height, self.fps = width, height, fps
        self.captured_fps = int(fps)
        log.write(_("capture: test picture (%g fps, %dx%d)") % (fps, width, height))
        return True

    def ffmpeg_input_args(self) -> list[str]:
        numerator, denominator = protocol.fps_fraction(self.fps)
        return ["-re", "-f", "lavfi", "-i",
                "testsrc2=size=%dx%d:rate=%d/%d,format=yuv420p" % (self.width, self.height, numerator, denominator)]

    def stop(self) -> None:
        self.captured_fps = 0


def output_index() -> int:
    """Which Desktop Duplication output to capture.

    DXGI numbers the outputs of an adapter, and on a single-screen PC the desktop is on 0 - which is what
    the default is for. It is a setting rather than a guess because a second screen shifts the numbering,
    and capturing the wrong one is silent: the stream runs, it just shows an empty desktop.
    """
    from .settings import settings
    try:
        return max(0, int(settings.get("capture_output", 0)))
    except (TypeError, ValueError):
        return 0


BACKENDS: dict[str, type] = {"ddagrab": DdaCapture, "gdigrab": GdiCapture}


def create_capture():
    """Desktop Duplication unless TEE_CST_CAPTURE asks for something else."""
    if os.environ.get("TEE_CST_TEST_SOURCE") == "1":
        return TestPatternCapture()
    wanted = os.environ.get("TEE_CST_CAPTURE", "").strip().lower()
    if wanted:
        chosen = BACKENDS.get(wanted)
        if chosen is None:
            log.write(_("capture: TEE_CST_CAPTURE=%s is not a source (%s)") % (wanted, ", ".join(sorted(BACKENDS))))
        else:
            reason = chosen.unavailable_reason()
            if not reason:
                return chosen()
            log.write(_("capture: %s cannot run here (%s) - using the usual source") % (wanted, reason))
    return DdaCapture()


def warm_up() -> None:
    """Nothing to warm up: Windows asks nobody for permission to read its own screen."""
    return
