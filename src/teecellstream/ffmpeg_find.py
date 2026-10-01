"""Which ffmpeg the server runs.

On Linux the package brings its own: ffmpeg 8.0.1 with the two patches in ffmpeg-nvenc/ (NVENC without
the deblocking filter, NVENC on whole pixels, MPEG-2 intra refresh), next to the program at
ffmpeg/ffmpeg. It is used when it runs here, and the distribution's ffmpeg on PATH when it does not - it
needs glibc 2.38, which is every system the window runs on anyway, but a fallback costs nothing. Without
the package (a source checkout) PATH is all there is. On Windows it is the classic way for a packaged program to fail: PATH may hold no ffmpeg at all, or it may
hold one that cannot do what the capture needs. On the test machine PATH pointed at a 7.1 "essentials"
build inside the Python folder while a full 8.1 sat in the WinGet package directory - both work, but
nothing said so, and a build without the ddagrab filter would have failed at the first PLAY with an
error that reads like a bug in this program.

So on Windows the candidates are gathered in order of trust and each is ASKED whether it has ddagrab.
The first one that has it wins; if none does, the first that runs at all is used anyway, because
gdigrab still works and a slow picture beats no picture. The answer is worked out once and remembered.
"""

import glob
import os
import shutil
import subprocess
import sys

from . import log
from .i18n import _

WINDOWS = sys.platform == "win32"
PROBE_TIMEOUT_S = 6.0
BUNDLED_LINUX = os.path.join("ffmpeg", "ffmpeg")   # relative to _executable_dir(), see the module doc
WANTED_FILTER = "ddagrab"      # Desktop Duplication; without it Windows capture falls back to gdigrab

_cached: str | None = None


def _executable_dir() -> str:
    """Where the program itself lives - next to a PyInstaller .exe, or the package's parent otherwise."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def bundled_linux() -> str:
    """The ffmpeg the .deb ships, or "" when there is none (a source checkout) or it is not executable."""
    path = os.path.join(_executable_dir(), BUNDLED_LINUX)
    return path if os.path.isfile(path) and os.access(path, os.X_OK) else ""


def runs(path: str) -> bool:
    """Whether this ffmpeg starts at all here - a binary for a newer glibc fails before main()."""
    try:
        done = subprocess.run([path, "-hide_banner", "-version"], capture_output=True, timeout=PROBE_TIMEOUT_S,
                              check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return done.returncode == 0


def windows_candidates() -> list[str]:
    """Every ffmpeg.exe worth trying, most trusted first. Existence is checked, capability is not."""
    found: list[str] = []

    def offer(path: str | None) -> None:
        if path and os.path.isfile(path) and path not in found:
            found.append(path)

    # 1. shipped beside the program: whoever put it there meant it to be used
    beside = _executable_dir()
    offer(os.path.join(beside, "ffmpeg.exe"))
    offer(os.path.join(beside, "ffmpeg", "bin", "ffmpeg.exe"))
    # 2. whatever PATH says
    offer(shutil.which("ffmpeg"))
    # 3. winget's package directory - where `winget install Gyan.FFmpeg` lands, and NOT on PATH
    local = os.environ.get("LOCALAPPDATA")
    if local:
        packages = os.path.join(local, "Microsoft", "WinGet", "Packages")
        for path in sorted(glob.glob(os.path.join(packages, "*FFmpeg*", "**", "bin", "ffmpeg.exe"),
                                     recursive=True), reverse=True):   # newest version name first
            offer(path)
    # 4. the places an installer or a manual unzip puts it
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), "C:\\"):
        if base:
            offer(os.path.join(base, "ffmpeg", "bin", "ffmpeg.exe"))
    return found


def has_wanted_filter(path: str) -> bool:
    """Whether this ffmpeg knows the capture filter Windows needs. False also when it will not run."""
    try:
        done = subprocess.run([path, "-hide_banner", "-loglevel", "quiet", "-filters"],
                              capture_output=True, text=True, timeout=PROBE_TIMEOUT_S, check=False,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return False
    return WANTED_FILTER in (done.stdout or "")


def find(explicit: str = "") -> str:
    """The ffmpeg to run. `explicit` (the setting) wins if it exists; otherwise see the module doc."""
    global _cached
    if explicit:
        chosen = explicit if os.path.isfile(explicit) else (shutil.which(explicit) or "")
        if chosen:
            return chosen
        log.write(_("ffmpeg: the path in the settings does not exist (%s), looking for one instead")
                  % explicit)
    if _cached is not None:
        return _cached
    if not WINDOWS:
        bundled = bundled_linux()
        if bundled:
            if runs(bundled):
                _cached = bundled
                return _cached
            log.write(_("ffmpeg: the bundled build does not run on this system (%s) - using the system's instead")
                      % bundled)
        _cached = shutil.which("ffmpeg") or "ffmpeg"
        return _cached

    candidates = windows_candidates()
    for path in candidates:
        if has_wanted_filter(path):
            _cached = path
            return _cached
    if candidates:
        log.write(_("ffmpeg: none of the %d found can do %s - the screen capture will be the slow one")
                  % (len(candidates), WANTED_FILTER))
        _cached = candidates[0]
        return _cached
    log.write(_("ffmpeg: not found. Install it (winget install Gyan.FFmpeg) or put ffmpeg.exe next to "
                "this program."))
    _cached = "ffmpeg"     # let the encoder probe fail with its own message
    return _cached


def forget() -> None:
    """Only for tests: drop what was worked out, so the next find() looks again."""
    global _cached
    _cached = None
