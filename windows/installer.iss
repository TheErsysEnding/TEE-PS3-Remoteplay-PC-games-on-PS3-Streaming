; Der Windows-Installer fuer TEE PS3 Remoteplay.
;
; Er bringt alles mit, was der Server braucht, damit nach der Erstinstallation nichts nachzureichen ist:
;   - den Server selbst (PyInstaller-Einzeldatei)
;   - ffmpeg.exe, NEBEN die Server-exe gelegt, weil ffmpeg_find.py genau dort zuerst nachsieht
;   - den ViGEmBus-Treiber, ohne den es keinen virtuellen Controller gibt - still und nur wenn er fehlt
;   - die Firewall-Ausnahme fuer UDP 38310, ohne die die PS3 den Server zwar findet, aber nichts zurueck-
;     schicken kann (der Beacon geht raus, die Antwort der Konsole kaeme unaufgefordert herein)
;
; Gebaut wird er auf dem Windows-PC mit Inno Setup:  ISCC.exe installer.iss

#define AppName       "TEE PS3 Remoteplay"
#define AppVersion    "1.0.1"
#define AppPublisher  "TEE"
#define AppUrl        "https://github.com/TheErsysEnding/TEE-PS3-Remoteplay-PC-games-on-PS3-Streaming"
#define AppDonate     "https://bero-host.de/spenden/x8atfjdyolqr"
#define AppHub        "https://linktr.ee/theersysending"
#define ServerExe     "TEE PS3 Remote Player server.exe"
#define VigemExe      "ViGEmBus_1.22.0_x64.exe"

[Setup]
AppId={{8B5F2C41-7A3D-4E19-9C6B-2F8A1D5E7B03}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
; these two show up in the Windows software list next to the entry, where somebody who
; wants to find the project again actually looks
AppSupportURL={#AppHub}
AppUpdatesURL={#AppUrl}/releases/latest
AppContact={#AppDonate}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
; Der Installer braucht Administrator - nicht fuer den Server, sondern fuer drei Dinge: nach
; "Program Files" schreiben, die Firewall-Regel anlegen und den Treiber installieren. Der Server
; selbst laeuft danach mit ganz normalen Benutzerrechten.
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=.
OutputBaseFilename={#AppName} Setup {#AppVersion}
SetupIconFile=tee-ps3-remote-player.ico
UninstallDisplayIcon={app}\{#ServerExe}
UninstallDisplayName={#AppName} {#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
LicenseFile=licenses\LICENSE-TEE.txt
InfoAfterFile=licenses\HINWEIS.txt
MinVersion=10.0

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
de.TaskAutostart=Beim Anmelden automatisch starten
de.TaskDesktop=Verknuepfung auf dem Desktop anlegen
de.StatusFirewall=Firewall-Ausnahme fuer die PS3 wird angelegt ...
de.StatusVigem=Controller-Treiber ViGEmBus wird installiert ...
en.TaskAutostart=Start automatically when I sign in
en.TaskDesktop=Create a desktop shortcut
en.StatusFirewall=Adding the firewall exception for the PS3 ...
en.StatusVigem=Installing the ViGEmBus controller driver ...

[Tasks]
Name: "desktopicon"; Description: "{cm:TaskDesktop}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart";  Description: "{cm:TaskAutostart}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Der Bau ist ein Ordner, keine Einzeldatei: mit Qt darin wuerde eine --onefile-exe bei JEDEM
; Start ueber 90 MB nach %TEMP% auspacken. Der Nutzer sieht den Ordner nie - er startet ueber
; das Startmenue.
Source: "server\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; ffmpeg MUSS neben der Server-exe liegen: ffmpeg_find.windows_candidates() sieht dort als erstes nach,
; noch vor PATH. Damit gewinnt der mitgelieferte Bau gegen ein aelteres ffmpeg irgendwo im System.
Source: "ffmpeg.exe";    DestDir: "{app}"; Flags: ignoreversion
Source: "licenses\*";    DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs
; der Treiber reist nur im Installer mit und wird danach wieder weggeraeumt
Source: "{#VigemExe}";   DestDir: "{tmp}"; Flags: deleteafterinstall

[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#ServerExe}"
Name: "{group}\Protokoll anzeigen";   Filename: "{localappdata}\{#AppName}\server.log"
; a shortcut, because a link in a text file nobody opens is not a link
Name: "{group}\Projekt unterstuetzen (1 EUR = 1 Monat Server)"; Filename: "{#AppDonate}"
Name: "{group}\Alle Projekte von TEE";  Filename: "{#AppHub}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";     Filename: "{app}\{#ServerExe}"; Tasks: desktopicon
Name: "{userstartup}\{#AppName}";     Filename: "{app}\{#ServerExe}"; Tasks: autostart

[Run]
; Der Treiber nur, wenn er fehlt - andere Programme (DS4Windows, Parsec) benutzen denselben, und eine
; zweite Installation daruebergebuegelt bringt nichts als Risiko. /quiet /norestart ist am Geraet
; nachgemessen: Rueckgabe 0, Dienst laeuft sofort, kein Neustart noetig.
Filename: "{tmp}\{#VigemExe}"; Parameters: "/quiet /norestart"; StatusMsg: "{cm:StatusVigem}"; \
  Check: not VigemBusInstalled; Flags: waituntilterminated

; Erst eine eventuell vorhandene gleichnamige Regel weg, dann neu - sonst sammeln sich bei jeder
; Neuinstallation Dubletten an. Der Regelname ist unserer, deshalb ist die Sprache des Systems egal;
; was sprachabhaengig waere, sind die eingebauten Gruppennamen, die hier niemand anfasst.
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#AppName}"""; \
  Flags: runhidden; StatusMsg: "{cm:StatusFirewall}"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#AppName}"" dir=in \
  action=allow protocol=UDP localport=38310 program=""{app}\{#ServerExe}"" enable=yes profile=any"; \
  Flags: runhidden; StatusMsg: "{cm:StatusFirewall}"

Filename: "{app}\{#ServerExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM ""{#ServerExe}"" /F"; Flags: runhidden; RunOnceId: "StopServer"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#AppName}"""; \
  Flags: runhidden; RunOnceId: "DropFirewallRule"

[UninstallDelete]
; Das Protokoll ist unseres und darf weg. Die Einstellungen des Nutzers bleiben stehen - wer neu
; installiert, will seine Bitrate und Aufloesung wiederhaben, und wer wirklich alles los werden will,
; loescht den Ordner selbst.
Type: files;          Name: "{localappdata}\{#AppName}\server.log"
Type: dirifempty;     Name: "{localappdata}\{#AppName}"

[Code]
function VigemBusInstalled: Boolean;
begin
  { Drei Zeugen, weil jeder einzelne luegen kann: der Dienstschluessel bleibt nach einer halben
    Deinstallation stehen, die .sys-Datei kann ohne Dienst herumliegen. Einer reicht als Hinweis,
    dass hier schon ein Treiber sitzt, den wir nicht anfassen sollten. }
  Result := RegKeyExists(HKEY_LOCAL_MACHINE, 'SYSTEM\CurrentControlSet\Services\ViGEmBus')
         or FileExists(ExpandConstant('{sys}\drivers\ViGEmBus.sys'));
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  { Eine laufende Fassung haelt ihre eigene .exe fest, und Inno wuerde beim Ueberschreiben nur einen
    Neustart verlangen. Sauberer: vorher beenden. Fehlt sie, meldet taskkill 128 - das ist kein Fehler. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM "{#ServerExe}" /F', '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := '';
end;
