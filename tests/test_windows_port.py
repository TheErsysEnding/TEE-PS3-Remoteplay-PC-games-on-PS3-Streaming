"""The Windows half, checked from Linux.

The one thing that cannot be checked by reading: whether the Windows path IMPORTS. capture.py needs
fcntl, display_mode.py needs PyGObject, virtual_gamepad.py needs evdev - none of which exist on Windows.
A single import of one of those from a Windows module makes the whole server fail to start there, and
nothing on this machine would notice, because here they all import perfectly well.

So the modules are imported with those names blocked, exactly as Windows would have them. That check
already earned its keep: gamepad_windows imported the stick curve from virtual_gamepad, which drags in
fcntl - correct intent (share the curve, do not copy it), wrong module. stick.py exists because of it.

Run: cd <project> && PYTHONPATH=src python3 -m unittest tests.test_windows_port -v
"""

import builtins
import importlib
import os
import pathlib
import sys
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="tee-cst-winport-")
os.environ.setdefault("TEE_CST_SETTINGS_PATH", os.path.join(_TMP, "settings.json"))
os.environ.setdefault("TEE_CST_LOG_PATH", os.path.join(_TMP, "server.log"))

# What a Windows PC does not have. vgamepad is optional even there, so it belongs in the list: the
# server has to start without it and say so, not die.
ABSENT_ON_WINDOWS = ("gi", "fcntl", "evdev", "termios", "vgamepad")

WINDOWS_MODULES = ("teecellstream.plat", "teecellstream.capture_windows", "teecellstream.display_windows",
                   "teecellstream.input_windows", "teecellstream.gamepad_windows",
                   "teecellstream.power_windows", "teecellstream.shell_extension_windows",
                   "teecellstream.netinfo_windows", "teecellstream.power_windows",
                   "teecellstream.console_windows", "teecellstream.autostart_windows",
                   "teecellstream.server", "teecellstream.__main__")


class _AsWindows:
    """Imports run as if this were Windows: sys.platform lies and the absent modules really are absent."""

    def __enter__(self):
        self._platform = sys.platform
        self._import = builtins.__import__
        self._modules = {n: m for n, m in sys.modules.items() if n.startswith("teecellstream")}
        for name in list(self._modules):
            del sys.modules[name]
        sys.platform = "win32"

        def guarded(name, *args, **kwargs):
            if name.split(".")[0] in ABSENT_ON_WINDOWS:
                raise ImportError("not available on Windows: " + name)
            return self._import(name, *args, **kwargs)

        builtins.__import__ = guarded
        return self

    def __exit__(self, *exc):
        builtins.__import__ = self._import
        sys.platform = self._platform
        for name in [n for n in sys.modules if n.startswith("teecellstream")]:
            del sys.modules[name]
        sys.modules.update(self._modules)
        return False


class WindowsImportTests(unittest.TestCase):

    def test_every_windows_module_imports_without_linux_only_packages(self):
        with _AsWindows():
            for name in WINDOWS_MODULES:
                with self.subTest(module=name):
                    importlib.import_module(name)

    def test_plat_picks_the_windows_twins(self):
        with _AsWindows():
            plat = importlib.import_module("teecellstream.plat")
            self.assertTrue(plat.WINDOWS)
            self.assertEqual("teecellstream.capture_windows", plat.capture.__name__)
            self.assertEqual("teecellstream.display_windows", plat.display_mode.__name__)
            self.assertEqual("teecellstream.input_windows", plat.DesktopInput.__module__)
            self.assertEqual("teecellstream.gamepad_windows", plat.VirtualGamepad.__module__)

    def test_plat_picks_the_linux_ones_here(self):
        import teecellstream.plat as plat
        self.assertFalse(plat.WINDOWS)
        self.assertEqual("teecellstream.capture", plat.capture.__name__)
        self.assertEqual("teecellstream.desktop_input", plat.DesktopInput.__module__)


