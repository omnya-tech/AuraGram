; Inno Setup script for AuraGram. Built by build.py, which passes the version:
;   ISCC /DAppVersion=1.0.0 installer.iss
; It packages dist\AuraGram, the folder PyInstaller produces.

#define AppName "AuraGram"
#define AppExe "AuraGram.exe"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
; Identifies the app to Windows across versions. Never change it, or upgrades install side by side.
AppId={{6B6E1A52-4D0C-4B7E-9C3A-AE21F0D47A61}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Per-user install: no administrator prompt.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
SetupIconFile=assets\auragram.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; The program keeps running in the background, so it must be closed to replace its files.
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "arabic"; MessagesFile: "compiler:Languages\Arabic.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
arabic.DesktopIcon=إنشاء اختصار على سطح المكتب
english.DesktopIcon=Create a desktop shortcut
arabic.StartWithWindows=تشغيل AuraGram في الخلفية عند بدء ويندوز
english.StartWithWindows=Start AuraGram in the background when Windows starts
arabic.LaunchNow=تشغيل AuraGram الآن
english.LaunchNow=Launch AuraGram now

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"
Name: "startup"; Description: "{cm:StartWithWindows}"

[Files]
Source: "dist\{#AppName}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; --background: start hidden next to the clock; the window opens with Ctrl+Alt+Shift+A.
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"" --background"; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchNow}"; Flags: nowait postinstall skipifsilent

; The account data in %APPDATA%\AuraGram (the Telegram session and settings) is
; deliberately left in place on uninstall, so reinstalling does not sign the user out.
