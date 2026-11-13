#include "version.iss"
#ifndef ReleaseVersion
  #define ReleaseVersion DefaultReleaseVersion
#endif
#ifndef ProductVersion
  #define ProductVersion DefaultProductVersion
#endif
#define MyAppName "短剧推广运营系统 V3"
#define MyAppExeName "ShortDramaPlatformV3.exe"

[Setup]
AppId={{BC107354-3709-407F-BD46-15E4D0433BA9}
AppName={#MyAppName}
AppVersion={#ProductVersion}
AppVerName={#MyAppName} {#ProductVersion}（{#ReleaseVersion}）
AppPublisher=ShortDramaPlatform
DefaultDirName={localappdata}\ShortDramaPlatform_V3
DefaultGroupName={#MyAppName}
UninstallDisplayName={#MyAppName} {#ReleaseVersion}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=releases\{#ReleaseVersion}\交付
OutputBaseFilename=ShortDramaPlatform_V3_{#ProductVersion}_Setup_{#ReleaseVersion}
SetupIconFile=assets\v2-application-icon.ico
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/fast
SolidCompression=yes
CloseApplications=no
RestartApplications=no
DisableProgramGroupPage=yes
VersionInfoVersion={#ProductVersion}
VersionInfoTextVersion={#ProductVersion} ({#ReleaseVersion})

[Languages]
Name: "chinesesimplified"; MessagesFile: "assets\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建 V3 桌面快捷方式"; GroupDescription: "快捷方式："

[Files]
Source: "releases\{#ReleaseVersion}\ShortDramaPlatformV3\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\V3 业务与功能说明"; Filename: "{app}\使用说明.html"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\使用说明.html"; Description: "查看 V3 使用说明"; Flags: shellexec postinstall skipifsilent unchecked
