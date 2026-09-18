"""Mouse and keyboard on Windows: SendInput, where Linux uses uinput.

Two things differ from the Linux side and both matter.

The pointer moves in ABSOLUTE coordinates. SendInput's relative mode goes through the mouse acceleration
curve ("Enhanced pointer precision"), so the same stick deflection would travel a different distance
depending on a setting nobody remembers changing. Reading the cursor, adding our own delta and sending an
absolute position is the only way the pad behaves the same on every PC.

Keys go in as SCANCODES, not virtual keys. The console sends HID usages - key POSITIONS - and Windows maps
a scancode through the active layout exactly as a real keyboard is mapped. Sending virtual-key codes
instead would ask US to decide which character a key produces, which is the mistake the Linux side already
had to undo once: the layout belongs to the PC, not to the sender.
"""

import ctypes
import os
import time
import threading
from ctypes import wintypes

from . import log
from .protocol import PadBits
from .i18n import _

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE, MOUSEEVENTF_ABSOLUTE, MOUSEEVENTF_VIRTUALDESK = 0x0001, 0x8000, 0x4000
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_KEYUP, KEYEVENTF_SCANCODE, KEYEVENTF_EXTENDEDKEY = 0x0002, 0x0008, 0x0001
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79

# The pointer curve, shared with the Linux side rather than copied - see stick.py. Copying it would
# mean the pad feels different on one system the first time anybody tunes the other.
from .stick import (MAX_ELAPSED_S, POINTER_SPEED, SCROLL_SPEED, WHEEL_NOTCH_HI_RES as WHEEL_DELTA,
                    apply_pointer_dead_zone as apply_dead_zone)


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


def _send(*inputs) -> bool:
    array = (_INPUT * len(inputs))(*inputs)
    sent = ctypes.windll.user32.SendInput(len(inputs), array, ctypes.sizeof(_INPUT))
    return sent == len(inputs)


def _mouse(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> _INPUT:
    return _INPUT(type=INPUT_MOUSE,
                  u=_INPUTUNION(mi=_MOUSEINPUT(dx=dx, dy=dy, mouseData=data, dwFlags=flags,
                                               time=0, dwExtraInfo=None)))


def _key(scan: int, up: bool) -> _INPUT:
    flags = KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0)
    if scan & 0xE000 == 0xE000:      # the E0-prefixed half of the set: arrows, right ctrl/alt, keypad /
        flags |= KEYEVENTF_EXTENDEDKEY
    return _INPUT(type=INPUT_KEYBOARD,
                  u=_INPUTUNION(ki=_KEYBDINPUT(wVk=0, wScan=scan & 0xFF, dwFlags=flags,
                                               time=0, dwExtraInfo=None)))


# HID usage -> PS/2 set-1 scancode. Scancodes and not virtual keys, on purpose: Windows runs a scancode
# through the active layout exactly as it does for a real keyboard, so the PC's own layout decides which
# character appears. Sending virtual keys would move that decision to us - the same mistake the console
# side had to undo, where translating on the sender meant two layouts and one of them wrong.
# 0xE0xx marks the extended half of the set (arrows, right ctrl/alt, keypad slash); _key() turns that
# into the EXTENDEDKEY flag.
HID_TO_SCANCODE: dict[int, int] = {}
for _i, _c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    HID_TO_SCANCODE[0x04 + _i] = (0x1E, 0x30, 0x2E, 0x20, 0x12, 0x21, 0x22, 0x23, 0x17, 0x24, 0x25,
                                  0x26, 0x32, 0x31, 0x18, 0x19, 0x10, 0x13, 0x1F, 0x14, 0x16, 0x2F,
                                  0x11, 0x2D, 0x15, 0x2C)[_i]
for _i in range(9):
    HID_TO_SCANCODE[0x1E + _i] = 0x02 + _i          # 1..9
HID_TO_SCANCODE[0x27] = 0x0B                        # 0
for _i in range(10):
    HID_TO_SCANCODE[0x3A + _i] = 0x3B + _i          # F1..F10
