"""Starting with Windows: a shortcut in the user's Startup folder.

The Linux twin writes an XDG .desktop file; the Windows equivalent is a .lnk in
%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup. That folder is per-user and needs no
administrator, and Windows runs what is in it in the INTERACTIVE session - which is the whole point
here: a server started in session 0 can see no desktop to capture.

The shortcut is written without any COM library: a .lnk is a documented binary format, but writing one
by hand is a lot of bytes for very little. Instead the entry is a one-line .cmd, which the Startup
folder runs exactly the same way and which anybody can read and delete.
"""

import os
import sys

from . import log
from .i18n import _

ENTRY_NAME = "TEE PS3 Remoteplay.cmd"


def _startup_dir() -> str:
    roaming = os.environ.get("APPDATA")
    if not roaming:
        return ""
    return os.path.join(roaming, "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def path() -> str:
    """Where the autostart entry lives, or "" when Windows will not say where Startup is."""
    folder = _startup_dir()
    return os.path.join(folder, ENTRY_NAME) if folder else ""


def _program() -> str:
    """The command that starts the server again - the .exe itself when frozen, else python -m."""
    if getattr(sys, "frozen", False):
        return '"%s" --minimized' % os.path.abspath(sys.executable)
    return '"%s" -m teecellstream --minimized' % os.path.abspath(sys.executable)


def exec_line() -> str:
    return _program()


def is_enabled() -> bool:
    entry = path()
    return bool(entry) and os.path.isfile(entry)


def set_enabled(wanted: bool) -> bool:
    """Create or remove the entry. Returns what the state IS afterwards, so the switch can follow it."""
    entry = path()
    if not entry:
        log.write(_("autostart: Windows does not say where the Startup folder is"))
        return False
    try:
        if wanted:
            os.makedirs(os.path.dirname(entry), exist_ok=True)
            # start "" ... hands the server off and lets the .cmd end at once, so no console window of
            # the shell itself is left standing behind the server's own
            with open(entry, "w", encoding="utf-8") as handle:
                handle.write("@echo off\r\nstart \"\" %s\r\n" % _program())
            log.write(_("autostart: starts at login (minimised)"))
        else:
            if os.path.isfile(entry):
                os.remove(entry)
            log.write(_("autostart: no longer starts at login"))
    except OSError as error:
        log.write(_("autostart: could not change the setting: %s") % error)
    return is_enabled()
