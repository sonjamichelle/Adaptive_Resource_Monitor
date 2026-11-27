#define RunKey "Software\Microsoft\Windows\CurrentVersion\Run"

[Setup]
AppId={#SetupId}
AppName={#Product}
AppVersion={#AppVersion}
AppVerName={#Product} {#AppVersion}
AppPublisher={#ArmPublisher}
AppPublisherURL={#AppWebsite}
AppSupportURL={#AppSupport}
AppCopyright={#ArmCopyright}
AppComments={#AppDescription}
DefaultDirName={localappdata}\Programs\Adaptive Resource Monitor
DefaultGroupName={#Product}
DisableProgramGroupPage=auto
AllowNoIcons=yes
DisableDirPage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
SetupArchitecture=x64
MinVersion=10.0.17763
OutputBaseFilename=AdaptiveResourceMonitor-{#AppVersion}-windows-x64-setup
VersionInfoVersion={#FileVersion}
VersionInfoTextVersion={#AppVersion}
VersionInfoProductName={#Product}
VersionInfoProductTextVersion={#AppVersion}
VersionInfoCompany={#ArmPublisher}
VersionInfoCopyright={#ArmCopyright}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#AppIcon}
WizardImageFile={#WizardImage}
WizardSmallImageFile={#WizardEmblem}
UninstallDisplayIcon={app}\{#Executable}
CloseApplications=no
RestartApplications=no

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start Adaptive Resource Monitor with Windows"; Flags: unchecked

[Files]
Source: "{#Payload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#Product}"; Filename: "{app}\{#Executable}"; IconFilename: "{app}\{#Executable}"; AppUserModelID: "{#AppModelId}"; Check: not ArmUpdate
Name: "{userdesktop}\{#Product}"; Filename: "{app}\{#Executable}"; IconFilename: "{app}\{#Executable}"; AppUserModelID: "{#AppModelId}"; Tasks: desktopicon; Check: not ArmUpdate

[Registry]
Root: HKCU; Subkey: "{#RunKey}"; ValueType: string; ValueName: "AdaptiveResourceMonitor"; ValueData: """{app}\{#Executable}"""; Tasks: startup; Check: not ArmUpdate

[Run]
Filename: "{app}\{#Executable}"; Description: "Open Adaptive Resource Monitor"; Flags: nowait postinstall skipifsilent

[Code]
function OpenPayloadFile(Name: String; Access, Share: Cardinal; Security: Integer;
  Creation, Flags: Cardinal; Template: THandle): THandle;
  external 'CreateFileW@kernel32.dll stdcall';

function ClosePayloadFile(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Target: String;
  Handle: THandle;
begin
  Result := '';
  Target := ExpandConstant('{app}\{#Executable}');
  if FileExists(Target) then
  begin
    { An executable loaded as a Windows image cannot be opened for writing. }
    Handle := OpenPayloadFile(Target, 2, 7, 0, 3, 0, 0);
    if Handle = THandle(-1) then
      Result := 'Close Adaptive Resource Monitor from its notification-area menu, then run Setup again.'
    else
      ClosePayloadFile(Handle);
  end;
end;

function ArmUpdate: Boolean;
begin
  Result := ExpandConstant('{param:ARMUPDATE|0}') = '1';
end;

procedure CurUninstallStepChanged(Step: TUninstallStep);
var
  Value, Target: String;
begin
  if Step = usPostUninstall then
  begin
    Target := ExpandConstant('{app}\{#Executable}');
    if RegQueryStringValue(HKCU, '{#RunKey}', 'AdaptiveResourceMonitor', Value) then
      if (CompareText(Value, Target) = 0) or (CompareText(Value, '"' + Target + '"') = 0) then
        RegDeleteValue(HKCU, '{#RunKey}', 'AdaptiveResourceMonitor');
  end;
end;
