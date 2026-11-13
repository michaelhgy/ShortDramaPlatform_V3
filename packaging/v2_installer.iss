#define MyAppName "短剧推广运营系统 V2"
#define MyAppVersion "2026.09.21"
#define MyAppPublisher "ShortDramaPlatform"
#define MyAppExeName "ShortDramaPlatform.exe"

[Setup]
AppId={{8A1E4D20-723A-4E0D-A58A-9D5D2A40E7E8}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\ShortDramaPlatform_V2
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=output\installer
OutputBaseFilename=ShortDramaPlatform_V2_Setup_2026.09.21
SetupIconFile=assets\v2-application-icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "assets\ChineseSimplified.isl"

[Files]
Source: "output\ShortDramaPlatform\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent
