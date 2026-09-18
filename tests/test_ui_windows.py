"""The Qt window, driven for real - offscreen, with no screen and no Windows.

This file exists because of one bug. The Start/Stop button kept saying "Stop" however often it was
pressed: the handler called trip_fuse(None), trip_fuse appends a sentence to the reason it is given,
None + str raised inside the click handler, the server stayed armed, and the label never changed.
Nothing in the suite could see that - there was no test that pressed a button. There is now.

Qt runs headless here (QT_QPA_PLATFORM=offscreen), so these are real widgets: the window is built, the
button is clicked, the dropdowns are changed, and what the server received is checked. Where PySide6 is
not installed the whole file skips rather than fails - it is not part of the Linux program.

Run: cd <project> && PYTHONPATH=src python3 -m unittest tests.test_ui_windows -v
"""

import os
import sys
import tempfile
import unittest

_TMP = tempfile.mkdtemp(prefix="tee-cst-qt-")
os.environ.setdefault("TEE_CST_SETTINGS_PATH", os.path.join(_TMP, "settings.json"))
os.environ.setdefault("TEE_CST_LOG_PATH", os.path.join(_TMP, "server.log"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from PySide6.QtWidgets import QApplication
except ImportError:                                   # noqa: F401 - the message is the point
    raise unittest.SkipTest("PySide6 is not installed here - the Qt window is the Windows half")

from teecellstream import protocol                     # noqa: E402
from teecellstream.display_choose import DISPLAY_STRATEGIES   # noqa: E402
from teecellstream.i18n import set_language            # noqa: E402
from teecellstream.ui_text import (BITRATE_HINT, DISPLAY_HINTS, ENTROPY_HINTS, FPS_HINT,
                                   LOSS_RECOVERY_HINTS, LOSS_RECOVERY_KINDS, SLICE_HINTS,
                                   bitrate_labels, fps_labels, size_hints, size_labels)  # noqa: E402
from test_gui import FakeEncoder, MockServer           # noqa: E402


class FakeDisplayMode:
    """What the window asks of server.display_mode, and nothing more."""

    def __init__(self):
        self.is_changed = False
        self.is_confirmed = True
        self.prompt = None
        self.confirmed = 0
        self.rejected = 0

    def set_confirm_prompt(self, prompt):
        self.prompt = prompt

    def confirm_visible(self):
        self.confirmed += 1

    def reject_visible(self):
        self.rejected += 1


class QtServer(MockServer):
    """The GUI mock plus the two things only the Qt window reaches for."""

    def __init__(self):
        super().__init__()
        self.display_mode = FakeDisplayMode()
        self.live_streamer = None
        self.stop_calls = []

    def stop_streaming(self, why, user_stop=False):
        self.stop_calls.append((why, user_stop))


class WindowTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        set_language("en")
        from teecellstream.ui_windows import MainWindow
        self.server = QtServer()
        self.window = MainWindow(self.server)

    def tearDown(self):
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()

    # ------------------------------------------------------------------ the button that started this
    def test_the_button_really_alternates(self):
        """THE regression. Pressing it must disarm the server and the label must follow - both ways."""
        self.assertTrue(self.server.is_armed)
        self.assertEqual("Stop", self.window._arm_button.text())

        self.window._arm_button.click()
        self.assertFalse(self.server.is_armed, "the server is still armed after Stop")
        self.assertEqual(["stopped by you"], self.server.disarm_reasons)
        self.assertEqual("Start", self.window._arm_button.text(), "the label did not follow")

        self.window._arm_button.click()
        self.assertTrue(self.server.is_armed)
        self.assertEqual(1, self.server.arm_calls)
        self.assertEqual("Stop", self.window._arm_button.text())

    def test_stopping_uses_disarm_and_never_the_fuse(self):
        """trip_fuse is for a FAULT: it appends "Press Start once it is fixed" to a reason, so calling it
        with none raised inside the click handler and the press did nothing at all."""
        self.window._arm_button.click()
        self.assertEqual(1, len(self.server.disarm_reasons))
        self.assertNotIn("Press Start", self.server.disarm_reasons[0])

    # --------------------------------------------------------------------------- what is locked, when
    def test_only_the_encoder_is_locked_while_a_ps3_streams(self):
        """Everything else is read when the NEXT stream starts, so locking it took the settings away at
        the one moment somebody wants to change one - and made the window look unusable."""
        self.server.is_ps3_connected = True
        self.window._refresh()
        self.assertFalse(self.window._encoder_row.control.isEnabled())
        for row in (self.window._size_row, self.window._fps_row, self.window._bitrate_row,
                    self.window._loss_row, self.window._entropy_row, self.window._rate_row,
                    self.window._slice_row, self.window._display_row):
            self.assertTrue(row.control.isEnabled(), row.title.text())

    def test_the_encoder_is_free_again_once_the_stream_ends(self):
        self.server.is_ps3_connected = True
        self.window._refresh()
        self.server.is_ps3_connected = False
        self.window._refresh()
        self.assertTrue(self.window._encoder_row.control.isEnabled())

    # ------------------------------------------------------------------- every dropdown reaches through
    def test_each_dropdown_writes_its_setting(self):
        cases = (
            (self.window._size_combo, protocol.STREAM_SIZES, "stream_size"),
            (self.window._fps_combo, protocol.FPS_CHOICES, "stream_fps"),
            (self.window._bitrate_combo, protocol.BITRATE_CHOICES_KBPS, "video_kbps"),
            (self.window._entropy_combo, protocol.ENTROPY_CODERS, "entropy_coder"),
            (self.window._rate_combo, protocol.RATE_CONTROLS, "rate_control"),
            (self.window._slice_combo, protocol.SLICE_COUNTS, "slice_count"),
            (self.window._loss_combo, LOSS_RECOVERY_KINDS, "loss_recovery"),
            (self.window._display_combo, DISPLAY_STRATEGIES, "display_strategy"),
        )
        for combo, choices, attribute in cases:
            with self.subTest(setting=attribute):
                index = len(choices) - 1
                combo.setCurrentIndex(index)
                self.assertEqual(choices[index], getattr(self.server, attribute))

    def test_the_swap_switch_reaches_through(self):
        self.window._swap.setChecked(True)
        self.assertTrue(self.server.swap_mouse_sticks)
        self.window._swap.setChecked(False)
        self.assertFalse(self.server.swap_mouse_sticks)

    def test_every_dropdown_has_exactly_as_many_entries_as_its_source(self):
        """Two lists that must agree is one list too many - this project has shifted a dropdown against
        its own values twice already, and a silent off-by-one picks the wrong resolution."""
        for combo, choices in ((self.window._size_combo, protocol.STREAM_SIZES),
                               (self.window._fps_combo, protocol.FPS_CHOICES),
                               (self.window._bitrate_combo, protocol.BITRATE_CHOICES_KBPS),
                               (self.window._entropy_combo, protocol.ENTROPY_CODERS),
                               (self.window._rate_combo, protocol.RATE_CONTROLS),
                               (self.window._slice_combo, protocol.SLICE_COUNTS),
                               (self.window._loss_combo, LOSS_RECOVERY_KINDS),
                               (self.window._display_combo, DISPLAY_STRATEGIES)):
            with self.subTest(first=combo.itemText(0)):
                self.assertEqual(len(choices), combo.count())

    # ----------------------------------------------------------------------------- the explanations
    def test_the_hint_follows_the_selection(self):
        for index in range(len(protocol.STREAM_SIZES)):
            self.window._size_combo.setCurrentIndex(index)
            self.assertEqual(size_hints()[index], self.window._size_row.hint.text())
        for index in range(len(DISPLAY_STRATEGIES)):
            self.window._display_combo.setCurrentIndex(index)
            self.assertEqual(DISPLAY_HINTS[index], self.window._display_row.hint.text())

    def test_the_fixed_hints_are_the_shared_ones(self):
        """Both windows show the same sentence because they read the same constant - written out a second
        time it fell out of the German table and showed English in a German window."""
        self.assertEqual(FPS_HINT, self.window._fps_row.hint.text())
        self.assertEqual(BITRATE_HINT, self.window._bitrate_row.hint.text())

    # ------------------------------------------------------------------------------ the two languages
    def test_switching_language_relabels_without_changing_a_setting(self):
        """The dangerous half of a language switch: the lists are rebuilt, and an index that does not
        survive silently picks a different resolution."""
        self.window._size_combo.setCurrentIndex(4)
        before = self.server.stream_size
        set_language("de")
        try:
            self.assertEqual("Bildrate", self.window._fps_row.title.text())
            self.assertEqual(4, self.window._size_combo.currentIndex())
            self.assertEqual(before, self.server.stream_size, "the language switch moved a setting")
            self.assertNotEqual(FPS_HINT, self.window._fps_row.hint.text(), "the hint stayed English")
        finally:
            set_language("en")
        self.assertEqual("Frame rate", self.window._fps_row.title.text())
        self.assertEqual(before, self.server.stream_size)

    def test_both_languages_label_every_dropdown_entry(self):
        for code in ("en", "de"):
            set_language(code)
            for combo in (self.window._size_combo, self.window._fps_combo, self.window._bitrate_combo,
                          self.window._loss_combo, self.window._rate_combo, self.window._slice_combo,
                          self.window._display_combo, self.window._theme_combo):
                for index in range(combo.count()):
                    with self.subTest(language=code, entry=index):
                        self.assertTrue(combo.itemText(index).strip(), "an empty entry in the dropdown")
        set_language("en")

    # -------------------------------------------------------------------------------- light and dark
    def test_each_appearance_asks_for_the_right_scheme(self):
        """Only the ASKING can be checked here. The offscreen plugin has no system theme and ignores
        setColorScheme outright - measured: colorScheme() stays Unknown whatever it is told. That the
        palette really moves was measured on the machine itself instead: window colour #f3f3f3 light
        against #1e1e1e dark, with the windows11 style still in place, so it is the platform's own dark
        mode rather than a repaint of ours."""
        asked = []
        self.window._apply_theme = asked.append
        for label, kind in (("Light", "light"), ("Dark", "dark"), ("Follow Windows", "system")):
            with self.subTest(appearance=label):
                self.window._theme_combo.setCurrentIndex(self.window._theme_combo.findText(label))
                self.assertEqual(kind, asked[-1])

    def test_the_appearance_is_remembered(self):
        from teecellstream.settings import settings
        self.window._theme_combo.setCurrentIndex(self.window._theme_combo.findText("Dark"))
        self.assertEqual("dark", settings.get("theme", "system"))
        self.window._theme_combo.setCurrentIndex(self.window._theme_combo.findText("Follow Windows"))
        self.assertEqual("system", settings.get("theme", "system"))

    def test_the_quiet_labels_are_recoloured_from_the_CURRENT_palette(self):
        """They used to keep the colour they were built with - light grey on a dark window after one
        switch, which is the one combination nobody can read. The invariant that holds on any platform:
        after a change of appearance a hint's colour is the palette's text colour, whatever that is."""
        from PySide6.QtGui import QPalette
        self.window._theme_combo.setCurrentIndex(self.window._theme_combo.findText("Dark"))
        text = QApplication.palette().color(QPalette.ColorRole.WindowText)
        self.assertIn("%d,%d,%d" % (text.red(), text.green(), text.blue()),
                      self.window._fps_row.hint.styleSheet())
        self.window._theme_combo.setCurrentIndex(self.window._theme_combo.findText("Follow Windows"))

    # --------------------------------------------------------------------------------- the status line
    def test_the_status_line_and_the_dot_follow_the_server(self):
        self.window._refresh()
        self.assertEqual("Waiting for a PS3 …", self.window._status.text())

        self.server.is_ps3_connected = True
        self.server.connected_ps3 = "192.0.2.5"
        self.window._refresh()
        self.assertEqual("PS3 connected: 192.0.2.5", self.window._status.text())

        self.server.is_armed = False
        self.server.trip_reason = "stopped by you"
        self.window._refresh()
        self.assertEqual("Stopped", self.window._status.text())
        self.assertEqual("stopped by you", self.window._summary.text(), "the reason must replace the summary")

    # ------------------------------------------------------------------------------- the command slots
    def test_a_slot_saves_what_was_typed(self):
        from teecellstream import custom_commands
        slot = self.window._slots[0]
        slot["kind"].setCurrentIndex(1)            # "Run a command or URI"
        slot["value"].setText("steam://open/bigpicture")
        slot["name"].setText("Big Picture")
        self.window.save_pending_commands()
        self.window._save_slot(1)
        stored = custom_commands.get(1)
        self.assertEqual("run", stored["kind"])
        self.assertEqual("steam://open/bigpicture", stored["value"])
        self.assertEqual("Big Picture", stored["label"])

    def test_the_command_field_is_dead_while_the_slot_is_off(self):
        slot = self.window._slots[1]
        slot["kind"].setCurrentIndex(0)            # "None"
        self.assertFalse(slot["value"].isEnabled())
        self.assertTrue(slot["name"].isEnabled(), "the name is a label for the slot and always editable")
        slot["kind"].setCurrentIndex(1)
        self.assertTrue(slot["value"].isEnabled())

    # ----------------------------------------------------------------------- the "can you see this?" box
    def test_the_prompt_counts_down_and_switches_back_by_itself(self):
        """Answering nothing has to mean no: the case this exists for is a screen showing nothing."""
        self.server.display_mode.is_confirmed = False
        self.window._show_confirm(2)
        dialog = self.window._confirm
        self.assertIsNotNone(dialog)
        self.assertIn("2", dialog._text.text())
        dialog._tick()
        dialog._tick()
        dialog._tick()
        self.assertEqual(1, self.server.display_mode.rejected)
        self.assertEqual(0, self.server.display_mode.confirmed)

    def test_answering_yes_keeps_the_mode(self):
        self.server.display_mode.is_confirmed = False
        self.window._show_confirm(15)
        self.window._confirm._keep()
        self.assertEqual(1, self.server.display_mode.confirmed)
        self.assertEqual(0, self.server.display_mode.rejected)

    def test_the_prompt_is_the_one_the_display_thread_was_handed(self):
        """It arrives on the switching thread, so it has to cross over as a signal - a widget touched
        from that thread is a crash, not a glitch."""
        self.assertIsNotNone(self.server.display_mode.prompt)


if __name__ == "__main__":
    unittest.main()


class SupportLinksTests(unittest.TestCase):
    """The three links live in the window, not only in the About box - and an About box is where a
    link goes to be seen once."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        set_language("en")
        from teecellstream.ui_windows import MainWindow
        self.window = MainWindow(QtServer())

    def tearDown(self):
        self.window.close()
        self.app.processEvents()

    def test_all_three_addresses_are_in_the_window(self):
        from teecellstream import URL_DONATE, URL_GITHUB, URL_HUB
        markup = self.window._support_links.text()
        for url in (URL_DONATE, URL_HUB, URL_GITHUB):
            self.assertIn(url, markup)
        self.assertTrue(self.window._support_links.openExternalLinks(),
                        "a link that does not open is a decoration")

    def test_the_pitch_says_what_the_money_buys(self):
        from teecellstream import DONATE_PITCH
        self.assertEqual(DONATE_PITCH, self.window._support_pitch.text())

    def test_it_is_translated_too(self):
        from teecellstream import DONATE_PITCH
        set_language("de")
        try:
            self.assertNotEqual(DONATE_PITCH, self.window._support_pitch.text())
            self.assertIn("bero-host.de", self.window._support_links.text())
        finally:
            set_language("en")
