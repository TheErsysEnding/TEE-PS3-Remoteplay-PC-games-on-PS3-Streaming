"""The window: a view onto the server, nothing more (port of MainWindow.xaml.cs).

Closing it only hides it - the server keeps running, which is the point. Beenden (tray or menu) is the only
thing that stops it. The server is duck-typed: anything with the properties Server exposes will do (tests use a
mock), and the window never blocks on it - it polls every 500 ms like the original DispatcherTimer.
"""

import os
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import (APP_EXEC, APP_NAME, DONATE_HEADLINE, DONATE_PITCH, LINK_DONATE, LINK_GITHUB,  # noqa: E402
               LINK_HUB, DONATE_PITCH_SHORT, UPSTREAM_VERSION, URL_DONATE, URL_GITHUB, URL_HUB,
               __version__,
               autostart, custom_commands, display_mode, log, protocol)
from .i18n import _, add_translations, language, set_language, on_language_changed, off_language_changed  # noqa: E402
from .settings import settings  # noqa: E402

REFRESH_TICK_MS = 500
SLOT_SAVE_DELAY_MS = 400       # typing in a command field: save once the fingers pause, not per keystroke
WINDOW_WIDTH = 640
WINDOW_HEIGHT = 600
NARROW_BREAKPOINT = "max-width: 500sp"

from .ui_text import (BITRATE_HINT, FPS_HINT, status_text, COMMANDS_INTRO, COMMAND_KINDS, COMMAND_KIND_LABELS, DISPLAY_HINTS, DISPLAY_LABELS,
                      DEBLOCK_HINTS, DEBLOCK_LABELS, DEBLOCK_UNAVAILABLE_HINT,
                      MOTION_HINTS, MOTION_LABELS, MOTION_UNAVAILABLE_HINT, CODEC_HINTS, CODEC_LABELS, nvenc_switch_hint,
                      ENTROPY_HINTS, ENTROPY_LABELS, HIDE_HINT, LANGUAGE_CODES, LANGUAGE_LABELS, 
                      LOSS_RECOVERY_HINTS, LOSS_RECOVERY_KINDS, LOSS_RECOVERY_LABELS, RATE_HINTS, 
                      RATE_LABELS, SIZE_HINT_BY_SIZE, SLICE_HINTS, SLICE_LABELS, SOURCE_BAND, 
                      STATUS_CONNECTED, STATUS_STOPPED, STATUS_WAITING, bitrate_labels, fps_labels, 
                      size_hints, size_labels, source_rate_text)  # noqa: E402  - siehe ui_text: beide Fenster, ein Wortlaut



CSS = """
.status-card { padding: 18px; }
.status-dot { min-width: 12px; min-height: 12px; border-radius: 6px; margin: 2px; }
.status-dot-idle { background-color: #8a8a8a; }
.status-dot-live { background-color: #3dd56d; box-shadow: 0 0 6px alpha(#3dd56d, 0.7); }
.log-pane { border-top: 1px solid alpha(currentColor, 0.15); }
textview.log-view, textview.log-view > text {
  font-family: monospace; font-size: 12px; background-color: #1d1d20; color: #d6d6da;
}
"""

_css_installed = False


def dev_icon_dir() -> str:
    """data/icons of a source checkout (so the window and About get the icon before anything is installed)."""
    candidate = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "icons")
    return candidate if os.path.isdir(candidate) else ""


