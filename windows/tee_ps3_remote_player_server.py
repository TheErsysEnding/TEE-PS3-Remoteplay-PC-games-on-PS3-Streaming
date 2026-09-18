"""What "TEE PS3 Remote Player server.exe" runs.

Three things this does that `python -m teecellstream` does not:

- It opens the Qt window (app_windows.py), not the GTK one. `python -m teecellstream` without
  --headless imports app.py, which is PyGObject and cannot exist here; the window that CAN exist here
  is the Qt twin, and this is what knows to ask for it. --headless still runs with no window at all.
- It keeps its console. Double-clicked, the program's whole output is that window, so a message like
  "ffmpeg not found" has to stay readable instead of vanishing with the process.
- It puts the settings and the log where Windows programs put them (%APPDATA% / %LOCALAPPDATA%) rather
  than in ~/.config, which is where the Linux defaults would land them.
"""

import os
import sys
import traceback

APP_FOLDER = "TEE PS3 Remoteplay"


def _windows_paths() -> None:
    """Settings and log under %APPDATA% and %LOCALAPPDATA%. Set BEFORE teecellstream is imported: both
    modules work their paths out at import time."""
    roaming = os.environ.get("APPDATA")
    local = os.environ.get("LOCALAPPDATA") or roaming
    if roaming and not os.environ.get("TEE_CST_SETTINGS_PATH"):
        os.environ["TEE_CST_SETTINGS_PATH"] = os.path.join(roaming, APP_FOLDER, "settings.json")
    if local and not os.environ.get("TEE_CST_LOG_PATH"):
        os.environ["TEE_CST_LOG_PATH"] = os.path.join(local, APP_FOLDER, "server.log")


def _wait_for_the_reader() -> None:
    """A console opened by a double-click closes with the process, taking the error with it."""
    if sys.stdin is not None and sys.stdin.isatty():
        try:
            input("\nEnter beendet dieses Fenster. ")
        except (EOFError, KeyboardInterrupt):
            pass


def main() -> int:
    _windows_paths()
    if not getattr(sys, "frozen", False):    # running from the checkout, not from the .exe
        here = os.path.dirname(os.path.abspath(__file__))
        sys.path.insert(0, os.path.join(os.path.dirname(here), "src"))

    arguments = list(sys.argv)
    if "--headless" in arguments:
        from teecellstream.__main__ import main as server_main
        return server_main(arguments)

    from teecellstream.app_windows import main as window_main
    return window_main(arguments)


if __name__ == "__main__":
    try:
        code = main()
    except SystemExit as leaving:
        code = leaving.code if isinstance(leaving.code, int) else 0
    except BaseException:                    # noqa: BLE001 - the console IS the error report here
        traceback.print_exc()
        _wait_for_the_reader()
        code = 1
    else:
        if code:
            _wait_for_the_reader()
    sys.exit(code)
