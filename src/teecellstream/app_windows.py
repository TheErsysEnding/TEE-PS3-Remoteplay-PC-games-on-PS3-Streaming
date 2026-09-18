"""The Windows application: one Qt event loop, one window, one tray icon.

app.py does this with GTK and libadwaita and cannot run here at all. The shape is the same, though, and
deliberately so - the server is started first and lives on its own; the window is only a view, and
closing it leaves the server running. Quitting is the tray icon or Ctrl+Q, exactly as on Linux.
"""

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from . import APP_NAME, log
from .i18n import _, set_language
from .server import Server
from .settings import settings
from .ui_text import status_text
from .ui_windows import MainWindow, _dot

TRAY_TICK_MS = 1000
APP_USER_MODEL_ID = "TEE.PS3Remoteplay.Server.1"


def _icon() -> QIcon:
    """The program icon: the shipped .ico when there is one, otherwise the same dot the window draws."""
    here = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for candidate in (os.path.join(here, "tee-ps3-remote-player.ico"),
                      os.path.join(here, "windows", "tee-ps3-remote-player.ico")):
        if os.path.isfile(candidate):
            return QIcon(candidate)
    return QIcon(_dot("#2ecc71", 32))


def _tell_windows_who_we_are() -> None:
    """Without this the taskbar groups the window under "python" and shows python's icon - the frozen
    .exe is still a python process as far as the shell is concerned until it says otherwise."""
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except (AttributeError, OSError):
        pass


class TrayIcon(QSystemTrayIcon):
    """Show, open the log, quit - the same four entries as the Linux tray, minus the separator."""

    def __init__(self, window: MainWindow, server, on_quit):
        super().__init__(_icon(), window)
        self._window = window
        self._server = server
        self._last_tip = ""

        menu = QMenu()
        self._show_action = QAction(_("Show"), menu)
        self._show_action.triggered.connect(self._show_window)
        self._log_action = QAction(_("Open the log"), menu)
        self._log_action.triggered.connect(window._open_log)
        self._quit_action = QAction(_("Quit"), menu)
        self._quit_action.triggered.connect(on_quit)
        menu.addAction(self._show_action)
        menu.addAction(self._log_action)
        menu.addSeparator()
        menu.addAction(self._quit_action)
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(TRAY_TICK_MS)
        self._refresh()

    def _on_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self._show_window()

    def _show_window(self) -> None:
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()

    def _refresh(self) -> None:
        connected = bool(self._server.is_ps3_connected)
        self.setIcon(QIcon(_dot("#2ecc71" if connected else "#8a8a8a", 32)))
        tip = APP_NAME + " – " + status_text(self._server.is_armed, connected,
                                             self._server.connected_ps3 or "")
        if tip != self._last_tip:       # Windows redraws the balloon on every set, so only on a change
            self._last_tip = tip
            self.setToolTip(tip)
        self._show_action.setText(_("Show"))
        self._log_action.setText(_("Open the log"))
        self._quit_action.setText(_("Quit"))


def main(argv: list[str]) -> int:
    """Start the server, then show a window onto it. --minimized starts in the tray."""
    _tell_windows_who_we_are()
    QApplication.setDesktopSettingsAware(True)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(_icon())
    app.setQuitOnLastWindowClosed(False)    # closing the window must not end the server

    set_language(str(settings.get("language", "en") or "en"))

    server = Server()
    if not server.start():
        QMessageBox.critical(None, APP_NAME,
                             _("Another copy of the server is already running."))
        return 1
    server.install_exit_hooks()

    state = {"quitting": False}

    def quit_everything() -> None:
        if state["quitting"]:
            return
        state["quitting"] = True
        window.save_pending_commands()
        server.shutdown()
        app.quit()

    window = MainWindow(server, on_quit=quit_everything)
    tray = TrayIcon(window, server, quit_everything)
    tray.show()

    if "--minimized" in argv:
        log.write(_("started minimised - the icon in the notification area opens the window"))
    else:
        window.show()

    return app.exec()
