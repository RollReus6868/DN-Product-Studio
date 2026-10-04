; Inno Setup script - per-user install, no admin rights needed.
; Build:  ISCC.exe /DAppVersion=2.1.0 installer\DNProductStudio.iss
; Expects PyInstaller onedir output in dist\DNProductStudio\

#ifndef AppVersion
  #error "Pass /DAppVersion=x.y.z to ISCC"
#endif

[Setup]
AppId={{3D7A9C14-52E8-4B6F-A1C3-9E0F4D2B7A65}
AppName=DN Product Studio
AppVersion={#AppVersion}
AppVerName=DN Product Studio {#AppVersion}
AppPublisher=DN Product Studio
DefaultDirName={localappdata}\Programs\DN Product Studio
DefaultGroupName=DN Product Studio
DisableProgramGroupPage=yes
DisableDirPage=auto
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=DNProductStudio-{#AppVersion}-windows-setup
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\DNProductStudio.exe
UninstallDisplayName=DN Product Studio
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
VersionInfoVersion={#AppVersion}
VersionInfoProductName=DN Product Studio

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[InstallDelete]
; wipe files of the previous version so stale libraries never mix with new ones
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\DNProductStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\DN Product Studio"; Filename: "{app}\DNProductStudio.exe"
Name: "{autodesktop}\DN Product Studio"; Filename: "{app}\DNProductStudio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\DNProductStudio.exe"; Description: "Launch DN Product Studio"; Flags: nowait postinstall skipifsilent
