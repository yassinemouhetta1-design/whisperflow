; ============================================================
;  WhisperFlow — Script d'installation Inno Setup
;  Génère Installer\WhisperFlow-Setup.exe (app complète + CUDA + modèle)
; ============================================================

#define MyAppName "WhisperFlow"
#define MyAppVersion "1.1.1"
#ifndef BundleDir
  #define BundleDir "dist\WhisperFlow"
#endif
#ifndef PrereqDir
  #define PrereqDir "prerequisites"
#endif
#ifndef ReleaseOutputDir
  #define ReleaseOutputDir "Installer"
#endif
#define MyAppPublisher "WhisperFlow Local"
#define MyAppExeName "WhisperFlow.exe"

[Setup]
AppId={{8F4C2E97-6A51-4D3B-9E08-7C5A1B2D4F60}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir={#ReleaseOutputDir}
OutputBaseFilename=WhisperFlow-Setup-1.1.1-Windows-x64
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
; Compression poussée : le paquet est gros (modèle + CUDA), on privilégie le ratio
Compression=zip/1
SolidCompression=no
ArchitecturesAllowed=x64compatible
MinVersion=10.0.17763
AppMutex=Local\WhisperFlow.Application.v1
CloseApplications=yes
RestartApplications=no
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
WizardStyle=modern

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "Lancer WhisperFlow au démarrage de Windows"; GroupDescription: "Options supplémentaires :"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#PrereqDir}\vc_redist.x64.exe"; Flags: dontcopy
Source: "{#PrereqDir}\WebView2RuntimeInstallerX64.exe"; Flags: dontcopy

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\models"

[Code]
function WebView2Installe(): Boolean;
var
  v: String;
begin
  Result := RegQueryStringValue(HKLM32, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v);
  if not Result then
    Result := RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', v);
  Result := Result and (v <> '') and (v <> '0.0.0.0');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ExitCode: Integer;
begin
  Result := '';
  ExtractTemporaryFile('vc_redist.x64.exe');
  if not Exec(ExpandConstant('{tmp}\vc_redist.x64.exe'), '/install /quiet /norestart', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
  begin
    Result := 'Impossible de lancer le composant Microsoft Visual C++.';
    exit;
  end;
  if (ExitCode <> 0) and (ExitCode <> 1638) and (ExitCode <> 3010) then
  begin
    Result := 'Installation Microsoft Visual C++ impossible (code ' + IntToStr(ExitCode) + ').';
    exit;
  end;
  if ExitCode = 3010 then NeedsRestart := True;
  if not WebView2Installe() then
  begin
    ExtractTemporaryFile('WebView2RuntimeInstallerX64.exe');
    if not Exec(ExpandConstant('{tmp}\WebView2RuntimeInstallerX64.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ExitCode) then
    begin
      Result := 'Impossible de lancer le composant Microsoft WebView2.';
      exit;
    end;
    if not WebView2Installe() then
      Result := 'Microsoft WebView2 est toujours absent. Code : ' + IntToStr(ExitCode) + '. Redémarrez le PC puis relancez cet installateur.';
  end;
end;
