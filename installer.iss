; AdeBuddy Inno Setup script
; 构建: ISCC.exe installer.iss
; 输出: dist\installer\AdeBuddy-Setup-<version>-x64.exe
;
; 依赖: dist\AdeBuddy\ (由 build.py 产出)

#ifndef APP_VERSION
  #define APP_VERSION "1.0.0"
#endif
#ifndef APP_ARCH
  #define APP_ARCH "x64"
#endif

[Setup]
AppName=AdeBuddy
AppVersion={#APP_VERSION}
AppPublisher=AdeBuddy
AppPublisherURL=https://github.com/superproxy/MyAgentPlugin
AppSupportURL=https://github.com/superproxy/MyAgentPlugin/issues
AppUpdatesURL=https://github.com/superproxy/MyAgentPlugin/releases
AppComments=AdeBuddy - 多 IDE Agent 配置工具
DefaultDirName={autopf}\AdeBuddy
DefaultGroupName=AdeBuddy
DisableProgramGroupPage=yes
OutputDir=dist\installer
OutputBaseFilename=AdeBuddy-Setup-{#APP_VERSION}-{#APP_ARCH}
Compression=lzma2/ultra64
SolidCompression=yes
ArchitecturesAllowed=win64
ArchitecturesInstallIn64BitMode=win64
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\AdeBuddy.exe
UninstallDisplayName=AdeBuddy {#APP_VERSION}
WizardStyle=modern
DisableWelcomePage=no
DisableReadyPage=no
SetupIconFile=assets\app.ico
VersionInfoVersion={#APP_VERSION}
VersionInfoProductVersion={#APP_VERSION}
LicenseFile=
InfoBeforeFile=

[Languages]
; Inno Setup 6.7.3 未内置 ChineseSimplified.isl，需另行下载放入 Languages 目录
; 如需中文界面：从 https://github.com/jrsoftware/issrc/blob/main/Files/Languages/Unofficial/ChineseSimplified.isl 下载
; 放到 "%LOCALAPPDATA%\Programs\Inno Setup 6\Languages\" 后启用下面这行
; Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 0,6.1

[Files]
; 整个 AdeBuddy 目录递归打包（含 exe + _internal）
Source: "dist\AdeBuddy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\AdeBuddy"; Filename: "{app}\AdeBuddy.exe"
Name: "{group}\卸载 AdeBuddy"; Filename: "{uninstallexe}"
Name: "{autodesktop}\AdeBuddy"; Filename: "{app}\AdeBuddy.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AdeBuddy.exe"; Description: "{cm:LaunchProgram,AdeBuddy}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; 卸载时清理用户配置（可选，默认保留）
; Filename: "{cmd}"; Parameters: "/c rmdir /s /q ""{%USERPROFILE}\.agentbuddy"""; Flags: runhidden

[UninstallDelete]
; 清理运行时生成的日志
Type: files; Name: "{app}\app.log"
Type: filesandordirs; Name: "{app}\.bundle_bootstrapped"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
