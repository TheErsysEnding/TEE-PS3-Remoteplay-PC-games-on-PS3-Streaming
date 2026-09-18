"""One import for everything that differs between Linux and Windows.

server.py imports from here and never learns which platform it is on. That is not tidiness: capture.py
imports fcntl and display_mode.py imports PyGObject, so on Windows those modules cannot even be IMPORTED,
let alone called. A try/except around each import in server.py would hide real failures on the platform
where the module is supposed to work; choosing once, here, keeps a missing dependency loud.

Everything NOT listed here is shared: the protocol, the sender, the live streamer, the encoder ladder,
the settings, the log - about 2650 lines that run unchanged on both. The PS3 application is untouched,
because the wire protocol is the same.
"""

import sys

WINDOWS = sys.platform == "win32"

if WINDOWS:
    from . import capture_windows as capture
    from . import display_windows as display_mode
    from . import shell_extension_windows as shell_extension
    from .display_windows import DisplayMode
    from .gamepad_windows import VirtualGamepad
    from .input_windows import DesktopInput
    from .console_windows import install_close_handler
    from .power_windows import keep_display_awake, show_pointer_without_mouse
else:
    from . import capture
    from . import display_mode
    from . import shell_extension
    from .desktop_input import DesktopInput
    from .display_mode import DisplayMode
    from .power import keep_display_awake, show_pointer_without_mouse

    def install_close_handler(on_closing) -> bool:
        """Windows only (see console_windows): closing a console window there raises an event instead of
        sending a signal, and nothing else would run the cleanup. A terminal closing on Linux sends
        SIGHUP, which the server already hooks, so there is nothing to add here."""
        return False
    from .virtual_gamepad import VirtualGamepad

__all__ = ["WINDOWS", "capture", "display_mode", "shell_extension",
           "DesktopInput", "DisplayMode", "VirtualGamepad", "keep_display_awake",
           "install_close_handler",
           "show_pointer_without_mouse"]
