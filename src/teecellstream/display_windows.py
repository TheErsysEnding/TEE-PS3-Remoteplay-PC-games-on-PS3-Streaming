"""Switching the desktop mode on Windows: ChangeDisplaySettingsEx, where Linux asks Mutter or xrandr.

Same contract as display_mode.DisplayMode, including the confirmation countdown - a monitor that accepts
a mode and shows nothing is not a Linux problem. The strategies mean the same on both sides and are
imported from nowhere: they are listed here so this module can be imported on a PC without PyGObject.
"""

import ctypes
import threading
import time
from ctypes import wintypes

from . import log
from .i18n import _

# The strategies and the choosers are shared with Linux, on purpose - see display_choose.
from .display_choose import (CONFIRM_SECONDS, DISPLAY_STRATEGIES, REFRESH_TOLERANCE_HZ,
                             SAME_RATE_TOLERANCE_HZ, choose_capture_mode, choose_sixty_hz_mode,
                             choose_size_only_mode)

ENUM_CURRENT_SETTINGS = -1
CDS_UPDATEREGISTRY, CDS_TEST, CDS_FULLSCREEN = 0x01, 0x02, 0x04
DISP_CHANGE_SUCCESSFUL = 0
DM_PELSWIDTH, DM_PELSHEIGHT, DM_DISPLAYFREQUENCY = 0x00080000, 0x00100000, 0x00400000


class DEVMODE(ctypes.Structure):
    _fields_ = [("dmDeviceName", wintypes.WCHAR * 32), ("dmSpecVersion", wintypes.WORD),
                ("dmDriverVersion", wintypes.WORD), ("dmSize", wintypes.WORD),
                ("dmDriverExtra", wintypes.WORD), ("dmFields", wintypes.DWORD),
                ("dmPositionX", wintypes.LONG), ("dmPositionY", wintypes.LONG),
                ("dmDisplayOrientation", wintypes.DWORD), ("dmDisplayFixedOutput", wintypes.DWORD),
                ("dmColor", wintypes.SHORT), ("dmDuplex", wintypes.SHORT),
                ("dmYResolution", wintypes.SHORT), ("dmTTOption", wintypes.SHORT),
                ("dmCollate", wintypes.SHORT), ("dmFormName", wintypes.WCHAR * 32),
                ("dmLogPixels", wintypes.WORD), ("dmBitsPerPel", wintypes.DWORD),
                ("dmPelsWidth", wintypes.DWORD), ("dmPelsHeight", wintypes.DWORD),
                ("dmDisplayFlags", wintypes.DWORD), ("dmDisplayFrequency", wintypes.DWORD),
                ("dmICMMethod", wintypes.DWORD), ("dmICMIntent", wintypes.DWORD),
                ("dmMediaType", wintypes.DWORD), ("dmDitherType", wintypes.DWORD),
                ("dmReserved1", wintypes.DWORD), ("dmReserved2", wintypes.DWORD),
                ("dmPanningWidth", wintypes.DWORD), ("dmPanningHeight", wintypes.DWORD)]


class Mode:
    """One mode a display offers. Same shape as display_mode.Mode so the choosers can be shared."""

    __slots__ = ("id", "width", "height", "refresh", "is_variable_rate")

    def __init__(self, width, height, refresh):
        self.width, self.height, self.refresh = width, height, float(refresh)
        self.id = "%dx%d@%.3f" % (width, height, refresh)
        self.is_variable_rate = False       # Windows does not report VRR modes separately


def _primary_device() -> str | None:
    """The device name Windows uses for the primary display, e.g. \\\\.\\DISPLAY1."""
    try:
        import ctypes.wintypes as wt
        class DISPLAY_DEVICE(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32),
                        ("DeviceString", wintypes.WCHAR * 128), ("StateFlags", wintypes.DWORD),
                        ("DeviceID", wintypes.WCHAR * 128), ("DeviceKey", wintypes.WCHAR * 128)]
        DISPLAY_DEVICE_PRIMARY = 0x00000004
        index, device = 0, DISPLAY_DEVICE()
        device.cb = ctypes.sizeof(DISPLAY_DEVICE)
        while ctypes.windll.user32.EnumDisplayDevicesW(None, index, ctypes.byref(device), 0):
            if device.StateFlags & DISPLAY_DEVICE_PRIMARY:
                return device.DeviceName
            index += 1
            device = DISPLAY_DEVICE()
            device.cb = ctypes.sizeof(DISPLAY_DEVICE)
    except (AttributeError, OSError):
        pass
    return None