def install_style() -> None:
    """CSS for the whole display; Adw.StyleManager keeps following the system's light/dark choice."""
    global _css_installed
    display = Gdk.Display.get_default()
    if _css_installed or display is None:
        return
    _css_installed = True
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    Gtk.StyleContext.add_provider_for_display(display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    icon_dir = dev_icon_dir()
    if icon_dir:
        Gtk.IconTheme.get_for_display(display).add_search_path(icon_dir)
    Gtk.Window.set_default_icon_name(APP_EXEC)


def open_log(parent: Gtk.Window | None = None) -> None:
    """Hands the log file to whatever the desktop opens .log files with."""
    if not os.path.exists(log.LOG_PATH):
        log.write(_("Log opened"))   # creates the file, so there is something to show
    try:
        launcher = Gtk.FileLauncher.new(Gio.File.new_for_path(log.LOG_PATH))
        launcher.launch(parent, None, _on_log_launched)
    except (GLib.Error, AttributeError) as error:
        _open_log_fallback(str(error))


def _on_log_launched(launcher, result) -> None:
    try:
        launcher.launch_finish(result)
    except GLib.Error as error:
        _open_log_fallback(error.message)


def _open_log_fallback(reason: str) -> None:
    try:
        subprocess.Popen(["xdg-open", log.LOG_PATH], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError as error:
        log.write(_("could not open the log: %s / %s") % (reason, error))


class MainWindow(Adw.ApplicationWindow):
    """MainWindow(app, server). Public widgets are for the app and the tests; everything else is private."""

    def __init__(self, app: Gtk.Application, server):
        super().__init__(application=app, title=APP_NAME, default_width=WINDOW_WIDTH, default_height=WINDOW_HEIGHT,
                         icon_name=APP_EXEC)
        self._app = app
        self._server = server
        self._syncing = False               # True while widgets are being set from the server, so handlers stay quiet
        self._shown_log_generation = -1
        self._encoder_kinds: list[str] = []
        self._slot_save_timers: dict[int, int] = {}
        install_style()

        self._build()
        self._install_actions()
        self.connect("close-request", self._on_close_request)
        self.connect("destroy", self._on_destroy)
        self._timer_id = GLib.timeout_add(REFRESH_TICK_MS, self._on_tick)
        on_language_changed(self._apply_language)   # the switch relabels this window in place
        # a mode switch asks the user whether they can still see anything; without a window to ask in
        # (headless), display_mode simply does not arm the countdown and behaves as it always did
        display = getattr(self._server, "display_mode", None)
        if display is not None and hasattr(display, "set_confirm_prompt"):
            display.set_confirm_prompt(self._prompt_display_confirm)
        self.refresh()

    # ------------------------------------------------------------------ layout

    def _build(self) -> None:
        toolbar = Adw.ToolbarView()
        self.set_content(toolbar)

        self.view_stack = Adw.ViewStack()
        switcher = Adw.ViewSwitcher(stack=self.view_stack, policy=Adw.ViewSwitcherPolicy.WIDE)
        self._header = Adw.HeaderBar(title_widget=switcher)
        self._window_title = Adw.WindowTitle(title=APP_NAME)
        self._switcher = switcher
        self._menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", primary=True,
                                           tooltip_text=_("Main menu"), menu_model=self._build_menu())
        self._header.pack_end(self._menu_button)
        toolbar.add_top_bar(self._header)

        self.view_stack.add_titled_with_icon(self._build_server_page(), "server", _("Server"), "video-display-symbolic")
        self.view_stack.add_titled_with_icon(self._build_commands_page(), "commands", _("Commands"), "utilities-terminal-symbolic")
        toolbar.set_content(self.view_stack)

        # narrow window: the switcher moves from the header to a bar along the bottom
        self._switcher_bar = Adw.ViewSwitcherBar(stack=self.view_stack)
        toolbar.add_bottom_bar(self._switcher_bar)
        breakpoint = Adw.Breakpoint.new(Adw.BreakpointCondition.parse(NARROW_BREAKPOINT))
        breakpoint.connect("apply", self._on_narrow)
        breakpoint.connect("unapply", self._on_wide)
        self.add_breakpoint(breakpoint)

    def _on_narrow(self, _breakpoint) -> None:
        self._header.set_title_widget(self._window_title)
        self._switcher_bar.set_reveal(True)

    def _on_wide(self, _breakpoint) -> None:
        self._header.set_title_widget(self._switcher)
        self._switcher_bar.set_reveal(False)

    def _build_menu(self) -> Gio.Menu:
        menu = Gio.Menu()
        section = Gio.Menu()
        section.append(_("Open the log"), "win.open-log")
        section.append(_("Autostart"), "win.autostart")
        menu.append_section(None, section)
        section = Gio.Menu()
        section.append(_("About ") + APP_NAME, "win.about")
        section.append(_("Quit"), "app.quit")
        menu.append_section(None, section)
        return menu

    def _build_server_page(self) -> Gtk.Widget:
        # settings above, the running commentary below; the handle between them lets the log grow
        paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL, shrink_start_child=False, shrink_end_child=False,
                          resize_start_child=True, resize_end_child=False)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, vexpand=True)
        clamp = Adw.Clamp(maximum_size=760, tightening_threshold=560,
                          margin_top=24, margin_bottom=24, margin_start=18, margin_end=18)
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        clamp.set_child(column)
        scroller.set_child(clamp)

        column.append(self._build_status_card())
        column.append(self._build_video_group())
        column.append(self._build_input_group())
        column.append(self._build_system_group())

        paned.set_start_child(scroller)
        paned.set_end_child(self._build_log_pane())
        return paned

    def _build_status_card(self) -> Gtk.Widget:
        card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14, css_classes=["card", "status-card"])
        self.status_dot = Gtk.Box(css_classes=["status-dot", "status-dot-idle"], valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        card.append(self.status_dot)

        texts = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, hexpand=True, valign=Gtk.Align.CENTER)
        self.status_label = Gtk.Label(label=_(STATUS_WAITING), xalign=0, wrap=True, css_classes=["title-2"])
        self.subtitle_label = Gtk.Label(label="", xalign=0, wrap=True, css_classes=["dim-label"])
        texts.append(self.status_label)
        texts.append(self.subtitle_label)
        card.append(texts)

        self.start_stop_button = Gtk.Button(label=_("Stop"), valign=Gtk.Align.CENTER, css_classes=["pill", "destructive-action"])
        self.start_stop_button.connect("clicked", self._on_start_stop_clicked)
        card.append(self.start_stop_button)
        return card

    def _build_video_group(self) -> Gtk.Widget:
        group = Adw.PreferencesGroup(title=_("Video"))
        self.encoder_model = Gtk.StringList()
        self.encoder_row = Adw.ComboRow(title=_("Encoder"), subtitle=_("Locked while a PS3 is streaming"), model=self.encoder_model)
        self.encoder_row.connect("notify::selected", self._on_encoder_selected)
        group.add(self.encoder_row)

        self.recovery_row = Adw.ComboRow(title=_("Error correction"), subtitle=_("How the stream gets back to a clean picture after packet loss"),
                                         model=Gtk.StringList.new([_(text) for text in LOSS_RECOVERY_LABELS]))
        self.recovery_row.connect("notify::selected", self._on_recovery_selected)
        group.add(self.recovery_row)

        # The PS3's decoder, not the network, is the wall: measured 38-40 ms per frame at 11-13 Mbit/s CABAC
        # against the 16.7 ms a 60 fps frame gets, so the console dropped every other one. These two rows are
        # what buy that time back.
        self.size_row = Adw.ComboRow(title=_("Resolution"),
                                    subtitle=_("Bigger means more readable text, but costs the PS3 roughly proportionally more decode time"),
                                    model=Gtk.StringList.new(list(size_labels())))
        self.size_row.connect("notify::selected", self._on_size_selected)
        group.add(self.size_row)

        self.fps_row = Adw.ComboRow(title=_("Frame rate"),
                                    subtitle=_(FPS_HINT),
                                    model=Gtk.StringList.new(list(fps_labels())))
        self.fps_row.connect("notify::selected", self._on_fps_selected)
        group.add(self.fps_row)

        self.bitrate_row = Adw.ComboRow(title=_("Bitrate"),
                                        subtitle=_(BITRATE_HINT),
                                        model=Gtk.StringList.new(list(bitrate_labels())))
        self.bitrate_row.connect("notify::selected", self._on_bitrate_selected)
        group.add(self.bitrate_row)

        self.codec_row = Adw.ComboRow(title=_("Codec"),
                                      model=Gtk.StringList.new([_(text) for text in CODEC_LABELS]))
        self.codec_row.connect("notify::selected", self._on_codec_selected)
        group.add(self.codec_row)

        self.coder_row = Adw.ComboRow(title=_("Entropy coding"),
                                      subtitle=_("The PS3 decodes CAVLC about 43 % faster – CABAC only while the picture stays fluid"),
                                      model=Gtk.StringList.new([_(text) for text in ENTROPY_LABELS]))
        self.coder_row.connect("notify::selected", self._on_coder_selected)
        group.add(self.coder_row)

        self.deblock_row = Adw.ComboRow(title=_("NVENC deblocking filter"),
                                        model=Gtk.StringList.new([_(text) for text in DEBLOCK_LABELS]))
        self.deblock_row.connect("notify::selected", self._on_deblock_selected)
        group.add(self.deblock_row)

        self.motion_row = Adw.ComboRow(title=_("NVENC motion vectors"),
                                       model=Gtk.StringList.new([_(text) for text in MOTION_LABELS]))
        self.motion_row.connect("notify::selected", self._on_motion_selected)
        group.add(self.motion_row)

        self.rate_row = Adw.ComboRow(title=_("Rate control"),
                                     subtitle=_("What the encoder spends its bitrate on – only the x264 encoder can do all three"),
                                     model=Gtk.StringList.new([_(text) for text in RATE_LABELS]))
        self.rate_row.connect("notify::selected", self._on_rate_selected)
        group.add(self.rate_row)

        self.slice_row = Adw.ComboRow(title=_("Slices per picture (experiment)"),
                                      model=Gtk.StringList.new([_(text) for text in SLICE_LABELS]))
        self.slice_row.connect("notify::selected", self._on_slice_selected)
        group.add(self.slice_row)

        self.display_row = Adw.ComboRow(title=_("The desktop while streaming"),
                                        model=Gtk.StringList.new([_(text) for text in DISPLAY_LABELS]))
        self.display_row.connect("notify::selected", self._on_display_selected)
        group.add(self.display_row)
        return group

    def _build_input_group(self) -> Gtk.Widget:
        group = Adw.PreferencesGroup(title=_("Input"))
        self.swap_sticks_row = Adw.SwitchRow(title=_("Swap the sticks in mouse mode"), subtitle=_("The right stick moves the pointer"))
        self.swap_sticks_row.connect("notify::active", self._on_swap_sticks_toggled)
        group.add(self.swap_sticks_row)
        return group

    def _build_system_group(self) -> Gtk.Widget:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        group = Adw.PreferencesGroup(title=_("System"))
        self.language_row = Adw.ComboRow(title=_("Language"),
                                         subtitle=_("The interface switches over at once – no restart"),
                                         model=Gtk.StringList.new(list(LANGUAGE_LABELS)))
        self.language_row.set_selected(LANGUAGE_CODES.index(language()) if language() in LANGUAGE_CODES else 0)
        self.language_row.connect("notify::selected", self._on_language_selected)
        group.add(self.language_row)
        self.autostart_row = Adw.SwitchRow(title=_("Start at login (minimised)"), subtitle=_("Creates an autostart entry"))
        self.autostart_row.connect("notify::active", self._on_autostart_row_toggled)
        group.add(self.autostart_row)
        box.append(group)
        hint = Gtk.Label(label=_(HIDE_HINT), xalign=0, wrap=True, css_classes=["dim-label", "caption"])
        box.append(hint)
        box.append(self._build_support_group())
        return box

    def _build_support_group(self) -> Gtk.Widget:
        """The three links, clickable, in the window itself rather than in an About box.

        An About box is where a link goes to be seen once. The donation one pays for the server this
        project is built and hosted on, and a single euro covers a month of it - worth saying where
        somebody actually looks."""
        group = Adw.PreferencesGroup(title=_(DONATE_HEADLINE), description=_(DONATE_PITCH),
                                     margin_top=12)
        for title, link, url in ((_("Donate"), LINK_DONATE, URL_DONATE),
                                 (_("All my projects"), LINK_HUB, URL_HUB),
                                 (_("Source code"), LINK_GITHUB, URL_GITHUB)):
            row = Adw.ActionRow(title=title, subtitle=link, activatable=True)
            # the whole row opens it - a link the size of a row beats a link the size of a word on a
            # screen somebody is looking at from the other side of the desk
            row.connect("activated", self._open_link, url)
            row.add_suffix(Gtk.Image(icon_name="adw-external-link-symbolic"))
            group.add(row)
        return group

    def _open_link(self, _row, url: str) -> None:
        Gtk.UriLauncher(uri=url).launch(self, None, None)

    def _build_log_pane(self) -> Gtk.Widget:
        pane = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, css_classes=["log-pane"])
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6, margin_start=18, margin_end=10, margin_top=6, margin_bottom=4)
        header.append(Gtk.Label(label=_("Log"), xalign=0, hexpand=True, css_classes=["heading"]))
        open_button = Gtk.Button(label=_("Open the log"), css_classes=["flat"], action_name="win.open-log", tooltip_text=_("Ctrl+L"))
        header.append(open_button)
        pane.append(header)

        scroller = Gtk.ScrolledWindow(min_content_height=150, vexpand=True)
        self.log_view = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, css_classes=["log-view"],
                                     left_margin=10, right_margin=10, top_margin=6, bottom_margin=6)
        self._log_end_mark = self.log_view.get_buffer().create_mark(None, self.log_view.get_buffer().get_end_iter(), False)
        scroller.set_child(self.log_view)
        pane.append(scroller)
        return pane

    def _build_commands_page(self) -> Gtk.Widget:
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        clamp = Adw.Clamp(maximum_size=760, tightening_threshold=560,
                          margin_top=24, margin_bottom=24, margin_start=18, margin_end=18)
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        clamp.set_child(column)
        scroller.set_child(clamp)
        column.append(Gtk.Label(label=_(COMMANDS_INTRO), xalign=0, wrap=True, css_classes=["dim-label"]))

        self.slot_rows: list[tuple[Adw.ComboRow, Adw.EntryRow, Adw.EntryRow]] = []
        for slot in range(1, custom_commands.SLOT_COUNT + 1):
            command = custom_commands.get(slot) or {}
            group = Adw.PreferencesGroup(title=_("Command %d") % slot)
            kind_row = Adw.ComboRow(title=_("Action"), model=Gtk.StringList.new([_(text) for text in COMMAND_KIND_LABELS]))
            kind = command.get("kind", "none")
            kind_row.set_selected(COMMAND_KINDS.index(kind) if kind in COMMAND_KINDS else 0)
            value_row = Adw.EntryRow(title=_("Command or URI"), text=command.get("value", "") or "")
            label_row = Adw.EntryRow(title=_("Name"), text=command.get("label", "") or "")
            value_row.set_sensitive(kind == "run")   # only Run needs a command; None leaves the field disabled
            kind_row.connect("notify::selected", self._on_slot_kind_changed, slot)
            value_row.connect("changed", self._on_slot_text_changed, slot)
            label_row.connect("changed", self._on_slot_text_changed, slot)
            group.add(kind_row)
            group.add(value_row)
            group.add(label_row)
            column.append(group)
            self.slot_rows.append((kind_row, value_row, label_row))
        return scroller

    # ------------------------------------------------------------------ actions and shortcuts

    def _install_actions(self) -> None:
        action = Gio.SimpleAction.new("open-log", None)
        action.connect("activate", lambda *_: open_log(self))
        self.add_action(action)

        action = Gio.SimpleAction.new("about", None)
        action.connect("activate", lambda *_: self.show_about())
        self.add_action(action)

        self._autostart_action = Gio.SimpleAction.new_stateful("autostart", None, GLib.Variant.new_boolean(autostart.is_enabled()))
        self._autostart_action.connect("change-state", self._on_autostart_change_state)
        self.add_action(self._autostart_action)
        self._set_quietly(self.autostart_row.set_active, autostart.is_enabled())

        if self._app.lookup_action("quit") is None:   # the real app brings its own (it stops the server first)
            action = Gio.SimpleAction.new("quit", None)
            action.connect("activate", self._on_fallback_quit)
            self._app.add_action(action)
        self._app.set_accels_for_action("app.quit", ["<Control>q"])
        self._app.set_accels_for_action("win.open-log", ["<Control>l"])

    def _on_fallback_quit(self, *_args) -> None:
        try:
            self._server.shutdown()
        finally:
            self._app.quit()

    def show_about(self) -> Adw.AboutDialog:
        about = Adw.AboutDialog(application_name=APP_NAME, application_icon=APP_EXEC, version=__version__,
                                developer_name="TEE", license_type=Gtk.License.APACHE_2_0, copyright="© 2026 TEE",
                                website=URL_GITHUB, issue_url=URL_GITHUB + "/issues",
                                comments=("Streams the PC desktop to a PS3 running the cell-stream app and plays "
                                          "its controller back on the PC.\n\nLinux port of cell-stream-server "
                                          "(ps3-dev, Release %s)." % UPSTREAM_VERSION))
        # Adw puts these under "Details", which is where somebody goes looking for them
        about.add_link(_("Donate") + " – " + _(DONATE_PITCH_SHORT), URL_DONATE)
        about.add_link(_("All my projects"), URL_HUB)
        about.present(self)
        return about

    # ------------------------------------------------------------------ handlers

    def _on_start_stop_clicked(self, _button) -> None:
        if self._server.is_armed:
            self._server.disarm("stopped by you")
        else:
            self._server.arm()
        self.refresh()

    # the encoder cannot change under a live stream, so put the selection back if one starts between the
    # dropdown being enabled and the choice being made
    def _on_encoder_selected(self, row, _pspec) -> None:
        if self._syncing:
            return
        encoders = list(self._server.available_encoders)
        index = row.get_selected()
        if index < 0 or index >= len(encoders):
            return
        chosen = encoders[index]
        if chosen is self._server.chosen_encoder:
            return
        if self._server.is_ps3_connected:
            log.write(_("encoders: end the stream first, then change the encoder"))
            self._sync_choices()
            return
        self._server.chosen_encoder = chosen

    def _on_recovery_selected(self, row, _pspec) -> None:
        if self._syncing:
            return
        index = row.get_selected()
        if index < 0 or index >= len(LOSS_RECOVERY_KINDS) or LOSS_RECOVERY_KINDS[index] == self._server.loss_recovery:
            return
        if self._server.is_ps3_connected:
            log.write(_("video: end the stream first, then change the error correction"))
            self._sync_choices()
            return
        self._server.loss_recovery = LOSS_RECOVERY_KINDS[index]

    def _on_fps_selected(self, row, _pspec) -> None:
        if self._syncing:
            return
        index = row.get_selected()
        if index < 0 or index >= len(protocol.FPS_CHOICES):
            return
        if protocol.FPS_CHOICES[index] == self._server.stream_fps:
            return
        if self._server.is_ps3_connected:
            log.write(_("video: end the stream first, then change the frame rate"))
            self._sync_choices()
            return
        self._server.stream_fps = protocol.FPS_CHOICES[index]

    def _on_bitrate_selected(self, row, _pspec) -> None:
        if self._syncing:
            return
        index = row.get_selected()
        if index < 0 or index >= len(protocol.BITRATE_CHOICES_KBPS):
            return
        if protocol.BITRATE_CHOICES_KBPS[index] == self._server.video_kbps:
            return
        if self._server.is_ps3_connected:
            log.write(_("video: end the stream first, then change the bitrate"))
            self._sync_choices()
            return
        self._server.video_kbps = protocol.BITRATE_CHOICES_KBPS[index]

    def _on_size_selected(self, row, _pspec) -> None:
        if self._syncing:
            return
        index = row.get_selected()
        if index < 0 or index >= len(protocol.STREAM_SIZES) or protocol.STREAM_SIZES[index] == self._server.stream_size:
            return
        if self._server.is_ps3_connected:
            log.write(_("video: end the stream first, then change the resolution"))
            self._sync_choices()
            return
        self._server.stream_size = protocol.STREAM_SIZES[index]

    def _on_coder_selected(self, row, _pspec) -> None:
        if self._syncing:
            return
        index = row.get_selected()
        if index < 0 or index >= len(protocol.ENTROPY_CODERS) or protocol.ENTROPY_CODERS[index] == self._server.entropy_coder:
            return
        if self._server.is_ps3_connected:
            log.write(_("video: end the stream first, then change the entropy coder"))
            self._sync_choices()
            return
        self._server.entropy_coder = protocol.ENTROPY_CODERS[index]

    def _on_codec_selected(self, row, _pspec) -> None:
        if self._syncing:
            return
        index = row.get_selected()
        if index < 0 or index >= len(protocol.VIDEO_CODECS) or protocol.VIDEO_CODECS[index] == self._server.video_codec:
            return
        if self._server.is_ps3_connected:
            log.write(_("video: end the stream first, then change the codec"))
            self._sync_choices()
            return
        self._server.video_codec = protocol.VIDEO_CODECS[index]

    def _on_deblock_selected(self, row, _pspec) -> None:
        if self._syncing:
            return
        index = row.get_selected()
        if index < 0 or index >= len(protocol.NVENC_DEBLOCKING) or protocol.NVENC_DEBLOCKING[index] == self._server.nvenc_deblocking:
            return
        if self._server.is_ps3_connected:
            log.write(_("video: end the stream first, then change the deblocking filter"))
            self._sync_choices()
            return
        self._server.nvenc_deblocking = protocol.NVENC_DEBLOCKING[index]

    def _on_motion_selected(self, row, _pspec) -> None:
        if self._syncing:
            return
        index = row.get_selected()
        if index < 0 or index >= len(protocol.NVENC_MOTION) or protocol.NVENC_MOTION[index] == self._server.nvenc_motion:
            return
        if self._server.is_ps3_connected:
            log.write(_("video: end the stream first, then change the motion vectors"))
            self._sync_choices()
            return
        self._server.nvenc_motion = protocol.NVENC_MOTION[index]

    def _on_language_selected(self, row, _pspec) -> None:
        if self._syncing:
            return
        index = row.get_selected()
        if not (0 <= index < len(LANGUAGE_CODES)):
            return
        settings.set("language", LANGUAGE_CODES[index])
        set_language(LANGUAGE_CODES[index])     # calls _apply_language through the listener

    def _apply_language(self) -> None:
        """Relabel the whole window in place. The two pages are thrown away and built again rather than
        walked widget by widget: every label then comes from the same code that created it in the first
        place, so a new row cannot be forgotten here later. Everything the pages show is either read back
        from the server (_sync_choices) or from the settings file, so nothing is lost - except an unsaved
        keystroke in a command field, which is why the pending saves are flushed first."""
        for slot, timer in list(self._slot_save_timers.items()):
            GLib.source_remove(timer)
            self._slot_save_timers.pop(slot, None)
            self._on_slot_save_due(slot)
        visible = self.view_stack.get_visible_child_name() or "server"
        for name in ("server", "commands"):
            child = self.view_stack.get_child_by_name(name)
            if child is not None:
                self.view_stack.remove(child)
        self.view_stack.add_titled_with_icon(self._build_server_page(), "server", _("Server"),
                                             "video-display-symbolic")
        self.view_stack.add_titled_with_icon(self._build_commands_page(), "commands", _("Commands"),
                                             "utilities-terminal-symbolic")
        self.view_stack.set_visible_child_name(visible)
        self._menu_button.set_menu_model(self._build_menu())
        self._menu_button.set_tooltip_text(_("Main menu"))
        self._shown_log_generation = None    # the new log view is empty; force one refresh into it
        self._sync_choices()
        self.refresh()
        self._refresh_log()

    def _sync_hints(self) -> None:
        """Each combo row explains its CURRENT choice underneath itself. The dropdown holds short names
        because GTK ellipsises a long selected value at any window size - the sentence goes here, where
        it always fits."""
        for row, hints in ((self.size_row, size_hints()), (self.codec_row, CODEC_HINTS), (self.coder_row, ENTROPY_HINTS),
                           (self.rate_row, RATE_HINTS), (self.recovery_row, LOSS_RECOVERY_HINTS),
                           (self.slice_row, SLICE_HINTS),
                           (self.display_row, DISPLAY_HINTS)):
            index = row.get_selected()
            if 0 <= index < len(hints) and row.get_subtitle() != _(hints[index]):
                row.set_subtitle(_(hints[index]))
        # the filter switch only exists with an ffmpeg that can pass it on; with any other the row says so
        # and stays greyed out rather than offering a choice that would change nothing
        # (and only on a PC with an NVIDIA encoder: the bundled ffmpeg knows the options on every machine)
        for row, able, hints, missing in ((self.deblock_row, "nvenc_can_skip_deblocking", DEBLOCK_HINTS, DEBLOCK_UNAVAILABLE_HINT),
                                          (self.motion_row, "nvenc_can_use_whole_pixels", MOTION_HINTS, MOTION_UNAVAILABLE_HINT)):
            available, hint = nvenc_switch_hint(self._server, able, hints, row.get_selected(), missing)
            row.set_sensitive(available)
            if row.get_subtitle() != _(hint):
                row.set_subtitle(_(hint))

    def _on_rate_selected(self, row, _pspec) -> None:
        if self._syncing:
            return
        index = row.get_selected()
        if index < 0 or index >= len(protocol.RATE_CONTROLS) or protocol.RATE_CONTROLS[index] == self._server.rate_control:
            return
        if self._server.is_ps3_connected:
            log.write(_("video: end the stream first, then change the rate control"))
            self._sync_choices()
            return
        self._server.rate_control = protocol.RATE_CONTROLS[index]

    def _on_slice_selected(self, row, _pspec) -> None:
        if self._syncing:
            return
        index = row.get_selected()
        if index < 0 or index >= len(protocol.SLICE_COUNTS) or protocol.SLICE_COUNTS[index] == self._server.slice_count:
            return
        if self._server.is_ps3_connected:
            log.write(_("video: end the stream first, then change the slice count"))
            self._sync_choices()
            return
        self._server.slice_count = protocol.SLICE_COUNTS[index]

    # --- the "can you still see this?" safety net ------------------------------------------------
    # A monitor can accept a mode and show nothing at all. The user is then staring at a black desktop
    # with no way to click anything, which is why the countdown - not the button - is what actually saves
    # them: display_mode reverts on its own unless someone confirms. This dialog just makes the good case
    # quick, and gives an immediate way out for the case where the picture is there but wrong.
    def _prompt_display_confirm(self, seconds: int) -> None:
        """Called from display_mode's worker thread: hand it straight to the GTK loop and return."""
        GLib.idle_add(self._show_display_confirm, seconds)

    def _show_display_confirm(self, seconds: int):
        display = self._server.display_mode
        dialog = Adw.AlertDialog(heading=_("Can you see this window?"),
                                 body=self._confirm_body(seconds))
        dialog.add_response("no", _("No, switch back"))
        dialog.add_response("yes", _("Yes, keep it"))
        dialog.set_response_appearance("yes", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_response_appearance("no", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("yes")
        dialog.set_close_response("no")

        left = {"seconds": seconds, "done": False, "expired": False}

        def tick():
            if left["done"]:
                return GLib.SOURCE_REMOVE
            # answered somewhere else - by the user, or by the console proving it is receiving. Close
            # without answering: this dialog no longer has anything to decide.
            if display.is_confirmed:
                left["done"] = left["expired"] = True
                dialog.close()
                return GLib.SOURCE_REMOVE
            left["seconds"] -= 1
            if left["seconds"] <= 0:
                left["done"] = left["expired"] = True
                dialog.close()      # display_mode is switching back on its own; just get out of the way
                return GLib.SOURCE_REMOVE
            dialog.set_body(self._confirm_body(left["seconds"]))
            return GLib.SOURCE_CONTINUE

        def answered(_dialog, response):
            # close_response is "no", so a dialog that closes ITSELF arrives here as a rejection. It is
            # not one: nobody said no. Left unguarded this switched the desktop back a second time, and
            # did it silently - in the log the mode simply went back with no reason given.
            if left["expired"]:
                return
            left["done"] = True
            if response == "yes":
                display.confirm_visible()
                log.write(_("display: picture confirmed, the new resolution stays"))
            else:
                display.reject_visible()

        dialog.connect("response", answered)
        GLib.timeout_add_seconds(1, tick)
        dialog.present(self)
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _confirm_body(seconds: int) -> str:
        return _("The desktop was switched for the stream.\n\n"
                 "If you can read this, everything is fine. With no answer it switches back to the previous "
                 "resolution automatically in %d seconds.") % seconds

    def _on_display_selected(self, row, _pspec) -> None:
        if self._syncing:
            return
        index = row.get_selected()
        if 0 <= index < len(display_mode.DISPLAY_STRATEGIES):
            self._server.display_strategy = display_mode.DISPLAY_STRATEGIES[index]

    def _on_swap_sticks_toggled(self, row, _pspec) -> None:
        if not self._syncing:
            self._server.swap_mouse_sticks = row.get_active()

    def _on_autostart_row_toggled(self, row, _pspec) -> None:
        if not self._syncing:
            self._autostart_action.change_state(GLib.Variant.new_boolean(row.get_active()))

    def _on_autostart_change_state(self, action, value) -> None:
        wanted = value.get_boolean()
        if autostart.is_enabled() != wanted:
            autostart.set_enabled(wanted)
        actual = autostart.is_enabled()   # the file system has the last word
        action.set_state(GLib.Variant.new_boolean(actual))
        self._set_quietly(self.autostart_row.set_active, actual)

    def _on_slot_kind_changed(self, kind_row, _pspec, slot: int) -> None:
        _kind, value_row, _label = self.slot_rows[slot - 1]
        value_row.set_sensitive(kind_row.get_selected() == COMMAND_KINDS.index("run"))
        self._save_slot(slot)

    def _on_slot_text_changed(self, _row, slot: int) -> None:
        if slot in self._slot_save_timers:
            GLib.source_remove(self._slot_save_timers[slot])
        self._slot_save_timers[slot] = GLib.timeout_add(SLOT_SAVE_DELAY_MS, self._on_slot_save_due, slot)

    def _on_slot_save_due(self, slot: int) -> bool:
        self._slot_save_timers.pop(slot, None)
        self._save_slot(slot)
        return GLib.SOURCE_REMOVE

    def _save_slot(self, slot: int) -> None:
        kind_row, value_row, label_row = self.slot_rows[slot - 1]
        index = kind_row.get_selected()
        custom_commands.set(slot, {
            "kind": COMMAND_KINDS[index] if 0 <= index < len(COMMAND_KINDS) else "none",
            "value": value_row.get_text() or "",
            "label": label_row.get_text() or "",
        })

    # the X button hides us; only Beenden really exits
    def _on_close_request(self, _window) -> bool:
        try:
            self.hide_to_tray()
        except Exception as error:   # noqa: BLE001 - an exception here would return FALSE and destroy the window
            log.write(_("window: could not go to the background: %s") % error)
            self.set_visible(False)
        return True

    def _on_destroy(self, _widget) -> None:
        self.shut_down()   # belt and braces: measured not to arrive at all (see shut_down), but harmless twice

    def flush_pending_saves(self) -> None:
        """A Befehle field saves 400 ms after the last keystroke; whatever is still inside that pause goes now."""
        for slot, timer in list(self._slot_save_timers.items()):
            GLib.source_remove(timer)
            self._slot_save_timers.pop(slot, None)
            try:
                self._save_slot(slot)
            except Exception as error:   # noqa: BLE001 - a failed save must not stop the shutdown around it
                log.write(_("command %d could not be saved: %s") % (slot, error))

    def shut_down(self) -> None:
        """Give back what the window owns, while its widgets are still readable. The app calls this before it
        quits, because the destroy signal does not get here: measured on GTK 4.22.4 / PyGObject 3.56, a handler
        connected on a Python subclass of Adw.ApplicationWindow never runs, so the 500 ms timer would keep
        ticking on a destroyed window (3 ticks in 1.5 s after destroy()) for the life of the process."""
        self.flush_pending_saves()
        # the language listener holds this window by a bound method, so leaving it registered keeps a
        # destroyed window - and through it the application - alive for ever. It belongs HERE and not in
        # the destroy handler for the same reason the timer does: that handler never runs.
        off_language_changed(self._apply_language)
        if self._timer_id:
            GLib.source_remove(self._timer_id)
            self._timer_id = 0

    # ------------------------------------------------------------------ show / hide

    def hide_to_tray(self) -> None:
        self.flush_pending_saves()   # closing the window is the moment the user is done typing in Befehle
        self.set_visible(False)
        if not settings.get("hide_notice_shown", False):
            settings.set("hide_notice_shown", True)
            self._send_notification("hidden", _("Still running in the background"),
                                    _("The server is still waiting for the PS3. Quit from the tray icon or the menu."))

    def present_from_tray(self, activation_token: str | None = None) -> None:
        # a fresh map gets the focus on its own; a window already on screen is only raised when we hand the
        # compositor the token the click produced (GTK spends it on the next present)
        if activation_token:
            self.set_startup_id(activation_token)
        self.set_visible(True)
        self.unminimize()
        self.present()

    def _send_notification(self, ident: str, title: str, body: str) -> None:
        if not self._app.get_is_registered():
            return
        notification = Gio.Notification.new(title)
        notification.set_body(body)
        notification.set_icon(Gio.ThemedIcon.new(APP_EXEC))
        self._app.send_notification(ident, notification)

    # ------------------------------------------------------------------ refresh

    def _on_tick(self) -> bool:
        try:
            self.refresh()
        except Exception as error:   # noqa: BLE001 - a display glitch must not stop the timer for good
            log.write(_("window: refresh failed: %s") % error)
        return GLib.SOURCE_CONTINUE

    def refresh(self) -> None:
        """Grey until a PS3 turns up, green while it is streaming; the button and the locks follow the server."""
        server = self._server
        connected = bool(server.is_ps3_connected)
        armed = bool(server.is_armed)
        who = server.connected_ps3 or ""
        status = status_text(armed, connected, who)
        if self.status_label.get_text() != status:
            self.status_label.set_text(status)

        subtitle = server.settings_summary if (armed or server.trip_reason is None) else server.trip_reason
        if connected:
            subtitle += source_rate_text(server.captured_fps, int(server.stream_fps))
        if self.subtitle_label.get_text() != subtitle:
            self.subtitle_label.set_text(subtitle)

        self._set_dot(connected)
        self._set_button(armed)

        self._sync_choices()
        locked = connected   # don't let the encoder change out from under a live stream
        self.encoder_row.set_sensitive(not locked and len(self._encoder_kinds) > 0)
        self.recovery_row.set_sensitive(not locked)
        self.size_row.set_sensitive(not locked)
        self.fps_row.set_sensitive(not locked)
        self.bitrate_row.set_sensitive(not locked)
        self.coder_row.set_sensitive(not locked)

        if self.get_visible():
            self._refresh_log()

    def _set_dot(self, live: bool) -> None:
        wanted, other = ("status-dot-live", "status-dot-idle") if live else ("status-dot-idle", "status-dot-live")
        if not self.status_dot.has_css_class(wanted):
            self.status_dot.remove_css_class(other)
            self.status_dot.add_css_class(wanted)

    def _set_button(self, armed: bool) -> None:
        label, wanted, other = ("Stop", "destructive-action", "suggested-action") if armed else ("Start", "suggested-action", "destructive-action")
        if self.start_stop_button.get_label() != label:
            self.start_stop_button.set_label(label)
        if not self.start_stop_button.has_css_class(wanted):
            self.start_stop_button.remove_css_class(other)
            self.start_stop_button.add_css_class(wanted)

    def _set_quietly(self, setter, value) -> None:
        """Move a widget without its handler answering; the flag is restored, never just cleared, so a nested
        call cannot unmute the sync that is still running around it."""
        was_syncing = self._syncing
        self._syncing = True
        try:
            setter(value)
        finally:
            self._syncing = was_syncing

    def _sync_choices(self) -> None:
        """Widgets follow the server (the model is rebuilt only when the encoder list itself changes)."""
        server = self._server
        was_syncing = self._syncing
        self._syncing = True
        try:
            encoders = list(server.available_encoders)
            kinds = [encoder.kind for encoder in encoders]
            if kinds != self._encoder_kinds:
                self._encoder_kinds = kinds
                self.encoder_model.splice(0, self.encoder_model.get_n_items(), [encoder.name for encoder in encoders])
                self.encoder_row.set_subtitle("Locked while a PS3 is streaming" if encoders else "No H.264 encoder found")
            chosen = server.chosen_encoder
            if chosen is not None and chosen in encoders:
                index = encoders.index(chosen)
                if self.encoder_row.get_selected() != index:
                    self.encoder_row.set_selected(index)

            recovery = server.loss_recovery
            index = LOSS_RECOVERY_KINDS.index(recovery) if recovery in LOSS_RECOVERY_KINDS else 0
            if self.recovery_row.get_selected() != index:
                self.recovery_row.set_selected(index)

            size = tuple(server.stream_size)
            index = protocol.STREAM_SIZES.index(size) if size in protocol.STREAM_SIZES else 0
            if self.size_row.get_selected() != index:
                self.size_row.set_selected(index)

            fps = server.stream_fps
            index = protocol.FPS_CHOICES.index(fps) if fps in protocol.FPS_CHOICES else len(protocol.FPS_CHOICES) - 1
            if self.fps_row.get_selected() != index:
                self.fps_row.set_selected(index)

            kbps = server.video_kbps
            index = protocol.BITRATE_CHOICES_KBPS.index(kbps) if kbps in protocol.BITRATE_CHOICES_KBPS else 0
            if self.bitrate_row.get_selected() != index:
                self.bitrate_row.set_selected(index)

            coder = server.entropy_coder
            index = protocol.ENTROPY_CODERS.index(coder) if coder in protocol.ENTROPY_CODERS else 0
            if self.coder_row.get_selected() != index:
                self.coder_row.set_selected(index)

            rate = getattr(server, "rate_control", "quality")
            index = protocol.RATE_CONTROLS.index(rate) if rate in protocol.RATE_CONTROLS else 0
            if self.rate_row.get_selected() != index:
                self.rate_row.set_selected(index)

            index = LANGUAGE_CODES.index(language()) if language() in LANGUAGE_CODES else 0
            if self.language_row.get_selected() != index:
                self.language_row.set_selected(index)

            slices = getattr(server, "slice_count", 1)
            index = protocol.SLICE_COUNTS.index(slices) if slices in protocol.SLICE_COUNTS else 0
            if self.slice_row.get_selected() != index:
                self.slice_row.set_selected(index)

            codec = getattr(server, "video_codec", "h264")
            index = protocol.VIDEO_CODECS.index(codec) if codec in protocol.VIDEO_CODECS else 0
            if self.codec_row.get_selected() != index:
                self.codec_row.set_selected(index)

            deblocking = getattr(server, "nvenc_deblocking", "on")
            index = protocol.NVENC_DEBLOCKING.index(deblocking) if deblocking in protocol.NVENC_DEBLOCKING else 0
            if self.deblock_row.get_selected() != index:
                self.deblock_row.set_selected(index)

            motion = getattr(server, "nvenc_motion", "quarter")
            index = protocol.NVENC_MOTION.index(motion) if motion in protocol.NVENC_MOTION else 0
            if self.motion_row.get_selected() != index:
                self.motion_row.set_selected(index)

            self._sync_hints()

            strategy = getattr(server, "display_strategy", "capture")
            index = (display_mode.DISPLAY_STRATEGIES.index(strategy)
                     if strategy in display_mode.DISPLAY_STRATEGIES else 1)
            if self.display_row.get_selected() != index:
                self.display_row.set_selected(index)
            if self.swap_sticks_row.get_active() != bool(server.swap_mouse_sticks):
                self.swap_sticks_row.set_active(bool(server.swap_mouse_sticks))
        finally:
            self._syncing = was_syncing

    def _refresh_log(self) -> None:
        generation = log.generation()
        if generation == self._shown_log_generation:
            return
        self._shown_log_generation = generation
        buffer = self.log_view.get_buffer()
        buffer.set_text(log.get_recent())
        self.log_view.scroll_to_mark(self._log_end_mark, 0.0, True, 0.0, 1.0)
