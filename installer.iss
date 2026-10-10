; Inno Setup script for AuraGram. Built by build.py, which passes the version and
; the publisher from core/constants.py:
;   ISCC /DAppVersion=1.0.0 "/DAppPublisher=Omnya Technology" installer.iss
; It packages dist\AuraGram, the folder PyInstaller produces.
;
; Where things go:
;   the program            C:\Program Files\AuraGram           (needs administrator rights)
;   each user's own data   %APPDATA%\AuraGram (Roaming)        (made by the program itself)
;   downloaded files       the user's Downloads\AuraGram

#define AppName "AuraGram"
#define AppExe "AuraGram.exe"
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppPublisher
  #define AppPublisher "Omnya Technology"
#endif
#ifndef AppCopyright
  #define AppCopyright ""
#endif

[Setup]
; Identifies the app to Windows across versions. Never change it, or upgrades install side by side.
AppId={{6B6E1A52-4D0C-4B7E-9C3A-AE21F0D47A61}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppCopyright={#AppCopyright}
VersionInfoVersion={#AppVersion}
VersionInfoCompany={#AppPublisher}
; Installed for everyone on the computer, under Program Files.
PrivilegesRequired=admin
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=dist
OutputBaseFilename={#AppName}-Setup-{#AppVersion}
SetupIconFile=assets\auragram.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; The running copy is closed by the code below, which lets it sign off properly;
; Windows' own "close applications" step would only see a program with no window.
CloseApplications=no

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
arabic.UninstallShortcut=إزالة AuraGram
english.UninstallShortcut=Uninstall AuraGram
arabic.RemoveData=هل تريد أيضاً حذف بيانات حسابك وإعداداتك من هذا الجهاز؟%n%nإذا اخترت «نعم» فستحتاج إلى تسجيل الدخول من جديد عند تثبيت AuraGram مرة أخرى.%nإذا اخترت «لا» فستبقى محفوظة في المجلد:%n%1
english.RemoveData=Also delete your account data and settings from this computer?%n%nIf you choose Yes, you will have to sign in again the next time you install AuraGram.%nIf you choose No, they stay in the folder:%n%1

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"
Name: "startup"; Description: "{cm:StartWithWindows}"

[Files]
Source: "dist\{#AppName}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\{cm:UninstallShortcut}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; --background: start hidden next to the clock; the window opens with Ctrl+Alt+Shift+A.
; HKA is the all-users key here, matching the all-users install.
Root: HKA; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#AppName}"; ValueData: """{app}\{#AppExe}"" --background"; Tasks: startup; Flags: uninsdeletevalue

[Run]
; runasoriginaluser: start it as the person at the keyboard, not as the administrator who installed it.
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchNow}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallDelete]
; Anything the program left beside itself (there should be nothing: it writes only to the user's folders).
Type: filesandordirs; Name: "{app}"

[Code]
// AuraGram keeps running in the background, so its files are in use until it exits.
// First ask it to close itself, which signs it off from Telegram cleanly; then make
// sure, in case it was frozen or belonged to another user's session.
procedure CloseRunningProgram();
var
  ResultCode: Integer;
  ExePath: String;
begin
  ExePath := ExpandConstant('{app}\{#AppExe}');
  if FileExists(ExePath) then
    Exec(ExePath, '--quit', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#AppExe}', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

// Installing over an existing copy (an upgrade).
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  CloseRunningProgram();
  Result := '';
end;

function InitializeUninstall(): Boolean;
begin
  CloseRunningProgram();
  Result := True;
end;

// The Telegram session and settings live in the user's Roaming folder, not in
// Program Files, so removing the program does not touch them. Offer to remove
// them too, defaulting to No: deleting them signs the user out for good.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep <> usPostUninstall then
    Exit;
  DataDir := ExpandConstant('{userappdata}\{#AppName}');
  if not DirExists(DataDir) then
    Exit;
  // In a silent uninstall nobody is there to answer, so the data is kept.
  if SuppressibleMsgBox(FmtMessage(CustomMessage('RemoveData'), [DataDir]), mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
    DelTree(DataDir, True, True, True);
end;