class ContractTests(unittest.TestCase):
    """Each twin has to offer what the Linux original does, or server.py breaks on one platform only."""

    @staticmethod
    def _public(cls):
        return {name for name in dir(cls) if not name.startswith("_")}

    def test_desktop_input_matches(self):
        from teecellstream.desktop_input import DesktopInput as Linux
        from teecellstream.input_windows import DesktopInput as Windows
        missing = self._public(Linux) - self._public(Windows) - {"HID_BUTTONS"}   # internal to the Linux one
        self.assertEqual(set(), missing)

    def test_virtual_gamepad_matches(self):
        from teecellstream.virtual_gamepad import VirtualGamepad as Linux
        from teecellstream.gamepad_windows import VirtualGamepad as Windows
        self.assertEqual(set(), self._public(Linux) - self._public(Windows))

    def test_display_mode_matches(self):
        from teecellstream.display_mode import DisplayMode as Linux
        from teecellstream.display_windows import DisplayMode as Windows
        self.assertEqual(set(), self._public(Linux) - self._public(Windows))

    def test_capture_backends_match(self):
        from teecellstream.capture_base import ScreenCapture
        from teecellstream import capture_windows
        for backend in (capture_windows.DdaCapture, capture_windows.GdiCapture):
            with self.subTest(backend=backend.name):
                self.assertEqual(set(), self._public(ScreenCapture) - self._public(backend))


class SharedNotCopiedTests(unittest.TestCase):
    """The measured numbers must be ONE copy. Two that must agree is one too many - this project has
    paid for that twice already, once with the resolution names and once with their explanations."""

    def test_both_platforms_use_the_same_stick_curve(self):
        from teecellstream import stick, virtual_gamepad, desktop_input, input_windows
        self.assertIs(virtual_gamepad.to_axis, stick.to_axis)
        self.assertIs(desktop_input.apply_dead_zone, stick.apply_pointer_dead_zone)
        self.assertIs(input_windows.apply_dead_zone, stick.apply_pointer_dead_zone)
        self.assertEqual(desktop_input.POINTER_SPEED, input_windows.POINTER_SPEED)

    def test_both_platforms_use_the_same_mode_choosers(self):
        from teecellstream import display_choose, display_mode, display_windows
        self.assertIs(display_mode.choose_sixty_hz_mode, display_choose.choose_sixty_hz_mode)
        self.assertIs(display_windows.choose_sixty_hz_mode, display_choose.choose_sixty_hz_mode)
        self.assertEqual(display_mode.DISPLAY_STRATEGIES, display_windows.DISPLAY_STRATEGIES)

    def test_the_gamepad_and_pointer_curves_stay_different(self):
        """They look alike and are not: 12/115 drives an axis, 16/112 drives a pointer. Merging them
        because they resemble each other would be a quiet regression in whichever one lost."""
        from teecellstream import stick
        self.assertNotEqual((stick.STICK_DEAD_ZONE, stick.STICK_FULL_TILT),
                            (stick.POINTER_DEAD_ZONE, stick.POINTER_FULL_TILT))


