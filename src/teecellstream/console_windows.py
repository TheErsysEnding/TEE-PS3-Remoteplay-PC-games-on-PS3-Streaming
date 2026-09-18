"""Being told that the console window is closing.

The server puts things back when it ends: the desktop resolution it switched, the MouseKeys setting it
turned on, the ffmpeg it started. All of that hangs off atexit and the SIGTERM/SIGINT handlers - and
NONE of them fire when somebody clicks the X on the console window. Windows does not send a signal
there; it raises CTRL_CLOSE_EVENT against a handler the process must have registered in advance, gives
it a few seconds, and then ends the process whether it answered or not. Python registers a handler for
Ctrl+C and Ctrl+Break only, so without this module closing the window left the desktop at 1280x720 and
the keyboard-mouse switched on - on the one platform where closing the window IS how people quit.
"""

import ctypes
from ctypes import wintypes

from . import log
from .i18n import _

CTRL_C_EVENT = 0
CTRL_BREAK_EVENT = 1
CTRL_CLOSE_EVENT = 2        # the X on the window, or taskkill without /F
CTRL_LOGOFF_EVENT = 5
CTRL_SHUTDOWN_EVENT = 6

# The ones Python does not already handle. Ctrl+C and Ctrl+Break stay with Python's own SIGINT path,
# which the server already hooks - answering them here as well would run the shutdown twice.
CLOSING_EVENTS = (CTRL_CLOSE_EVENT, CTRL_LOGOFF_EVENT, CTRL_SHUTDOWN_EVENT)

_kept: list = []            # every installed callback, kept alive for the life of the process


def is_closing_event(event: int) -> bool:
    """Whether this is a console event that ends the process. Split out so it can be tested anywhere."""
    return event in CLOSING_EVENTS


def make_handler(on_closing):
    """The handler body, without any Windows type around it - again so a test can call it directly."""

    def handler(event):
        if not is_closing_event(event):
            return False    # not ours: let the next handler (Python's own Ctrl+C) have it
        try:
            on_closing()
        except Exception:   # noqa: BLE001 - we have seconds, and there is nobody left to tell
            pass
        return True         # handled; Windows ends the process once we return

    return handler


def install_close_handler(on_closing) -> bool:
    """Run `on_closing` when the console window closes. False if Windows would not take the handler."""
    # WINFUNCTYPE is looked up here rather than at module level: it exists only on Windows, and a module
    # that cannot be IMPORTED elsewhere cannot be checked by the test suite that runs on Linux.
    prototype = getattr(ctypes, "WINFUNCTYPE", None)
    if prototype is None:
        return False
    callback = prototype(wintypes.BOOL, wintypes.DWORD)(make_handler(on_closing))
    try:
        installed = bool(ctypes.windll.kernel32.SetConsoleCtrlHandler(callback, True))
    except (AttributeError, OSError):
        return False
    if installed:
        _kept.append(callback)   # ctypes keeps no reference; a collected callback crashes the process
    else:
        # Worth a line: without it, closing the window leaves the desktop at the streaming resolution,
        # and there would be nothing in the log to explain why.
        log.write(_("console: Windows refused the close handler - closing the window will not put the "
                    "desktop back"))
    return installed