def _current(device: str | None) -> DEVMODE | None:
    mode = DEVMODE()
    mode.dmSize = ctypes.sizeof(DEVMODE)
    if ctypes.windll.user32.EnumDisplaySettingsW(device, ENUM_CURRENT_SETTINGS, ctypes.byref(mode)):
        return mode
    return None


def capture_modes(device: str | None = None) -> list:
    """Every mode the primary display offers, as Mode objects the shared choosers understand."""
    if device is None:
        device = _primary_device()
    modes, index, seen = [], 0, set()
    probe = DEVMODE()
    probe.dmSize = ctypes.sizeof(DEVMODE)
    while ctypes.windll.user32.EnumDisplaySettingsW(device, index, ctypes.byref(probe)):
        key = (probe.dmPelsWidth, probe.dmPelsHeight, probe.dmDisplayFrequency)
        if key not in seen and probe.dmBitsPerPel >= 32:
            seen.add(key)
            modes.append(Mode(probe.dmPelsWidth, probe.dmPelsHeight, probe.dmDisplayFrequency))
        index += 1
        probe = DEVMODE()
        probe.dmSize = ctypes.sizeof(DEVMODE)
    return modes


# How long Desktop Duplication refuses to start after the desktop has changed resolution. ddagrab
# then dies with "Desktop duplication access denied" and the stream never produces a frame - which is
# what happened on the first real PS3 connection to the Windows server: the mode switch and the
# capture start were 4 ms apart. Measured on the test machine (Radeon 780M) by switching and then
# probing: denied at 0.31 s and 0.42 s, fine at 0.86 s. The wait is generous on top of that, because
# it costs a fifth of a second once per stream and the alternative is a stream that does not start.
DUPLICATION_SETTLE_SECONDS = 1.2


