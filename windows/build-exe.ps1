# Baut "TEE PS3 Remote Player server.exe" auf dem Windows-PC.
# Aufruf:  powershell -NoProfile -ExecutionPolicy Bypass -File build-exe.ps1
$ErrorActionPreference = "Stop"
# Alles relativ zum Ordner dieses Skripts: der Quellbaum (src\, das Startmodul, das Icon) liegt
# daneben, und kein Pfad im Repo verraet, auf wessen Rechner gebaut wurde.
$base = $PSScriptRoot
$log  = Join-Path $base "build.log"
function W($t) { Add-Content $log $t; Write-Output $t }
Set-Content $log ("=== Bau " + (Get-Date -Format "HH:mm:ss") + " ===")

$name = "TEE PS3 Remote Player server"
Set-Location $base
# Eine laufende Fassung haelt ihre eigene Datei fest - PyInstaller bekaeme WinError 5 und liesse die
# ALTE exe stehen, die dann faelschlich wie ein geglueckter Bau aussieht.
Get-Process -Name $name -EA SilentlyContinue | ForEach-Object {
  W ("  laufende Fassung beendet: PID " + $_.Id)
  Stop-Process -Id $_.Id -Force -EA SilentlyContinue
}
Get-Process -Name ffmpeg -EA SilentlyContinue | Stop-Process -Force -EA SilentlyContinue
Start-Sleep -Seconds 2
Remove-Item "$base\build","$base\dist" -Recurse -Force -EA SilentlyContinue

$arguments = @(
  '-m','PyInstaller','--noconfirm','--clean','--onedir','--console',
  '--name', $name,
  '--icon', "$base\tee-ps3-remote-player.ico",
  '--paths', "$base\src",
  # netinfo_windows wird erst beim ersten Beacon geladen - sicherheitshalber ausdruecklich
  '--hidden-import','teecellstream.netinfo_windows',
  '--hidden-import','teecellstream.capture_windows',
  '--hidden-import','teecellstream.display_windows',
  '--hidden-import','teecellstream.input_windows',
  '--hidden-import','teecellstream.gamepad_windows',
  '--hidden-import','teecellstream.power_windows',
  '--hidden-import','teecellstream.shell_extension_windows',
  '--hidden-import','teecellstream.console_windows',
  '--hidden-import','teecellstream.autostart_windows',
  '--hidden-import','teecellstream.ui_windows',
  '--hidden-import','teecellstream.app_windows',
  '--hidden-import','teecellstream.ui_text',
  # vgamepad laedt ViGEmClient.dll ueber einen Pfad aus seinem eigenen __file__ - das ist kein Import,
  # nur collect-all zieht die DLL mit. Ohne sie baut die exe klaglos und das Pad bleibt stumm.
  '--collect-all','vgamepad',
  # das alles gibt es unter Windows nicht; ohne die Ausschluesse sucht PyInstaller danach und warnt
  '--exclude-module','gi',
  '--exclude-module','gi.repository',
  '--exclude-module','evdev',
  '--exclude-module','dbus',
  '--exclude-module','fcntl',
  '--exclude-module','termios',
  '--exclude-module','tkinter',
  '--exclude-module','PySide6.QtQml',
  '--exclude-module','PySide6.QtQuick',
  '--exclude-module','PySide6.QtMultimedia',
  '--exclude-module','PySide6.QtWebEngineCore',
  '--exclude-module','PySide6.Qt3DCore',
  '--exclude-module','PySide6.QtCharts',
  '--exclude-module','PySide6.QtDataVisualization',
  '--exclude-module','PySide6.QtPdf',
  # Die Linux-Haelfte von plat.py ist im else-Zweig statisch sichtbar, hier aber nicht importierbar.
  # Zur Laufzeit wird sie unter Windows nie angefasst - ohne diese Ausschluesse zieht PyInstaller sie
  # samt Suche nach gi/evdev/fcntl mit und das Bauprotokoll steht voller "module not found".
  '--exclude-module','teecellstream.capture',            # braucht fcntl
  '--exclude-module','teecellstream.portal',             # braucht gi
  '--exclude-module','teecellstream.display_mode',       # braucht gi
  '--exclude-module','teecellstream.power',              # braucht gi
  '--exclude-module','teecellstream.shell_extension',    # braucht gi
  '--exclude-module','teecellstream.desktop_input',      # braucht evdev
  '--exclude-module','teecellstream.virtual_gamepad',    # braucht evdev
  '--exclude-module','teecellstream.hid_keys',           # braucht evdev, nur desktop_input nutzt es
  # Die Oberflaeche gibt es unter Windows nicht: app/ui/tray sind reines PyGObject
  '--exclude-module','teecellstream.app',
  '--exclude-module','teecellstream.ui',
  '--exclude-module','teecellstream.tray',
  '--exclude-module','teecellstream.autostart',
  # reine Groesse, der headless-Pfad fasst nichts davon an
  '--exclude-module','tkinter',
  '--exclude-module','unittest',
  '--exclude-module','pydoc',
  '--exclude-module','pdb',
  "$base\tee_ps3_remote_player_server.py"
)
W ("PyInstaller " + (& python -m PyInstaller --version))
# & mit @-Splatting statt Start-Process: nur so bleibt "TEE PS3 Remote Player server" EIN Argument.
# ErrorActionPreference muss dafuer runter: PyInstaller schreibt seinen normalen Fortschritt nach
# stderr, und "Stop" macht daraus einen Abbruch beim ersten INFO-Zeile.
$ErrorActionPreference = "Continue"
& python @arguments > "$base\build.out" 2> "$base\build.err"
$code = $LASTEXITCODE
$ErrorActionPreference = "Stop"
W ("Rueckgabe: " + $code)
Get-Content "$base\build.err" -EA SilentlyContinue | Select-String -Pattern "ERROR|WARNING: Hidden|not found|Traceback" |
  Select-Object -First 25 | ForEach-Object { W ("  ! " + $_) }
# --onedir legt dist\<Name>\<Name>.exe an, nicht dist\<Name>.exe
$exe = "$base\dist\$name\$name.exe"
if (Test-Path $exe) {
  $ordner = Split-Path $exe
  $gesamt = (Get-ChildItem $ordner -Recurse -File | Measure-Object -Property Length -Sum).Sum
  W ("fertig: " + $exe)
  W ("  Ordner gesamt: " + [math]::Round($gesamt / 1MB, 1) + " MB, " +
     (Get-ChildItem $ordner -Recurse -File).Count + " Dateien")
} else {
  W "KEINE EXE ENTSTANDEN"
  Get-Content "$base\build.err" -EA SilentlyContinue | Select-Object -Last 25 | ForEach-Object { W ("  " + $_) }
}