HID_TO_SCANCODE.update({
    0x44: 0x57, 0x45: 0x58,                                          # F11 F12
    0x28: 0x1C, 0x29: 0x01, 0x2A: 0x0E, 0x2B: 0x0F, 0x2C: 0x39,      # Enter Esc Back Tab Space
    0x2D: 0x0C, 0x2E: 0x0D, 0x2F: 0x1A, 0x30: 0x1B, 0x31: 0x2B,      # - = [ ] \
    0x32: 0x2B, 0x33: 0x27, 0x34: 0x28, 0x35: 0x29,                  # non-US# ; ' `
    0x36: 0x33, 0x37: 0x34, 0x38: 0x35, 0x39: 0x3A,                  # , . / CapsLock
    0x46: 0xE037, 0x47: 0x46, 0x48: 0x45,                            # PrtSc ScrollLock Pause
    0x49: 0xE052, 0x4A: 0xE047, 0x4B: 0xE049,                        # Insert Home PageUp
    0x4C: 0xE053, 0x4D: 0xE04F, 0x4E: 0xE051,                        # Delete End PageDown
    0x4F: 0xE04D, 0x50: 0xE04B, 0x51: 0xE050, 0x52: 0xE048,          # right left down up
    0x53: 0x45, 0x54: 0xE035, 0x55: 0x37, 0x56: 0x4A, 0x57: 0x4E, 0x58: 0xE01C,
    0x59: 0x4F, 0x5A: 0x50, 0x5B: 0x51, 0x5C: 0x4B, 0x5D: 0x4C,
    0x5E: 0x4D, 0x5F: 0x47, 0x60: 0x48, 0x61: 0x49, 0x62: 0x52, 0x63: 0x53,
    0x64: 0x56,                    # the extra key European boards have and US ones do not
    0x65: 0xE05D,                  # context menu
    0xE0: 0x1D, 0xE1: 0x2A, 0xE2: 0x38, 0xE3: 0xE05B,                # left ctrl shift alt win
    0xE4: 0xE01D, 0xE5: 0x36, 0xE6: 0xE038, 0xE7: 0xE05C,            # right ctrl shift alt win
})
del _i, _c

MODIFIER_SCANCODES = ((1 << 0, 0x1D), (1 << 1, 0x2A), (1 << 2, 0x38), (1 << 3, 0xE05B),
                      (1 << 4, 0xE01D), (1 << 5, 0x36), (1 << 6, 0xE038), (1 << 7, 0xE05C))

# pad button -> what it does as a mouse or a key, same bindings as the Linux side
CLICK_BINDINGS = ((PadBits.CROSS, (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)),
                  (PadBits.CIRCLE, (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)),
                  (PadBits.SQUARE, (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP)))
KEY_BINDINGS = ((PadBits.UP, 0xE048), (PadBits.DOWN, 0xE050), (PadBits.LEFT, 0xE04B),
                (PadBits.RIGHT, 0xE04D), (PadBits.START, 0xE05B))


KEYEVENTF_UNICODE = 0x0004


def _unicode(char: str, up: bool) -> _INPUT:
    flags = KEYEVENTF_UNICODE | (KEYEVENTF_KEYUP if up else 0)
    return _INPUT(type=INPUT_KEYBOARD,
                  u=_INPUTUNION(ki=_KEYBDINPUT(wVk=0, wScan=ord(char), dwFlags=flags,
                                               time=0, dwExtraInfo=None)))


