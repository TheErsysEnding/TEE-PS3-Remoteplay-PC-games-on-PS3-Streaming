# Baut den Installer. Erwartet neben sich: installer.iss, licenses\, das Icon, ffmpeg.exe und den
# ViGEmBus-Installer - und den fertigen Programmordner von build-exe.ps1. Wo der liegt, sagt -Build;
# ohne Angabe wird der Nachbarordner "tee-build" angenommen.
param([string]$Build = (Join-Path (Split-Path $PSScriptRoot -Parent) "tee-build"))
$base = $PSScriptRoot
$log  = Join-Path $base "installer.log"
function W($t) { Add-Content $log $t; Write-Output $t }
Set-Content $log ("=== Installer-Bau " + (Get-Date -Format "HH:mm:ss") + " ===")

if (-not (Test-Path "$base\ffmpeg.exe")) { W "ffmpeg.exe fehlt neben dem Skript"; exit 1 }
$fertig = Join-Path $Build "dist\TEE PS3 Remote Player server"
Remove-Item "$base\server" -Recurse -Force -EA SilentlyContinue
Copy-Item $fertig "$base\server" -Recurse -Force
W ("ffmpeg.exe:  " + [math]::Round((Get-Item "$base\ffmpeg.exe").Length / 1MB, 1) + " MB")
W ("Serverordner: " + [math]::Round(((Get-ChildItem "$base\server" -Recurse -File | Measure-Object -Property Length -Sum).Sum) / 1MB, 1) + " MB")

# winget installiert Inno je nach Paket mal systemweit, mal nur fuer den Benutzer
$iscc = Get-ChildItem `
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", `
  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe", `
  "C:\Program Files\Inno Setup 6\ISCC.exe" -EA SilentlyContinue | Select-Object -First 1
if (-not $iscc) { W "ISCC.exe nicht gefunden"; exit 1 }
W ("ISCC: " + $iscc.FullName)

$ErrorActionPreference = "Continue"
& $iscc.FullName "$base\installer.iss" > "$base\iscc.out" 2> "$base\iscc.err"
$code = $LASTEXITCODE
$ErrorActionPreference = "Stop"
W ("Rueckgabe: " + $code)
if ($code -ne 0) {
  Get-Content "$base\iscc.out","$base\iscc.err" -EA SilentlyContinue | Select-Object -Last 20 | ForEach-Object { W ("  " + $_) }
} else {
  Get-ChildItem "$base\*.exe" | Where-Object { $_.Name -like "*Setup*" } |
    ForEach-Object { W ("fertig: " + $_.FullName + "   " + [math]::Round($_.Length / 1MB, 1) + " MB") }
}