class DisplayMode:
    """Puts the desktop into the mode a stream wants, and puts it back afterwards.

    Same contract as the Linux DisplayMode, including the confirmation countdown. That countdown is not
    Linux-specific: a monitor can accept a mode and show nothing on either system, and whoever is
    streaming is looking at their television and cannot answer a dialog. It is called off as soon as the
    console proves it is receiving - see server.py.
    """

    def __init__(self, backend=None):
        self._gate = threading.RLock()
        self._changed = False
        self._original: DEVMODE | None = None
        self._original_size = (0, 0)
        self._device: str | None = None
        self._confirm_prompt = None
        self._confirmed = threading.Event()
        self._last_announced = None

    @property
    def is_changed(self) -> bool:
        return self._changed

    @property
    def backend_name(self) -> str:
        return "ChangeDisplaySettingsEx"

    @property
    def is_confirmed(self) -> bool:
        return self._confirmed.is_set()

    def match_for_capture(self, stream_width: int, stream_height: int, fps: float,
                          strategy: str = "capture") -> bool:
        """Put the desktop into the mode that suits this stream - see display_choose for which and why."""
        try:
            modes = capture_modes()
        except Exception as error:      # noqa: BLE001 - a failed enumeration just means "do not switch"
            log.write(_("display: could not read the modes (%s)") % error)
            modes = []
        chooser = {"sixty": choose_sixty_hz_mode, "size": choose_size_only_mode}.get(strategy, choose_capture_mode)
        width, height, refresh = chooser(modes, stream_width, stream_height, fps)
        announce = modes and self._last_announced != (stream_width, stream_height, width, height)
        self._last_announced = (stream_width, stream_height, width, height)
        was_changed = self._changed
        switched = self.match_to(width, height, refresh,
                                 SAME_RATE_TOLERANCE_HZ if modes else REFRESH_TOLERANCE_HZ)
        if announce and switched and not (self._changed and not was_changed):
            log.write(_("display: streaming %dx%d, the desktop is already at %dx%d@%g - nothing to switch")
                      % (stream_width, stream_height, width, height, refresh))
        if switched and self._changed and not was_changed:
            self.arm_confirmation()
        return switched

    def match_to(self, width: int, height: int, refresh_hz: float,
                 rate_tolerance: float = REFRESH_TOLERANCE_HZ) -> bool:
        with self._gate:
            if self._changed:
                return True
            device = _primary_device()
            now = _current(device)
            if now is None:
                log.write(_("display: could not read the current resolution, streaming scaled instead"))
                return False
            same_size = (now.dmPelsWidth, now.dmPelsHeight) == (width, height)
            same_rate = (not now.dmDisplayFrequency
                         or abs(now.dmDisplayFrequency - refresh_hz) <= rate_tolerance)
            if same_size and same_rate:
                return True

            wanted = DEVMODE()
            ctypes.memmove(ctypes.byref(wanted), ctypes.byref(now), ctypes.sizeof(DEVMODE))
            wanted.dmPelsWidth, wanted.dmPelsHeight = width, height
            wanted.dmDisplayFrequency = int(round(refresh_hz))
            wanted.dmFields = DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
            # ask first: CDS_TEST changes nothing and says whether the mode would be accepted
            change = ctypes.windll.user32.ChangeDisplaySettingsExW
            if change(device, ctypes.byref(wanted), None, CDS_TEST, None) != DISP_CHANGE_SUCCESSFUL:
                log.write(_("display: %dx%d@%g was refused, streaming scaled instead")
                          % (width, height, refresh_hz))
                return False
            if change(device, ctypes.byref(wanted), None, CDS_UPDATEREGISTRY, None) != DISP_CHANGE_SUCCESSFUL:
                log.write(_("display: %dx%d@%g was refused, streaming scaled instead")
                          % (width, height, refresh_hz))
                return False
            self._original = now
            self._original_size = (now.dmPelsWidth, now.dmPelsHeight)
            self._device = device
            self._changed = True
            log.write(_("display: desktop switched to %dx%d@%g (was %dx%d@%d)")
                      % (width, height, refresh_hz, now.dmPelsWidth, now.dmPelsHeight, now.dmDisplayFrequency))
            # see the constant: the screen capture cannot start yet. The gate stays held on purpose -
            # a restore arriving mid-switch should queue behind it, not race the driver.
            time.sleep(DUPLICATION_SETTLE_SECONDS)
            return True

    def set_confirm_prompt(self, prompt) -> None:
        self._confirm_prompt = prompt

    def confirm_visible(self) -> None:
        self._confirmed.set()

    def reject_visible(self) -> None:
        self._confirmed.set()
        self.restore()

    def arm_confirmation(self) -> None:
        prompt = self._confirm_prompt
        if prompt is None or not self._changed:
            return
        self._confirmed.clear()

        def wait_then_revert():
            if self._confirmed.wait(CONFIRM_SECONDS):
                return
            log.write(_("display: no confirmation after %d s - switching back to the old resolution")
                      % CONFIRM_SECONDS)
            self.restore()

        threading.Thread(target=wait_then_revert, name="display-confirm", daemon=True).start()
        try:
            prompt(CONFIRM_SECONDS)
        except Exception as error:   # noqa: BLE001 - a dialog that will not open must not cost the mode
            log.write(_("display: could not ask (%s), leaving the resolution as it is") % error)
            self._confirmed.set()

    def restore(self) -> None:
        with self._gate:
            if not self._changed:
                return
            self._confirmed.set()        # a restore for any reason ends the countdown
            self._changed = False        # cleared first: a second call must never fight the first
            width, height = self._original_size
            try:
                change = ctypes.windll.user32.ChangeDisplaySettingsExW
                if self._original is not None:
                    result = change(self._device, ctypes.byref(self._original), None, CDS_UPDATEREGISTRY, None)
                else:
                    result = change(self._device, None, None, 0, None)   # back to the registry default
                if result != DISP_CHANGE_SUCCESSFUL:
                    log.write(_("display: restoring %dx%d failed - please switch back in the display settings")
                              % (width, height))
                    return
            except (AttributeError, OSError) as error:
                log.write(_("display: restoring %dx%d failed (%s)") % (width, height, error))
                return
            log.write(_("display: desktop back at %dx%d") % (width, height))
