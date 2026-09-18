"""There is no GNOME Shell on Windows, so there is no extension to enable.

The Linux build ships a small shell extension that stops GNOME from handing a fullscreen window straight
to the display controller, which freezes the ScreenCast stream. Windows has no equivalent problem and no
equivalent knob, so this is a stub with the same names - the server reports the state in its window and
must not have to ask which platform it is on.
"""

UNAVAILABLE = "unavailable"
ENABLED = "enabled"
FAILED = "failed"

# Not "failed": nothing failed. There is simply nothing here that needs enabling.
NOT_NEEDED = "not-needed"


def ensure_enabled() -> str:
    return NOT_NEEDED


def is_enabled() -> bool:
    return True
