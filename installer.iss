; Inno Setup script -> installer\LocalSub-Setup.exe
#define AppName "LocalSub"
#define AppVersion "1.1.0"

[Setup]
AppId={{8C4E2F7A-3B1D-4E9A-9F21-5A7C0D6B1E42}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=LocalSub
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=installer
OutputBaseFilename=LocalSub-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\LocalSub.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "dist\LocalSub.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\LocalSub.exe"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\LocalSub.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\LocalSub.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