class BeaconTargetTests(unittest.TestCase):
    """The beacon has to leave through every adapter, on Windows too. There is no `ip addr` there, so
    the list comes out of GetAdaptersAddresses - and that means hand-written struct layouts, which is
    the kind of code that fails silently: a wrong offset reads a neighbouring field and yields a
    plausible-looking wrong address. The offsets are therefore pinned against Microsoft's documented
    x64 layout, which can be checked from here because the structs use fixed-width types."""

    # offsets of IP_ADAPTER_ADDRESSES_LH / IP_ADAPTER_UNICAST_ADDRESS_LH on 64-bit Windows
    ADAPTER_OFFSETS = {"Length": 0, "IfIndex": 4, "Next": 8, "FirstUnicastAddress": 24,
                       "PhysicalAddressLength": 88, "Mtu": 96, "IfType": 100, "OperStatus": 104}
    UNICAST_OFFSETS = {"Length": 0, "Flags": 4, "Next": 8, "Address": 16, "OnLinkPrefixLength": 56}

    def test_struct_layout_matches_the_documented_windows_one(self):
        import ctypes
        from teecellstream import netinfo_windows
        self.assertEqual(112, ctypes.sizeof(netinfo_windows.IP_ADAPTER_ADDRESSES))
        self.assertEqual(64, ctypes.sizeof(netinfo_windows.IP_ADAPTER_UNICAST_ADDRESS))
        self.assertEqual(16, ctypes.sizeof(netinfo_windows.SOCKADDR_IN))
        for field, offset in self.ADAPTER_OFFSETS.items():
            with self.subTest(field=field):
                self.assertEqual(offset, getattr(netinfo_windows.IP_ADAPTER_ADDRESSES, field).offset)
        for field, offset in self.UNICAST_OFFSETS.items():
            with self.subTest(field=field):
                self.assertEqual(offset, getattr(netinfo_windows.IP_ADAPTER_UNICAST_ADDRESS, field).offset)

    def test_broadcast_from_prefix_length(self):
        from teecellstream import netinfo_windows
        self.assertEqual("192.0.2.255", netinfo_windows.broadcast_for("192.0.2.10", 24))
        self.assertEqual("10.0.255.255", netinfo_windows.broadcast_for("10.0.13.7", 16))
        self.assertEqual("192.0.2.63", netinfo_windows.broadcast_for("192.0.2.50", 26))
        # a /32 is a host route (Windows hands those out for tunnels); it has no broadcast
        self.assertIsNone(netinfo_windows.broadcast_for("198.51.100.7", 32))
        self.assertIsNone(netinfo_windows.broadcast_for("nonsense", 24))

    def test_windows_targets_are_the_global_one_plus_every_adapter(self):
        with _AsWindows():
            from teecellstream import netinfo, netinfo_windows, protocol
            netinfo_windows.interface_broadcasts = lambda: ["192.0.2.255", "192.0.2.255", "10.0.0.255"]
            self.assertEqual([("255.255.255.255", protocol.BEACON_PORT),
                              ("192.0.2.255", protocol.BEACON_PORT),
                              ("10.0.0.255", protocol.BEACON_PORT)],
                             netinfo.get_beacon_targets())

    def test_windows_falls_back_to_the_global_broadcast_when_the_api_refuses(self):
        """It still has to announce itself - the PS3 on the same subnet hears 255.255.255.255."""
        with _AsWindows():
            from teecellstream import netinfo, netinfo_windows, protocol

            def refuse():
                raise OSError("GetAdaptersAddresses returned 1")

            netinfo_windows.interface_broadcasts = refuse
            self.assertEqual([("255.255.255.255", protocol.BEACON_PORT)], netinfo.get_beacon_targets())

    def test_linux_does_not_take_the_windows_path(self):
        from teecellstream import netinfo
        self.assertFalse(netinfo.WINDOWS)


class BusyScreenTests(unittest.TestCase):
    """ddagrab's "access denied" after a resolution change is a source that is busy, not one that is
    broken. Only the Windows backend may say so - the text is quoted from the real failure."""

    REAL_FAILURE = ("[Parsed_ddagrab_0 @ 000001d823361f80] Desktop duplication access denied\n"
                    "[fc#0 @ 000001d824b804c0] Error configuring filter graph: Operation not permitted\n"
                    "[out#0/h264] Nothing was written into output file")

    def test_the_real_failure_counts_as_busy(self):
        with _AsWindows():
            from teecellstream.capture_windows import DdaCapture
            self.assertTrue(DdaCapture().transient_failure(self.REAL_FAILURE))

    def test_an_unrelated_failure_does_not(self):
        with _AsWindows():
            from teecellstream.capture_windows import DdaCapture
            for text in ("Unknown encoder 'h264_nvenc'", "Invalid argument", "", None):
                with self.subTest(text=text):
                    self.assertFalse(DdaCapture().transient_failure(text))

    def test_the_display_switch_waits_for_the_duplication(self):
        """The wait has to outlast what was measured (denied at 0.42 s, fine at 0.86 s) with room to spare."""
        with _AsWindows():
            from teecellstream import display_windows
            self.assertGreaterEqual(display_windows.DUPLICATION_SETTLE_SECONDS, 0.9)