def _absolute(offset: int, size: int) -> int:
    """A pixel offset as the 0..65535 coordinate SendInput wants, aimed at the middle of the pixel."""
    if size <= 1:
        return 0
    return min(65535, (offset * 65536 + 32768) // size)


def _virtual_screen() -> tuple[int, int, int, int]:
    m = ctypes.windll.user32.GetSystemMetrics
    return m(SM_XVIRTUALSCREEN), m(SM_YVIRTUALSCREEN), max(1, m(SM_CXVIRTUALSCREEN)), max(1, m(SM_CYVIRTUALSCREEN))


class DesktopInput:
    """The PS3 pad as a pointer and keyboard on Windows, plus a real USB keyboard on the console.

    Same contract as the Linux DesktopInput so pad_receiver never learns which platform it is on. The
    keyword arguments exist for the same reason: `layout` and `variant` mean nothing here (Windows applies
    its own layout to a scancode), but the caller passes them and should not have to care.
    """

    def __init__(self, *, layout=None, variant=None, clock=None, open_devices=None):
        self._gate = threading.RLock()
        self._clock = clock or time.monotonic
        self._started = self._clock()
        self._last_apply_s = 0.0
        self._closed = False
        self._failed = False
        self._last_buttons = 0
        self._hid_down: set[int] = set()      # scancodes the console's own keyboard is holding
        self._hid_buttons = 0
        self._hid_unknown: set[int] = set()
        self._carry_x = self._carry_y = self._scroll_carry = 0.0
        self._on_windows = (os.name == "nt")
        if not self._on_windows:
            log.write(_("pad: this build drives Windows input, but this is not Windows"))

    # --------------------------------------------------------------------------- what the server asks
    @property
    def is_open(self) -> bool:
        return self._on_windows and not self._closed and not self._failed

    @property
    def device_paths(self) -> tuple:
        """Linux hands back the uinput nodes it created. Windows creates nothing - SendInput posts into
        the input queue directly - so there is no path to report and the window shows the API instead."""
        return ("SendInput", "SendInput") if self.is_open else (None, None)

    def close(self) -> None:
        with self._gate:
            if not self._closed:
                self.release_all()
            self._closed = True

    # ------------------------------------------------------------------------------------ the pad
    def apply(self, buttons: int, left_x: int, left_y: int, right_x: int, right_y: int) -> None:
        with self._gate:
            if not self.is_open:
                return
            now = self._clock() - self._started
            elapsed = max(0.0, min(MAX_ELAPSED_S, now - self._last_apply_s))
            self._last_apply_s = now
            self._move_pointer(left_x, left_y, elapsed)
            self._scroll(right_y, elapsed)

            pressed = buttons & ~self._last_buttons
            released = self._last_buttons & ~buttons
            events = []
            for bit, (down, up) in CLICK_BINDINGS:
                if pressed & (1 << bit):
                    events.append(_mouse(down))
                if released & (1 << bit):
                    events.append(_mouse(up))
            for bit, scan in KEY_BINDINGS:
                if pressed & (1 << bit):
                    events.append(_key(scan, False))
                if released & (1 << bit):
                    events.append(_key(scan, True))
            if events:
                self._emit(*events)
            self._last_buttons = buttons

    def _move_pointer(self, stick_x: int, stick_y: int, elapsed: float) -> None:
        x, y = apply_dead_zone(stick_x), apply_dead_zone(stick_y)
        if x == 0 and y == 0:
            return
        # squared response: small movements stay slow and precise, big ones cross the screen
        self._carry_x += x * abs(x) * POINTER_SPEED * elapsed
        self._carry_y += y * abs(y) * POINTER_SPEED * elapsed
        step_x, step_y = int(self._carry_x), int(self._carry_y)
        self._carry_x -= step_x
        self._carry_y -= step_y
        if step_x or step_y:
            self._move_by(step_x, step_y)

    def _move_by(self, dx: int, dy: int) -> None:
        """Absolute, not relative. Relative motion goes through the pointer acceleration curve, so the
        same stick deflection would travel different distances depending on a Windows setting."""
        point = wintypes.POINT()
        if not ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return
        vx, vy, vw, vh = _virtual_screen()
        target_x = min(vx + vw - 1, max(vx, point.x + dx))
        target_y = min(vy + vh - 1, max(vy, point.y + dy))
        # SendInput's absolute coordinates are 0..65535 across the whole virtual desktop, and Windows
        # turns one back into a pixel with floor(n * width / 65536). Aiming at the MIDDLE of that pixel's
        # band is what lands on the pixel we meant; scaling by 65535/(width-1) aims at the near edge and
        # falls one short on some of them - 10 pixels of 1280, 27 of 1920, 112 of 3840. The rounded form
        # below is exact for every pixel at every width (checked by the test, not by eye).
        nx = _absolute(target_x - vx, vw)
        ny = _absolute(target_y - vy, vh)
        self._emit(_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny))

    def _scroll(self, stick_y: int, elapsed: float) -> None:
        y = apply_dead_zone(stick_y)
        if y == 0:
            return
        self._scroll_carry += -y * SCROLL_SPEED * elapsed   # stick down scrolls down
        notches = int(self._scroll_carry)
        if notches:
            self._scroll_carry -= notches
            self._emit(_mouse(MOUSEEVENTF_WHEEL, data=notches * WHEEL_DELTA))

    # -------------------------------------------------- a real USB keyboard and mouse on the console
    def apply_hid(self, modifiers: int, keys, buttons: int, dx: int, dy: int, wheel: int) -> None:
        with self._gate:
            if not self.is_open:
                return
            wanted = {scan for bit, scan in MODIFIER_SCANCODES if modifiers & bit}
            for usage in keys:
                if usage in (0, 1):
                    continue                      # 0 = no key, 1 = the keyboard's own rollover marker
                scan = HID_TO_SCANCODE.get(usage)
                if scan is None:
                    if usage not in self._hid_unknown:
                        self._hid_unknown.add(usage)
                        log.write(_("pad: unknown key from the console's keyboard (HID 0x%02X)") % usage)
                    continue
                wanted.add(scan)

            events = [_key(s, True) for s in self._hid_down - wanted]
            events += [_key(s, False) for s in wanted - self._hid_down]
            self._hid_down = wanted
            if dx or dy:
                self._move_by(int(dx), int(dy))
            if wheel:
                events.append(_mouse(MOUSEEVENTF_WHEEL, data=int(wheel) * WHEEL_DELTA))
            pressed = buttons & ~self._hid_buttons
            released = self._hid_buttons & ~buttons
            for bit, (down, up) in ((1 << 0, (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)),
                                    (1 << 1, (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)),
                                    (1 << 2, (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP))):
                if pressed & bit:
                    events.append(_mouse(down))
                if released & bit:
                    events.append(_mouse(up))
            self._hid_buttons = buttons
            if events:
                self._emit(*events)

    # ------------------------------------------------------------------------- the on-screen keyboard
    def type_character(self, character: str) -> None:
        """One character from the PS3's on-screen keyboard.

        Injected as UNICODE rather than as a scancode. The console sends a finished character here (not a
        key position), so there is nothing to map through a layout - and KEYEVENTF_UNICODE types it
        whatever the PC's layout is, including characters the layout has no key for.
        """
        with self._gate:
            if not character or not self.is_open:
                return
            character = character[0]
            control = {"\b": 0x0E, "\t": 0x0F, "\n": 0x1C, "\r": 0x1C}.get(character)
            if control is not None:
                self._emit(_key(control, False), _key(control, True))
            else:
                self._emit(_unicode(character, False), _unicode(character, True))

    # ------------------------------------------------------------------------------------ letting go
    def release_all(self) -> None:
        """The stream ended: nothing may stay held down on the PC."""
        with self._gate:
            if not self.is_open:
                self._last_buttons = self._hid_buttons = 0
                self._hid_down = set()
                return
            events = [_key(s, True) for s in self._hid_down]
            self._hid_down = set()
            for bit, (down, up) in CLICK_BINDINGS:
                if self._last_buttons & (1 << bit):
                    events.append(_mouse(up))
            for bit, scan in KEY_BINDINGS:
                if self._last_buttons & (1 << bit):
                    events.append(_key(scan, True))
            for bit, (down, up) in ((1 << 0, (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)),
                                    (1 << 1, (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP)),
                                    (1 << 2, (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP))):
                if self._hid_buttons & bit:
                    events.append(_mouse(up))
            self._last_buttons = self._hid_buttons = 0
            self._carry_x = self._carry_y = self._scroll_carry = 0.0
            if events:
                self._emit(*events)

    def _emit(self, *events) -> None:
        try:
            if not _send(*events) and not self._failed:
                self._failed = True
                log.write(_("pad: SendInput was refused - is something blocking input?"))
        except OSError as error:
            if not self._failed:
                self._failed = True
                log.write(_("pad: input to Windows failed: %s") % error)
