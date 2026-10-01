"""The window on Windows: the same view onto the server as ui.py, built in Qt instead of GTK.

Why a second window at all, rather than porting the first: ui.py is GTK4 and libadwaita, and PyGObject
on Windows means MSYS2 and a folder of DLLs that no single .exe survives. Qt is the other way round -
it ships as a wheel, and since Qt 6.7 it carries Microsoft's own Windows 11 style, which the measured
machine reports as the ACTIVE style (windows11, alongside windowsvista/Windows/Fusion). So this window
is not an imitation of the platform look; it is the platform look, including dark mode, which Qt takes
from the system and which the user can override here.

What is NOT written twice: every label, every explanation, every list of choices. They live in
ui_text.py and both windows read them from there - the same discipline as stick.py and
display_choose.py, and for the same reason: the resolution names and their explanations have already
drifted apart twice in this project, once silently shifting every hint by one place.

The server is polled, never subscribed to - it announces nothing. 500 ms, like the GTK window.
"""

import os
import subprocess
import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (QAction, QColor, QGuiApplication, QIcon, QKeySequence, QPainter,
                           QPalette, QPixmap)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSplitter,
                               QSystemTrayIcon, QTabWidget, QVBoxLayout, QWidget)

from . import (APP_NAME, DONATE_HEADLINE, DONATE_PITCH, LINK_DONATE, LINK_GITHUB, LINK_HUB,
               UPSTREAM_VERSION, URL_DONATE, URL_GITHUB, URL_HUB, __version__,
               autostart_windows, custom_commands, log, protocol)
from .display_choose import CONFIRM_SECONDS, DISPLAY_STRATEGIES
from .i18n import _, available_languages, language, off_language_changed, on_language_changed, set_language
from .settings import settings
from .ui_text import (BITRATE_HINT, CODEC_HINTS, CODEC_LABELS, COMMAND_KINDS, COMMAND_KIND_LABELS, COMMANDS_INTRO,
                      DEBLOCK_HINTS, DEBLOCK_LABELS, DEBLOCK_UNAVAILABLE_HINT, DISPLAY_HINTS, DISPLAY_LABELS,
                      MOTION_HINTS, MOTION_LABELS, MOTION_UNAVAILABLE_HINT, ENTROPY_HINTS, ENTROPY_LABELS,
                      HIDE_HINT, LANGUAGE_CODES, LANGUAGE_LABELS,
                      FPS_HINT, LOSS_RECOVERY_HINTS, LOSS_RECOVERY_KINDS, LOSS_RECOVERY_LABELS, RATE_HINTS,
                      RATE_LABELS, SLICE_HINTS, SLICE_LABELS, bitrate_labels, fps_labels, size_hints,
                      size_labels, source_rate_text, status_text, nvenc_switch_hint)

REFRESH_TICK_MS = 500          # the same beat as the GTK window; the server announces nothing
WINDOW_WIDTH, WINDOW_HEIGHT = 720, 660
CONTENT_MAX_WIDTH = 820        # what Adw.Clamp does on the other side: text stops being a single long line
LOG_MIN_HEIGHT = 150
SLOT_SAVE_DELAY_MS = 400       # typing in a command field: save once the fingers pause, not per keystroke

THEME_KINDS = ("system", "light", "dark")
THEME_LABELS = ("Follow Windows", "Light", "Dark")


_HINTS: list = []     # every quiet label, so a change of theme can recolour all of them


def _dim(widget: QLabel) -> QLabel:
    """The explanation under a setting: smaller, quieter, and allowed to wrap onto a second line."""
    widget.setWordWrap(True)
    font = widget.font()
    font.setPointSizeF(max(7.5, font.pointSizeF() - 0.8))
    widget.setFont(font)
    _HINTS.append(widget)
    _recolour(widget)
    return widget


def _recolour(widget: QLabel) -> None:
    """Quiet, but quiet RELATIVE to the current theme - a colour taken once at build time would be
    light grey on a dark window after the first switch."""
    colour = QApplication.palette().color(QPalette.ColorRole.WindowText)
    widget.setStyleSheet("color: rgba(%d,%d,%d,175);" % (colour.red(), colour.green(), colour.blue()))


def recolour_hints() -> None:
    for widget in list(_HINTS):
        try:
            _recolour(widget)
        except RuntimeError:
            _HINTS.remove(widget)     # the C++ side is gone; the Python wrapper outlived it