class ConsoleCloseTests(unittest.TestCase):
    """Clicking the X on the console window is how a Windows user quits. Windows raises an event for it
    instead of sending a signal, and Python answers only Ctrl+C and Ctrl+Break - so without a handler of
    our own the desktop stayed at the streaming resolution and the keyboard-mouse setting stayed on."""

    def test_the_closing_events_are_answered_and_the_others_are_not(self):
        from teecellstream import console_windows as console
        for event in (console.CTRL_CLOSE_EVENT, console.CTRL_LOGOFF_EVENT, console.CTRL_SHUTDOWN_EVENT):
            self.assertTrue(console.is_closing_event(event), event)
        # Ctrl+C and Ctrl+Break already reach the server through Python's SIGINT handler. Answering them
        # here as well would run the whole shutdown twice.
        for event in (console.CTRL_C_EVENT, console.CTRL_BREAK_EVENT, 99):
            self.assertFalse(console.is_closing_event(event), event)

    def test_the_handler_cleans_up_and_says_it_handled_it(self):
        from teecellstream import console_windows as console
        ran = []
        handler = console.make_handler(lambda: ran.append(True))
        self.assertTrue(handler(console.CTRL_CLOSE_EVENT))
        self.assertEqual([True], ran)
        self.assertFalse(handler(console.CTRL_C_EVENT))
        self.assertEqual([True], ran, "Ctrl+C must not run the shutdown a second time")

    def test_a_cleanup_that_throws_still_lets_windows_close(self):
        """Windows gives the handler a few seconds and then ends the process either way. An exception
        escaping into the OS callback would be worse than a half-finished cleanup."""
        from teecellstream import console_windows as console

        def explode():
            raise RuntimeError("aufgeraeumt wurde nichts")

        self.assertTrue(console.make_handler(explode)(console.CTRL_CLOSE_EVENT))

    def test_the_server_asks_for_the_handler_when_it_installs_its_exit_hooks(self):
        source = pathlib.Path(__file__).parent.parent / "src" / "teecellstream" / "server.py"
        hooks = source.read_text().split("def install_exit_hooks", 1)[1].split("def ", 1)[0]
        self.assertIn("install_close_handler(self.shutdown)", hooks)



class AbsolutePointerTests(unittest.TestCase):
    """Windows turns an absolute coordinate back into a pixel with floor(n * width / 65536). Every pixel
    the pad can aim at must come back out as that pixel - the pointer is driven by repeated small steps,
    so a coordinate that lands one short does not just look wrong, it can stall the motion entirely."""

    @staticmethod
    def _lands_on(coordinate: int, size: int) -> int:
        return (coordinate * size) // 65536

    def test_every_pixel_of_every_common_width_comes_back_exactly(self):
        with _AsWindows():
            from teecellstream.input_windows import _absolute
            for size in (720, 1080, 1280, 1440, 1920, 2560, 3840, 5120):
                wrong = [pixel for pixel in range(size)
                         if self._lands_on(_absolute(pixel, size), size) != pixel]
                self.assertEqual([], wrong, "%d wrong of %d at width %d" % (len(wrong), size, size))

    def test_the_degenerate_sizes_do_not_divide_by_zero(self):
        with _AsWindows():
            from teecellstream.input_windows import _absolute
            self.assertEqual(0, _absolute(0, 1))
            self.assertEqual(0, _absolute(5, 0))

    def test_it_never_exceeds_what_sendinput_accepts(self):
        with _AsWindows():
            from teecellstream.input_windows import _absolute
            for size in (2, 720, 1920, 3840):
                self.assertLessEqual(_absolute(size - 1, size), 65535)
                self.assertGreaterEqual(_absolute(0, size), 0)



