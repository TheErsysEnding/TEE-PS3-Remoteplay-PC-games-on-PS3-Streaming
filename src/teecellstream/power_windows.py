"""Keeping the screen awake on Windows - and the mouse pointer drawable at all.

The Linux side asks the session manager over DBus for an inhibitor. Windows has a much smaller API for
the same thing: a per-thread flag saying "I am busy, do not blank the display". It has to be re-asserted
from the SAME thread that set it, which is why the state is held here rather than being a fire-and-forget.
"""

import atexit
import ctypes
import threading
from ctypes import wintypes

from . import log
from .i18n import _

ES_CONTINUOUS       = 0x80000000
ES_SYSTEM_REQUIRED  = 0x00000001
ES_DISPLAY_REQUIRED = 0x00000002

_gate = threading.Lock()
_awake = False


def keep_display_awake(on: bool) -> None:
    """While a stream runs the desktop must not blank - the console would be streaming a black screen."""
    global _awake
    with _gate:
        if on == _awake:
            return
        flags = ES_CONTINUOUS | (ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED if on else 0)
        try:
            if ctypes.windll.kernel32.SetThreadExecutionState(ctypes.c_uint(flags)) == 0:
                log.write(_("power: Windows refused the display-awake request"))
                return
        except (AttributeError, OSError) as error:   # noqa: BLE001 - never take the stream down for this
            log.write(_("power: cannot keep the display awake (%s)") % error)
            return
        _awake = on


# --------------------------------------------------------------------- the pointer nobody can see
#
# A PC with no mouse plugged in DRAWS no cursor. Windows reports GetSystemMetrics(SM_MOUSEPRESENT) = 0
# and GetCursorInfo() returns flags = 0, and the Desktop Duplication API then tells ffmpeg the pointer
# is invisible - so ddagrab's draw_mouse has nothing to draw. The pointer still MOVES, and clicks still
# land; it is simply not in the picture, which on a console at the other end of the room is the same as
# not working. Measured on the test machine: the pad moved the pointer from (0,319) to (164,319) while
# the screen showed nothing at all.
#
# Turning MouseKeys on is what fixes it: Windows then counts a pointing device as present
# (SM_MOUSEPRESENT flips to 1) and draws the cursor again. It is a system-wide accessibility setting, so
# it is only touched on a machine that has no mouse anyway, it is written with fWinIni = 0 (this session
# only, nothing lands in the user's profile), and it is put back the moment the stream ends.
#
# The alternative - AttachThreadInput to the foreground window and ShowCursor(TRUE) - also works and was
# measured working, but it has to STAY attached to keep the cursor up, and a merged input queue means a
# stall in this process becomes a stall in whatever the user is using. Not worth a cursor.

SM_MOUSEPRESENT = 19
SPI_GETMOUSEKEYS, SPI_SETMOUSEKEYS = 0x0036, 0x0037
MKF_MOUSEKEYSON, MKF_AVAILABLE = 0x00000001, 0x00000002


class MOUSEKEYS(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwFlags", wintypes.DWORD),
                ("iMaxSpeed", wintypes.DWORD), ("iTimeToMaxSpeed", wintypes.DWORD),
                ("iCtrlSpeed", wintypes.DWORD), ("dwReserved1", wintypes.DWORD),
                ("dwReserved2", wintypes.DWORD)]


_pointer_gate = threading.Lock()
_mousekeys_before: int | None = None    # what the setting was before we touched it; None = untouched


def _mousekeys() -> MOUSEKEYS:
    settings = MOUSEKEYS()
    settings.cbSize = ctypes.sizeof(MOUSEKEYS)
    if not ctypes.windll.user32.SystemParametersInfoW(SPI_GETMOUSEKEYS, settings.cbSize,
                                                      ctypes.byref(settings), 0):
        raise OSError("SystemParametersInfo(SPI_GETMOUSEKEYS) refused")
    return settings


def _write_mousekeys(flags: int) -> None:
    settings = _mousekeys()
    settings.dwFlags = flags
    # fWinIni = 0: change it for this session, write nothing to the user's profile
    if not ctypes.windll.user32.SystemParametersInfoW(SPI_SETMOUSEKEYS, settings.cbSize,
                                                      ctypes.byref(settings), 0):
        raise OSError("SystemParametersInfo(SPI_SETMOUSEKEYS) refused")


def has_mouse() -> bool:
    """Whether Windows thinks a pointing device is attached. False means the cursor is not drawn."""
    try:
        return bool(ctypes.windll.user32.GetSystemMetrics(SM_MOUSEPRESENT))
    except (AttributeError, OSError):
        return True     # cannot ask: assume the normal case and change nothing


def show_pointer_without_mouse(on: bool) -> None:
    """Make the cursor visible on a PC with no mouse, and put the setting back afterwards."""
    global _mousekeys_before
    with _pointer_gate:
        try:
            if on:
                if _mousekeys_before is not None or has_mouse():
                    return          # already done, or there is a real mouse and nothing to fix
                before = _mousekeys().dwFlags
                # MKF_REPLACENUMBERS is deliberately left as the user had it: with it off, the number pad
                # still types digits while NumLock is on, and only moves the pointer while it is off
                _write_mousekeys(before | MKF_MOUSEKEYSON | MKF_AVAILABLE)
                _mousekeys_before = before
                log.write(_("pointer: no mouse on this PC - the cursor would be invisible, so the "
                            "keyboard-mouse setting is on while streaming"))
            else:
                if _mousekeys_before is None:
                    return
                before, _mousekeys_before = _mousekeys_before, None
                _write_mousekeys(before)
        except (AttributeError, OSError, ValueError) as error:   # never take the stream down for a cursor
            log.write(_("pointer: could not change the cursor setting (%s)") % error)
            if on:
                _mousekeys_before = None


atexit.register(lambda: show_pointer_without_mouse(False))
