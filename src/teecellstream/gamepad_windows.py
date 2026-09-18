"""The PS3 pad as a virtual Xbox 360 controller on Windows, through ViGEmBus.

Same contract as virtual_gamepad.py, and deliberately the same stick curve: to_axis is imported from
there rather than copied, so the two platforms cannot drift apart the first time either is tuned.

One thing genuinely differs and it is easy to get backwards. evdev's Y axis points DOWN, like the PS3's,
so the Linux side passes it straight through. XInput's points UP. Without the inversion below, every game
on Windows would read the left stick upside down - and it would look like a game bug, not a server one.
"""

import threading

from . import log
from .protocol import PadBits
from .stick import STICK_DEAD_ZONE, STICK_FULL_TILT, to_axis
from .i18n import _

try:
    import vgamepad
except Exception:      # noqa: BLE001 - missing package, missing driver, missing DLL all land here
    vgamepad = None

TRIGGER_MAX = 255      # XInput triggers are a byte, not the 1023 evdev uses


def _buttons_for(module):
    """PS3 bit -> XUSB button, in the same order as virtual_gamepad.BUTTON_MAP."""
    x = module.XUSB_BUTTON
    return (
        (PadBits.CROSS, x.XUSB_GAMEPAD_A), (PadBits.CIRCLE, x.XUSB_GAMEPAD_B),
        (PadBits.SQUARE, x.XUSB_GAMEPAD_X), (PadBits.TRIANGLE, x.XUSB_GAMEPAD_Y),
        (PadBits.L1, x.XUSB_GAMEPAD_LEFT_SHOULDER), (PadBits.R1, x.XUSB_GAMEPAD_RIGHT_SHOULDER),
        (PadBits.SELECT, x.XUSB_GAMEPAD_BACK), (PadBits.START, x.XUSB_GAMEPAD_START),
        (PadBits.L3, x.XUSB_GAMEPAD_LEFT_THUMB), (PadBits.R3, x.XUSB_GAMEPAD_RIGHT_THUMB),
        (PadBits.UP, x.XUSB_GAMEPAD_DPAD_UP), (PadBits.DOWN, x.XUSB_GAMEPAD_DPAD_DOWN),
        (PadBits.LEFT, x.XUSB_GAMEPAD_DPAD_LEFT), (PadBits.RIGHT, x.XUSB_GAMEPAD_DPAD_RIGHT),
    )


class VirtualGamepad:
    """Plug in with try_open(), feed it the PS3's state with send(), unplug with close()."""

    def __init__(self):
        self._gate = threading.RLock()
        self._pad = None
        self._buttons = ()
        self._write_failed = False
        self.path: str | None = None

    @property
    def is_open(self) -> bool:
        return self._pad is not None

    def try_open(self) -> bool:
        """False means no gamepad - the caller falls back to pointer and keyboard."""
        with self._gate:
            if self._pad is not None:
                return True
            if vgamepad is None:
                log.write(_("pad: vgamepad is missing - install it with: pip install vgamepad"))
                return False
            try:
                pad = vgamepad.VX360Gamepad()
            except Exception as error:   # noqa: BLE001 - the driver is the usual reason
                log.write(_("pad: could not create the virtual gamepad (%s) - is ViGEmBus installed?")
                          % error)
                return False
            self._pad = pad
            self._buttons = _buttons_for(vgamepad)
            self._write_failed = False
            self.path = "ViGEmBus"
            log.write(_("pad: virtual Xbox 360 gamepad created (ViGEmBus)"))
            self._send_locked(0, 0, 0, 0, 0)   # a first report at rest, so nothing reads as held
            return True

    def send(self, buttons: int, left_x: int, left_y: int, right_x: int, right_y: int) -> None:
        with self._gate:
            if self._pad is None:
                return
            self._send_locked(buttons, left_x, left_y, right_x, right_y)

    def _send_locked(self, buttons, left_x, left_y, right_x, right_y) -> None:
        try:
            pad = self._pad
            pad.reset()
            for bit, button in self._buttons:
                if buttons & (1 << bit):
                    pad.press_button(button=button)
            pad.left_trigger(value=TRIGGER_MAX if buttons & (1 << PadBits.L2) else 0)
            pad.right_trigger(value=TRIGGER_MAX if buttons & (1 << PadBits.R2) else 0)
            # the inversion the header warns about: XInput counts Y upwards, the PS3 downwards
            pad.left_joystick(x_value=to_axis(left_x), y_value=-to_axis(left_y))
            pad.right_joystick(x_value=to_axis(right_x), y_value=-to_axis(right_y))
            pad.update()
        except Exception as error:   # noqa: BLE001 - never take the stream down over a pad report
            if not self._write_failed:
                self._write_failed = True      # say it once, not 60 times a second
                log.write(_("pad: gamepad report failed: %s") % error)

    def close(self) -> None:
        with self._gate:
            if self._pad is None:
                return
            self._send_locked(0, 0, 0, 0, 0)   # let go of everything before the device vanishes
            try:
                del self._pad
            except Exception:   # noqa: BLE001
                pass
            self._pad = None
            self.path = None
            log.write(_("pad: virtual gamepad removed"))