def _dot(colour: str, size: int = 14) -> QPixmap:
    """The status dot. Drawn rather than shipped as a file - two colours are not worth an asset."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(colour))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(0, 0, size - 1, size - 1)
    painter.end()
    return pixmap


class Row:
    """One setting: a title, a control, and the sentence underneath that explains the choice.

    libadwaita gives this for free (Adw.ComboRow has a subtitle). Qt does not, and the sentence is the
    part that matters - every one of them is a measured number from this project, and a dropdown that
    only shows "CAVLC" tells nobody why they should want it.
    """

    def __init__(self, grid: QGridLayout, row: int, title: str, control: QWidget, hint: str = ""):
        self.title = QLabel(title)
        self.title.setWordWrap(True)
        self.control = control
        self.hint = _dim(QLabel(hint))
        control.setMinimumWidth(260)
        grid.addWidget(self.title, row * 2, 0)
        grid.addWidget(control, row * 2, 1, alignment=Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self.hint, row * 2 + 1, 0, 1, 2)
        self.hint.setVisible(bool(hint))

    def set_hint(self, text: str) -> None:
        self.hint.setText(text)
        self.hint.setVisible(bool(text))

    def set_enabled(self, enabled: bool) -> None:
        self.control.setEnabled(enabled)
        self.title.setEnabled(enabled)


class ConfirmDialog(QDialog):
    """"Can you see this window?" - shown after the desktop mode was switched.

    It counts down out loud, because the case it exists for is the one where the user sees NOTHING: a
    mode the monitor cannot show. Answering nothing is therefore the same as saying no, and the server
    puts the old mode back. It can also close itself without an answer, from the other side: as soon as
    the console proves it is receiving pictures, the server confirms and this goes away.
    """

    def __init__(self, parent, seconds: int, on_keep, on_revert):
        super().__init__(parent)
        self.setWindowTitle(_("Can you see this window?"))
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._left = seconds
        self._on_keep, self._on_revert = on_keep, on_revert
        self._answered = False

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        self._text = QLabel()
        self._text.setWordWrap(True)
        layout.addWidget(self._text)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        revert = QPushButton(_("No, switch back"))
        keep = QPushButton(_("Yes, keep it"))
        keep.setDefault(True)
        revert.clicked.connect(self._revert)
        keep.clicked.connect(self._keep)
        buttons.addWidget(revert)
        buttons.addWidget(keep)
        layout.addLayout(buttons)

        self._tick()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _tick(self) -> None:
        self._text.setText(_("The desktop was switched to the streaming resolution. Switching back in "
                             "%d s unless you confirm.") % max(0, self._left))
        if self._left <= 0:
            self._revert()       # no answer is an answer: the screen is probably black
            return
        self._left -= 1

    def _finish(self, action) -> None:
        if self._answered:
            return
        self._answered = True
        self._timer.stop()
        action()
        self.accept()

    def _keep(self) -> None:
        self._finish(self._on_keep)

    def _revert(self) -> None:
        self._finish(self._on_revert)

    def closeEvent(self, event) -> None:     # noqa: N802 - Qt's name
        self._revert()                        # closing it is not an answer either
        super().closeEvent(event)

    def confirmed_elsewhere(self) -> None:
        """The console started receiving: the question answered itself, so take it off the screen."""
        if not self._answered:
            self._answered = True
            self._timer.stop()
            self.accept()


class MainWindow(QMainWindow):
    """The window. Duck-typed against the server, exactly like the GTK one, so the tests can drive it."""

    # The display-mode prompt arrives on the switching thread, not on the GUI thread. Qt widgets may only
    # be touched from the GUI thread, so it comes across as a signal - Qt queues it by itself.
    confirm_requested = Signal(int)

    def __init__(self, server, on_quit=None):
        super().__init__()
        self._server = server
        self._on_quit = on_quit
        self._rows: list = []
        self._retranslate: list = []
        self._log_generation = -1
        self._encoder_names: list = []
        self._confirm: ConfirmDialog | None = None
        self._slot_timers: dict = {}
        self._building = True

        self.setWindowTitle(APP_NAME)
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setMinimumSize(560, 480)

        self._tabs = QTabWidget()
        self.setCentralWidget(self._tabs)
        self._tabs.addTab(self._build_server_page(), _("Server"))
        self._tabs.addTab(self._build_commands_page(), _("Commands"))
        self._build_menu()

        self.confirm_requested.connect(self._show_confirm)
        self._server.display_mode.set_confirm_prompt(self.confirm_requested.emit)

        self._building = False
        self._apply_theme(str(settings.get("theme", "system") or "system"))
        self._refresh()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(REFRESH_TICK_MS)
        on_language_changed(self._retranslate_all)

    # ------------------------------------------------------------------------------------ the pages
    def _build_server_page(self) -> QWidget:
        splitter = QSplitter(Qt.Orientation.Vertical)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setMaximumWidth(CONTENT_MAX_WIDTH)
        column = QVBoxLayout(inner)
        column.setContentsMargins(18, 18, 18, 18)
        column.setSpacing(16)
        column.addWidget(self._build_status_card())
        column.addWidget(self._build_video_group())
        column.addWidget(self._build_input_group())
        column.addWidget(self._build_system_group())
        column.addWidget(self._build_support_group())
        hide_hint = _dim(QLabel(_(HIDE_HINT)))
        self._retranslate.append(lambda: hide_hint.setText(_(HIDE_HINT)))
        column.addWidget(hide_hint)
        column.addStretch(1)
        scroll.setWidget(inner)

        splitter.addWidget(scroll)
        splitter.addWidget(self._build_log_pane())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        return splitter

    def _build_status_card(self) -> QWidget:
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        self._dot = QLabel()
        self._dot.setPixmap(_dot("#8a8a8a"))
        self._dot.setFixedSize(16, 16)
        layout.addWidget(self._dot, alignment=Qt.AlignmentFlag.AlignTop)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        self._status = QLabel()
        font = self._status.font()
        font.setPointSizeF(font.pointSizeF() + 2.5)
        font.setBold(True)
        self._status.setFont(font)
        self._status.setWordWrap(True)
        self._summary = _dim(QLabel())
        texts.addWidget(self._status)
        texts.addWidget(self._summary)
        layout.addLayout(texts, 1)

        self._arm_button = QPushButton()
        self._arm_button.setMinimumWidth(110)
        self._arm_button.clicked.connect(self._toggle_armed)
        layout.addWidget(self._arm_button, alignment=Qt.AlignmentFlag.AlignVCenter)
        return card

    def _group(self, title: str) -> tuple[QGroupBox, QGridLayout]:
        box = QGroupBox(title)
        grid = QGridLayout(box)
        grid.setColumnStretch(0, 1)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)
        return box, grid

    def _combo(self, labels, on_change) -> QComboBox:
        combo = QComboBox()
        combo.addItems(list(labels))
        combo.currentIndexChanged.connect(lambda index: None if self._building else on_change(index))
        return combo

    def _build_video_group(self) -> QWidget:
        box, grid = self._group(_("Video"))
        line = 0

        self._encoder_combo = self._combo([], self._on_encoder)
        self._encoder_row = Row(grid, line, _("Encoder"), self._encoder_combo,
                                _("Locked while a PS3 is streaming"))
        line += 1

        self._loss_combo = self._combo([_(text) for text in LOSS_RECOVERY_LABELS], self._on_loss)
        self._loss_row = Row(grid, line, _("Error correction"), self._loss_combo)
        line += 1

        self._size_combo = self._combo(size_labels(), self._on_size)
        self._size_row = Row(grid, line, _("Resolution"), self._size_combo)
        line += 1

        self._fps_combo = self._combo(fps_labels(), self._on_fps)
        self._fps_row = Row(grid, line, _("Frame rate"), self._fps_combo, _(FPS_HINT))
        line += 1

        self._bitrate_combo = self._combo(bitrate_labels(), self._on_bitrate)
        self._bitrate_row = Row(grid, line, _("Bitrate"), self._bitrate_combo, _(BITRATE_HINT))
        line += 1

        # the three rows 1.1.0 added to the GTK window, in the same order there
        self._codec_combo = self._combo([_(text) for text in CODEC_LABELS], self._on_codec)
        self._codec_row = Row(grid, line, _("Codec"), self._codec_combo)
        line += 1

        self._entropy_combo = self._combo(ENTROPY_LABELS, self._on_entropy)
        self._entropy_row = Row(grid, line, _("Entropy coding"), self._entropy_combo)
        line += 1

        self._deblock_combo = self._combo([_(text) for text in DEBLOCK_LABELS], self._on_deblock)
        self._deblock_row = Row(grid, line, _("NVENC deblocking filter"), self._deblock_combo)
        line += 1

        self._motion_combo = self._combo([_(text) for text in MOTION_LABELS], self._on_motion)
        self._motion_row = Row(grid, line, _("NVENC motion vectors"), self._motion_combo)
        line += 1

        self._rate_combo = self._combo([_(text) for text in RATE_LABELS], self._on_rate)
        self._rate_row = Row(grid, line, _("Rate control"), self._rate_combo)
        line += 1

        self._slice_combo = self._combo([_(text) for text in SLICE_LABELS], self._on_slices)
        self._slice_row = Row(grid, line, _("Slices per picture (experiment)"), self._slice_combo)
        line += 1

        self._display_combo = self._combo([_(text) for text in DISPLAY_LABELS], self._on_display)
        self._display_row = Row(grid, line, _("The desktop while streaming"), self._display_combo)

        self._rows += [self._encoder_row, self._loss_row, self._size_row, self._fps_row,
                       self._bitrate_row, self._codec_row, self._entropy_row, self._deblock_row,
                       self._motion_row, self._rate_row, self._slice_row, self._display_row]
        self._retranslate.append(self._retranslate_video)
        return box

    def _build_input_group(self) -> QWidget:
        box, grid = self._group(_("Input"))
        self._swap = QCheckBox()
        self._swap.stateChanged.connect(
            lambda _state: None if self._building else setattr(self._server, "swap_mouse_sticks",
                                                               self._swap.isChecked()))
        self._swap_row = Row(grid, 0, _("Swap the sticks in mouse mode"), self._swap,
                             _("The right stick moves the pointer"))
        self._swap.setMinimumWidth(0)
        self._retranslate.append(lambda: (
            self._swap_row.title.setText(_("Swap the sticks in mouse mode")),
            self._swap_row.set_hint(_("The right stick moves the pointer"))))
        return box

    def _build_system_group(self) -> QWidget:
        box, grid = self._group(_("System"))

        self._language_combo = self._combo(LANGUAGE_LABELS, self._on_language)
        self._language_row = Row(grid, 0, _("Language"), self._language_combo,
                                 _("The interface switches over at once – no restart"))

        self._theme_combo = self._combo([_(text) for text in THEME_LABELS], self._on_theme)
        self._theme_row = Row(grid, 1, _("Appearance"), self._theme_combo,
                              _("Dark, light, or whatever Windows is set to"))

        self._autostart = QCheckBox()
        self._autostart.stateChanged.connect(
            lambda _state: None if self._building else self._on_autostart(self._autostart.isChecked()))
        self._autostart_row = Row(grid, 2, _("Start at login (minimised)"), self._autostart,
                                  _("Puts a shortcut in the Startup folder"))
        self._retranslate.append(self._retranslate_system)
        return box

    def _build_support_group(self) -> QWidget:
        """The three links, clickable. Not buried in an About box: the About box is where a link goes
        to be seen once, and the whole point of the donation one is that it pays for the server this
        thing is built on - one euro covers a month of it."""
        box, grid = self._group(_(DONATE_HEADLINE))
        self._support_pitch = _dim(QLabel(_(DONATE_PITCH)))
        grid.addWidget(self._support_pitch, 0, 0, 1, 2)
        self._support_links = QLabel()
        self._support_links.setOpenExternalLinks(True)
        self._support_links.setTextFormat(Qt.TextFormat.RichText)
        self._support_links.setWordWrap(True)
        grid.addWidget(self._support_links, 1, 0, 1, 2)
        self._retranslate.append(self._retranslate_support)
        self._retranslate_support()
        return box

    def _retranslate_support(self) -> None:
        self._support_pitch.setText(_(DONATE_PITCH))
        self._support_links.setText(
            '<a href="%s">%s</a> &nbsp;·&nbsp; <a href="%s">%s</a> &nbsp;·&nbsp; <a href="%s">%s</a>'
            % (URL_DONATE, _("Donate"), URL_HUB, _("All my projects"), URL_GITHUB, _("Source code")))

    def _build_log_pane(self) -> QWidget:
        pane = QWidget()
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(18, 6, 18, 12)
        header = QHBoxLayout()
        self._log_heading = QLabel(_("Log"))
        heading_font = self._log_heading.font()
        heading_font.setBold(True)
        self._log_heading.setFont(heading_font)
        header.addWidget(self._log_heading)
        header.addStretch(1)
        self._open_log_button = QPushButton(_("Open the log"))
        self._open_log_button.clicked.connect(self._open_log)
        header.addWidget(self._open_log_button)
        layout.addLayout(header)

        self._log_view = QPlainTextEdit()
        self._log_view.setReadOnly(True)
        self._log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._log_view.setMaximumBlockCount(log.RECENT_LINES + 20)
        self._log_view.setMinimumHeight(LOG_MIN_HEIGHT)
        font = self._log_view.font()
        font.setFamilies(["Consolas", "Cascadia Mono", "Courier New", "monospace"])
        self._log_view.setFont(font)
        layout.addWidget(self._log_view, 1)
        self._retranslate.append(lambda: (self._log_heading.setText(_("Log")),
                                          self._open_log_button.setText(_("Open the log"))))
        return pane

    def _build_commands_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setMaximumWidth(CONTENT_MAX_WIDTH)
        column = QVBoxLayout(inner)
        column.setContentsMargins(18, 18, 18, 18)
        column.setSpacing(14)

        self._commands_intro = _dim(QLabel(_(COMMANDS_INTRO)))
        column.addWidget(self._commands_intro)

        self._slots: list = []
        for slot in range(1, custom_commands.SLOT_COUNT + 1):
            box, grid = self._group(_("Command %d") % slot)
            kind = self._combo([_(text) for text in COMMAND_KIND_LABELS],
                               lambda index, s=slot: self._on_command_kind(s, index))
            value = QLineEdit()
            name = QLineEdit()
            kind_row = Row(grid, 0, _("Action"), kind)
            value_row = Row(grid, 1, _("Command or URI"), value)
            name_row = Row(grid, 2, _("Name"), name)
            value.setMinimumWidth(300)
            name.setMinimumWidth(300)
            value.textEdited.connect(lambda _t, s=slot: self._save_slot_soon(s))
            name.textEdited.connect(lambda _t, s=slot: self._save_slot_soon(s))
            self._slots.append({"box": box, "kind": kind, "value": value, "name": name,
                                "rows": (kind_row, value_row, name_row)})
            column.addWidget(box)
        column.addStretch(1)
        scroll.setWidget(inner)
        self._load_commands()
        self._retranslate.append(self._retranslate_commands)
        return scroll

    def _build_menu(self) -> None:
        bar = self.menuBar()
        self._program_menu = bar.addMenu(_("Program"))
        self._open_log_action = QAction(_("Open the log"), self)
        self._open_log_action.setShortcut(QKeySequence("Ctrl+L"))
        self._open_log_action.triggered.connect(self._open_log)
        self._program_menu.addAction(self._open_log_action)
        self._program_menu.addSeparator()
        self._quit_action = QAction(_("Quit"), self)
        self._quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self._quit_action.triggered.connect(self._quit)
        self._program_menu.addAction(self._quit_action)

        self._help_menu = bar.addMenu(_("Help"))
        self._about_action = QAction(_("About %s") % APP_NAME, self)
        self._about_action.triggered.connect(self._about)
        self._help_menu.addAction(self._about_action)
        self._retranslate.append(self._retranslate_menu)

    # --------------------------------------------------------------------------- what the user changes
    def _toggle_armed(self) -> None:
        # disarm(), not trip_fuse(): trip_fuse is for a FAULT and appends "Press Start once it is fixed"
        # to the reason - with no reason to append to it raised a TypeError inside the click handler,
        # the server stayed armed, and the button therefore kept saying Stop however often it was
        # pressed. disarm also ends a running stream and gives the desktop back, which is the whole job.
        if self._server.is_armed:
            self._server.disarm("stopped by you")
        else:
            self._server.arm()
        self._refresh()

    def _on_encoder(self, index: int) -> None:
        encoders = list(self._server.available_encoders)
        if 0 <= index < len(encoders):
            self._server.chosen_encoder = encoders[index]

    def _on_loss(self, index: int) -> None:
        self._server.loss_recovery = LOSS_RECOVERY_KINDS[index]
        self._loss_row.set_hint(_(LOSS_RECOVERY_HINTS[index]))

    def _on_size(self, index: int) -> None:
        self._server.stream_size = protocol.STREAM_SIZES[index]
        self._size_row.set_hint(_(size_hints()[index]))

    def _on_fps(self, index: int) -> None:
        self._server.stream_fps = protocol.FPS_CHOICES[index]

    def _on_bitrate(self, index: int) -> None:
        self._server.video_kbps = protocol.BITRATE_CHOICES_KBPS[index]

    def _on_codec(self, index: int) -> None:
        if 0 <= index < len(protocol.VIDEO_CODECS):
            self._server.video_codec = protocol.VIDEO_CODECS[index]
            self._codec_row.set_hint(_(CODEC_HINTS[index]))

    def _on_deblock(self, index: int) -> None:
        if 0 <= index < len(protocol.NVENC_DEBLOCKING):
            self._server.nvenc_deblocking = protocol.NVENC_DEBLOCKING[index]

    def _on_motion(self, index: int) -> None:
        if 0 <= index < len(protocol.NVENC_MOTION):
            self._server.nvenc_motion = protocol.NVENC_MOTION[index]

    def _on_entropy(self, index: int) -> None:
        self._server.entropy_coder = protocol.ENTROPY_CODERS[index]
        self._entropy_row.set_hint(_(ENTROPY_HINTS[index]))

    def _on_rate(self, index: int) -> None:
        self._server.rate_control = protocol.RATE_CONTROLS[index]
        self._rate_row.set_hint(_(RATE_HINTS[index]))

    def _on_slices(self, index: int) -> None:
        self._server.slice_count = protocol.SLICE_COUNTS[index]
        self._slice_row.set_hint(_(SLICE_HINTS[index]))

    def _on_display(self, index: int) -> None:
        self._server.display_strategy = DISPLAY_STRATEGIES[index]
        self._display_row.set_hint(_(DISPLAY_HINTS[index]))

    def _on_language(self, index: int) -> None:
        code = LANGUAGE_CODES[index]
        settings.set("language", code)
        set_language(code)      # every listener, this window included, relabels itself

    def _on_theme(self, index: int) -> None:
        self._apply_theme(THEME_KINDS[index])
        settings.set("theme", THEME_KINDS[index])

    def _apply_theme(self, kind: str) -> None:
        """Qt 6.8 and later carry the colour scheme themselves; all this does is override the system.
        Measured on the test machine: setting Dark takes the window colour from #f3f3f3 to #1e1e1e and
        leaves the windows11 style in place - so this is the platform's own dark mode, not a repaint."""
        scheme = {"light": Qt.ColorScheme.Light, "dark": Qt.ColorScheme.Dark}.get(kind,
                                                                                  Qt.ColorScheme.Unknown)
        try:
            QGuiApplication.styleHints().setColorScheme(scheme)
        except (AttributeError, TypeError) as error:
            log.write(_("window: this Qt cannot switch the appearance (%s)") % error)
            return
        recolour_hints()
        log.write(_("window: appearance %s, window colour %s")
                  % (kind, QApplication.palette().color(QPalette.ColorRole.Window).name()))

    def _on_autostart(self, wanted: bool) -> None:
        actual = autostart_windows.set_enabled(wanted)
        if actual != wanted:
            self._autostart.blockSignals(True)
            self._autostart.setChecked(actual)
            self._autostart.blockSignals(False)

    # ------------------------------------------------------------------------------- the command slots
    def _load_commands(self) -> None:
        for index, widgets in enumerate(self._slots, start=1):
            stored = custom_commands.get(index) or custom_commands.empty_command()
            kind = stored.get("kind", COMMAND_KINDS[0])
            widgets["kind"].blockSignals(True)
            widgets["kind"].setCurrentIndex(COMMAND_KINDS.index(kind) if kind in COMMAND_KINDS else 0)
            widgets["kind"].blockSignals(False)
            widgets["value"].setText(stored.get("value", ""))
            widgets["name"].setText(stored.get("label", ""))
            self._update_slot_enabled(index)

    def _update_slot_enabled(self, slot: int) -> None:
        widgets = self._slots[slot - 1]
        runs = widgets["kind"].currentIndex() == COMMAND_KINDS.index(custom_commands.KIND_RUN)
        widgets["rows"][1].set_enabled(runs)     # the command line is meaningless while the slot is off
        widgets["rows"][2].set_enabled(True)     # the name is a label for the slot and always editable

    def _on_command_kind(self, slot: int, index: int) -> None:
        self._update_slot_enabled(slot)
        self._save_slot(slot)

    def _save_slot_soon(self, slot: int) -> None:
        """Typing saves once the fingers pause - not on every keystroke, which would rewrite the file 60
        times for one URI."""
        timer = self._slot_timers.get(slot)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.timeout.connect(lambda s=slot: self._save_slot(s))
            self._slot_timers[slot] = timer
        timer.start(SLOT_SAVE_DELAY_MS)

    def _save_slot(self, slot: int) -> None:
        widgets = self._slots[slot - 1]
        custom_commands.set(slot, {"kind": COMMAND_KINDS[widgets["kind"].currentIndex()],
                                   "value": widgets["value"].text(),
                                   "label": widgets["name"].text()})

    def save_pending_commands(self) -> None:
        """Called before the window goes away: a half-typed slot must not be lost to a closing window."""
        for slot, timer in self._slot_timers.items():
            if timer.isActive():
                timer.stop()
                self._save_slot(slot)

    # --------------------------------------------------------------------------------- the 500 ms beat
    def _refresh(self) -> None:
        server = self._server
        connected = bool(server.is_ps3_connected)
        self._dot.setPixmap(_dot("#2ecc71" if connected else "#8a8a8a"))
        self._status.setText(status_text(server.is_armed, connected, server.connected_ps3 or ""))

        if not server.is_armed and server.trip_reason:
            self._summary.setText(_(server.trip_reason))
        else:
            extra = ""
            if connected and server.live_streamer is not None:
                capture = getattr(server.live_streamer, "capture", None)
                captured = getattr(capture, "captured_fps", 0) if capture is not None else 0
                # the cadence is the one that was CHOSEN, not protocol.FPS - the GTK window reads the
                # constant here and therefore judges a 30 fps stream against 60
                extra = source_rate_text(int(captured or 0), int(server.stream_fps))
            self._summary.setText(server.settings_summary + extra)

        self._arm_button.setText(_("Stop") if server.is_armed else _("Start"))
        streaming = connected

        encoders = [encoder.name for encoder in server.available_encoders]
        if encoders != self._encoder_names:
            self._encoder_names = encoders
            self._encoder_combo.blockSignals(True)
            self._encoder_combo.clear()
            self._encoder_combo.addItems(encoders)
            self._encoder_combo.blockSignals(False)
        self._encoder_row.set_enabled(bool(encoders) and not streaming)
        self._encoder_row.set_hint(_("Locked while a PS3 is streaming") if streaming else
                                   (_("No H.264 encoder found") if not encoders else ""))

        self._select(self._encoder_combo, self._index_of_encoder())
        self._select(self._loss_combo, self._index_in(LOSS_RECOVERY_KINDS, server.loss_recovery))
        self._select(self._size_combo, self._index_in(protocol.STREAM_SIZES, tuple(server.stream_size)))
        self._select(self._fps_combo, self._index_in(protocol.FPS_CHOICES, server.stream_fps))
        self._select(self._bitrate_combo, self._index_in(protocol.BITRATE_CHOICES_KBPS, server.video_kbps))
        self._select(self._entropy_combo, self._index_in(protocol.ENTROPY_CODERS, server.entropy_coder))
        self._select(self._codec_combo, self._index_in(protocol.VIDEO_CODECS, getattr(server, "video_codec", "h264")))
        self._select(self._deblock_combo, self._index_in(protocol.NVENC_DEBLOCKING,
                                                         getattr(server, "nvenc_deblocking", "on")))
        self._select(self._motion_combo, self._index_in(protocol.NVENC_MOTION, getattr(server, "nvenc_motion", "quarter")))
        self._select(self._rate_combo, self._index_in(protocol.RATE_CONTROLS, server.rate_control))
        self._select(self._slice_combo, self._index_in(protocol.SLICE_COUNTS, server.slice_count))
        self._select(self._display_combo, self._index_in(DISPLAY_STRATEGIES, server.display_strategy))
        self._select(self._language_combo, self._index_in(LANGUAGE_CODES, language()))
        self._select(self._theme_combo, self._index_in(THEME_KINDS,
                                                       str(settings.get("theme", "system") or "system")))

        self._loss_row.set_hint(_(LOSS_RECOVERY_HINTS[self._loss_combo.currentIndex()]))
        self._size_row.set_hint(_(size_hints()[max(0, self._size_combo.currentIndex())]))
        self._entropy_row.set_hint(_(ENTROPY_HINTS[self._entropy_combo.currentIndex()]))
        self._codec_row.set_hint(_(CODEC_HINTS[max(0, self._codec_combo.currentIndex())]))
        # the two NVENC switches only exist with an ffmpeg that passes them on (the installer brings one);
        # with any other ffmpeg - or no NVIDIA card - the row says so and stays greyed out
        for row, combo, hints, missing, able in (
                (self._deblock_row, self._deblock_combo, DEBLOCK_HINTS, DEBLOCK_UNAVAILABLE_HINT, "nvenc_can_skip_deblocking"),
                (self._motion_row, self._motion_combo, MOTION_HINTS, MOTION_UNAVAILABLE_HINT, "nvenc_can_use_whole_pixels")):
            available, hint = nvenc_switch_hint(server, able, hints, combo.currentIndex(), missing)
            row.set_enabled(available)
            row.set_hint(_(hint))
        self._rate_row.set_hint(_(RATE_HINTS[self._rate_combo.currentIndex()]))
        self._slice_row.set_hint(_(SLICE_HINTS[self._slice_combo.currentIndex()]))
        self._display_row.set_hint(_(DISPLAY_HINTS[self._display_combo.currentIndex()]))

        # ONLY the encoder is locked while a stream runs, exactly as on Linux. Everything else is read
        # when the next stream STARTS, so changing it mid-stream is harmless - and greying it out was
        # wrong twice over: it took the settings away at the very moment somebody wants to try one, and
        # it made the window look like it could not be used at all.

        self._swap.blockSignals(True)
        self._swap.setChecked(bool(server.swap_mouse_sticks))
        self._swap.blockSignals(False)
        self._autostart.blockSignals(True)
        self._autostart.setChecked(autostart_windows.is_enabled())
        self._autostart.blockSignals(False)

        self._refresh_log()
        if self._confirm is not None and self._server.display_mode.is_confirmed:
            self._confirm.confirmed_elsewhere()
            self._confirm = None

    @staticmethod
    def _index_in(choices, value) -> int:
        try:
            return list(choices).index(value)
        except ValueError:
            return -1

    def _index_of_encoder(self) -> int:
        chosen = self._server.chosen_encoder
        for index, encoder in enumerate(self._server.available_encoders):
            if chosen is not None and encoder.kind == chosen.kind:
                return index
        return -1

    def _select(self, combo: QComboBox, index: int) -> None:
        if index < 0 or index == combo.currentIndex():
            return
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _refresh_log(self) -> None:
        """Only when something was actually written - log.py counts that for us, so an idle server costs
        nothing. The view follows the end unless the user has scrolled up to read something."""
        generation = log.generation()
        if generation == self._log_generation:
            return
        self._log_generation = generation
        bar = self._log_view.verticalScrollBar()
        was_at_end = bar.value() >= bar.maximum() - 4
        self._log_view.setPlainText(log.get_recent())   # log.py hands back the whole tail as one string
        if was_at_end:
            bar.setValue(bar.maximum())

    # ------------------------------------------------------------------------------ menu and lifetime
    def _open_log(self) -> None:
        if not os.path.exists(log.LOG_PATH):
            log.write(_("Log opened"))      # give the file something to be, or Windows opens nothing
        try:
            os.startfile(log.LOG_PATH)      # noqa: S606 - the OS decides what opens a .log
        except (AttributeError, OSError) as error:
            log.write(_("could not open the log: %s") % error)

    def _about(self) -> None:
        QMessageBox.about(self, _("About %s") % APP_NAME,
                          "<b>%s</b><br>%s %s<br><br>%s<br>%s<br><br>"
                          "<a href=\"%s\">%s</a><br><a href=\"%s\">%s</a><br><a href=\"%s\">%s</a>"
                          "<br><br>%s" % (
                              APP_NAME, _("Version"), __version__,
                              _("Streams the PC desktop to a PlayStation 3."),
                              _("Based on cell-stream-server %s") % UPSTREAM_VERSION,
                              URL_GITHUB, LINK_GITHUB, URL_HUB, LINK_HUB, URL_DONATE, LINK_DONATE,
                              _(DONATE_PITCH)))

    def _quit(self) -> None:
        self.save_pending_commands()
        if self._on_quit is not None:
            self._on_quit()

    def closeEvent(self, event) -> None:    # noqa: N802 - Qt's name
        """Closing the window leaves the server running - the same bargain as on Linux. Quitting is the
        tray icon or Ctrl+Q, and the hint under the settings says so."""
        self.save_pending_commands()
        off_language_changed(self._retranslate_all)
        self._timer.stop()
        super().closeEvent(event)

    # -------------------------------------------------------------------------- the resolution prompt
    def _show_confirm(self, seconds: int) -> None:
        if self._confirm is not None:
            return
        mode = self._server.display_mode
        self._confirm = ConfirmDialog(self, int(seconds) or CONFIRM_SECONDS,
                                      on_keep=mode.confirm_visible, on_revert=mode.reject_visible)
        self._confirm.finished.connect(lambda _result: setattr(self, "_confirm", None))
        self._confirm.show()
        self._confirm.raise_()
        self._confirm.activateWindow()

    # -------------------------------------------------------------------------------- the two languages
    def _retranslate_all(self) -> None:
        """Qt can relabel in place, so the language switch keeps the log, the scroll position and every
        half-typed command field - the GTK window throws both pages away and rebuilds them."""
        self._building = True
        try:
            self._tabs.setTabText(0, _("Server"))
            self._tabs.setTabText(1, _("Commands"))
            for relabel in self._retranslate:
                relabel()
            self._refresh()
        finally:
            self._building = False

    def _retranslate_video(self) -> None:
        self._encoder_row.title.setText(_("Encoder"))
        self._loss_row.title.setText(_("Error correction"))
        self._size_row.title.setText(_("Resolution"))
        self._fps_row.title.setText(_("Frame rate"))
        self._fps_row.set_hint(_(FPS_HINT))
        self._bitrate_row.title.setText(_("Bitrate"))
        self._bitrate_row.set_hint(_(BITRATE_HINT))
        self._entropy_row.title.setText(_("Entropy coding"))
        self._codec_row.title.setText(_("Codec"))
        self._deblock_row.title.setText(_("NVENC deblocking filter"))
        self._motion_row.title.setText(_("NVENC motion vectors"))
        self._relabel(self._codec_combo, [_(text) for text in CODEC_LABELS])
        self._relabel(self._deblock_combo, [_(text) for text in DEBLOCK_LABELS])
        self._relabel(self._motion_combo, [_(text) for text in MOTION_LABELS])
        self._rate_row.title.setText(_("Rate control"))
        self._slice_row.title.setText(_("Slices per picture (experiment)"))
        self._display_row.title.setText(_("The desktop while streaming"))
        self._relabel(self._loss_combo, [_(text) for text in LOSS_RECOVERY_LABELS])
        self._relabel(self._size_combo, size_labels())
        self._relabel(self._fps_combo, fps_labels())
        self._relabel(self._bitrate_combo, bitrate_labels())
        self._relabel(self._rate_combo, [_(text) for text in RATE_LABELS])
        self._relabel(self._slice_combo, [_(text) for text in SLICE_LABELS])
        self._relabel(self._display_combo, [_(text) for text in DISPLAY_LABELS])

    def _retranslate_system(self) -> None:
        self._language_row.title.setText(_("Language"))
        self._language_row.set_hint(_("The interface switches over at once – no restart"))
        self._theme_row.title.setText(_("Appearance"))
        self._theme_row.set_hint(_("Dark, light, or whatever Windows is set to"))
        self._autostart_row.title.setText(_("Start at login (minimised)"))
        self._autostart_row.set_hint(_("Puts a shortcut in the Startup folder"))
        self._relabel(self._theme_combo, [_(text) for text in THEME_LABELS])

    def _retranslate_commands(self) -> None:
        self._commands_intro.setText(_(COMMANDS_INTRO))
        for index, widgets in enumerate(self._slots, start=1):
            widgets["box"].setTitle(_("Command %d") % index)
            kind_row, value_row, name_row = widgets["rows"]
            kind_row.title.setText(_("Action"))
            value_row.title.setText(_("Command or URI"))
            name_row.title.setText(_("Name"))
            self._relabel(widgets["kind"], [_(text) for text in COMMAND_KIND_LABELS])

    def _retranslate_menu(self) -> None:
        self._program_menu.setTitle(_("Program"))
        self._help_menu.setTitle(_("Help"))
        self._open_log_action.setText(_("Open the log"))
        self._quit_action.setText(_("Quit"))
        self._about_action.setText(_("About %s") % APP_NAME)

    def _relabel(self, combo: QComboBox, labels) -> None:
        """New words, same choice: the index has to survive, or switching language changes a setting."""
        index = combo.currentIndex()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(list(labels))
        combo.setCurrentIndex(index)
        combo.blockSignals(False)
