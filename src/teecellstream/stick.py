"""What the PS3's sticks report, turned into what each target wants.

Shared by both platforms. It lives apart from virtual_gamepad.py and desktop_input.py because those
import fcntl and evdev and cannot be imported on Windows at all - and copying the numbers instead would
mean the pad starts feeling different on one system the first time anybody tunes the other.

There are TWO curves here and they are deliberately not the same. Driving a gamepad axis and driving a
mouse pointer want different dead zones, and the values below were arrived at separately. Merging them
because they look alike would be a quiet regression in whichever one lost.

What does NOT belong here is the Y direction. evdev counts it downwards like the PS3, XInput counts it
upwards; that is a property of the target, not of the stick, and it lives with the target.
"""

# ------------------------------------------------------------------- driving a gamepad axis
AXIS_MAX = 32767              # sticks -32768..32767, like xpad
STICK_DEAD_ZONE = 12          # the PS3's sticks rest a few counts off centre
STICK_FULL_TILT = 115.0


def to_axis(value: int) -> int:
    """The PS3 reads -128..127 and rests a little off centre; the axis wants -32768..32767 centred."""
    tilt = 0.0
    if value >= STICK_DEAD_ZONE:
        tilt = (value - STICK_DEAD_ZONE) / (STICK_FULL_TILT - STICK_DEAD_ZONE)
    elif value <= -STICK_DEAD_ZONE:
        tilt = (value + STICK_DEAD_ZONE) / (STICK_FULL_TILT - STICK_DEAD_ZONE)
    tilt = max(-1.0, min(1.0, tilt))
    return int(tilt * AXIS_MAX)     # truncates toward zero, like the (short) cast in the original


# ------------------------------------------------------------------- driving a mouse pointer
# without a dead zone that drifts the pointer across the screen on its own
POINTER_DEAD_ZONE = 16

# pointer and scroll speeds are per SECOND, not per packet: the pad's send rate can vary, so moving by
# elapsed time keeps the speed steady and the motion smooth however the packets are spaced. the stick
# reads up to ~112 once the dead zone is off it. full tilt crosses the screen in ~1.8s; tune these two.
POINTER_FULL_TILT = 112.0
POINTER_PIXELS_PER_SECOND_AT_FULL_TILT = 880.0
SCROLL_NOTCHES_PER_SECOND_AT_FULL_TILT = 42.0

POINTER_SPEED = POINTER_PIXELS_PER_SECOND_AT_FULL_TILT / (POINTER_FULL_TILT * POINTER_FULL_TILT)
SCROLL_SPEED = SCROLL_NOTCHES_PER_SECOND_AT_FULL_TILT / POINTER_FULL_TILT
WHEEL_NOTCH_HI_RES = 120     # one detent, the unit both REL_WHEEL_HI_RES and Windows count in
MAX_ELAPSED_S = 0.05         # a gap between packets (or the first one) must not lurch the pointer


def apply_pointer_dead_zone(value: int) -> int:
    if -POINTER_DEAD_ZONE <= value <= POINTER_DEAD_ZONE:
        return 0
    return value - POINTER_DEAD_ZONE if value > 0 else value + POINTER_DEAD_ZONE