class InvisiblePointerTests(unittest.TestCase):
    """A Windows PC with no mouse plugged in draws no cursor. The pointer still moves - measured on the
    test machine, (0,319) -> (164,319) while the console's picture showed nothing - so the stream looked
    broken when it was working. MouseKeys makes Windows count a pointing device as present again."""

    def _power(self):
        from teecellstream import power_windows
        return power_windows

    def test_it_does_nothing_when_a_real_mouse_is_attached(self):
        """The setting belongs to the user. Touch it only on a PC that would show no cursor at all."""
        with _AsWindows():
            power = self._power()
            written = []
            power.has_mouse = lambda: True
            power._write_mousekeys = lambda flags: written.append(flags)
            power.show_pointer_without_mouse(True)
            self.assertEqual([], written)
            self.assertIsNone(power._mousekeys_before)

    def test_it_turns_mousekeys_on_and_puts_it_back_exactly(self):
        with _AsWindows():
            power = self._power()
            written = []
            before = 0x9000003E          # what the real machine reported
            power.has_mouse = lambda: False
            power._mousekeys = lambda: type("M", (), {"dwFlags": before})()
            power._write_mousekeys = lambda flags: written.append(flags)

            power.show_pointer_without_mouse(True)
            self.assertEqual([before | power.MKF_MOUSEKEYSON | power.MKF_AVAILABLE], written)
            power.show_pointer_without_mouse(False)
            self.assertEqual(before, written[-1], "the PC must get its own setting back, bit for bit")
            self.assertIsNone(power._mousekeys_before)

    def test_the_number_pad_keeps_typing(self):
        """MKF_REPLACENUMBERS is left as the user had it: flipping it would turn the number keys into
        pointer keys, and the console's USB keyboard would stop typing digits."""
        with _AsWindows():
            power = self._power()
            written = []
            power.has_mouse = lambda: False
            power._mousekeys = lambda: type("M", (), {"dwFlags": 0})()
            power._write_mousekeys = lambda flags: written.append(flags)
            power.show_pointer_without_mouse(True)
            self.assertEqual(0, written[0] & 0x00000080)

    def test_a_second_on_changes_nothing_and_off_stays_safe(self):
        """start/stop/start must not save the setting we ourselves made as the one to restore."""
        with _AsWindows():
            power = self._power()
            written = []
            power.has_mouse = lambda: False
            power._mousekeys = lambda: type("M", (), {"dwFlags": 0x20})()
            power._write_mousekeys = lambda flags: written.append(flags)
            power.show_pointer_without_mouse(True)
            power.show_pointer_without_mouse(True)
            self.assertEqual(1, len(written))
            power.show_pointer_without_mouse(False)
            power.show_pointer_without_mouse(False)      # a repeat STOP must not write again
            self.assertEqual([0x20 | 0x3, 0x20], written)

    def test_a_refusing_windows_never_takes_the_stream_down(self):
        with _AsWindows():
            power = self._power()

            def refuse():
                raise OSError("SystemParametersInfo refused")

            power.has_mouse = lambda: False
            power._mousekeys = refuse
            power.show_pointer_without_mouse(True)       # must not raise
            self.assertIsNone(power._mousekeys_before)
            power.show_pointer_without_mouse(False)      # nor must the way back

    def test_linux_has_the_same_call_and_it_does_nothing(self):
        from teecellstream import power
        self.assertIsNone(power.show_pointer_without_mouse(True))
        self.assertIsNone(power.show_pointer_without_mouse(False))


if __name__ == "__main__":
    unittest.main()
