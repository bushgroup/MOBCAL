; Inno Setup script for the mobcal installer.
;
; Packages the onedir folder dist\mobcal\ that tools\build_exe.ps1 builds: mobcal.exe (the
; command), mobcal-gui.exe (the window, without a console) and PyInstaller's _internal\, the
; two Fortran binaries built in CI with their build.json under
; fortran\, and the 2012 choline input and outputs under examples\. Compile with Inno Setup 6:
;
;   iscc packaging\mobcal.iss
;
; (tools\build_exe.ps1 does this last), and the installer lands in dist\installer\.
;
; Per-user (PrivilegesRequired=lowest): an instrument PC's operator account may lack admin
; rights, and nothing here needs them. mobcal is a command, so the default-checked "addtopath"
; task puts the install directory on the user's PATH, and the uninstaller takes it off again.
; The Start menu gets the window, MOBCAL, first; then a command prompt with mobcal on its PATH
; whichever way that task went, and the self-check. The last page offers to open the window.
;
; MyAppVersion is one of the three version declarations tools\check_public.py compares.

#define MyAppName "MOBCAL"
#define MyAppVersion "2.0.0rc2.dev0"
#define MyAppPublisher "University of Washington"
#define MyAppURL "https://github.com/bushgroup/MOBCAL"
#define MyAppExeName "mobcal.exe"
#define MyGuiExeName "mobcal-gui.exe"

[Setup]
AppId={{A4606743-A6A3-4002-A966-D8EA444CAB47}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
UninstallDisplayIcon={app}\{#MyGuiExeName}
SetupIconFile=icon\mobcal.ico
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist\installer
OutputBaseFilename=mobcal-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
ChangesEnvironment=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "addtopath"; Description: "Add mobcal to my PATH, so that a new terminal can run it"
Name: "desktopicon"; Description: "Put MOBCAL on the desktop"; Flags: unchecked

[InstallDelete]
; Setup never deletes a file the new build does not carry, so an upgrade would otherwise keep
; the previous version's libraries, binaries and build.json beside the new ones.
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\fortran"
Type: filesandordirs; Name: "{app}\examples"

[Files]
Source: "..\dist\mobcal\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MOBCAL"; Filename: "{app}\{#MyGuiExeName}"; WorkingDir: "{userdocs}"; Comment: "Calculate collision cross sections"
Name: "{userdesktop}\MOBCAL"; Filename: "{app}\{#MyGuiExeName}"; WorkingDir: "{userdocs}"; Tasks: desktopicon
Name: "{group}\MOBCAL command prompt"; Filename: "{cmd}"; Parameters: "/k ""set ""PATH={app};%PATH%"" && mobcal --help"""; WorkingDir: "{userdocs}"; Comment: "A command prompt in which mobcal runs"
Name: "{group}\MOBCAL self-check"; Filename: "{cmd}"; Parameters: "/k """"{app}\{#MyAppExeName}"" self-check"""; WorkingDir: "{app}"; Comment: "Check that this installation can compute a cross section"
Name: "{group}\Uninstall MOBCAL"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyGuiExeName}"; WorkingDir: "{userdocs}"; Description: "Open MOBCAL"; Flags: postinstall skipifsilent nowait unchecked
Filename: "{cmd}"; Parameters: "/k """"{app}\{#MyAppExeName}"" self-check"""; WorkingDir: "{app}"; Description: "Run the self-check"; Flags: postinstall skipifsilent nowait

[Code]
const
  EnvKey = 'Environment';

{ True if Dir is one of the ;-separated entries of Paths, ignoring case. }
function PathHas(Paths, Dir: string): Boolean;
begin
  Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';') > 0;
end;

procedure AddToPath(Dir: string);
var
  Paths: string;
begin
  if not RegQueryStringValue(HKCU, EnvKey, 'Path', Paths) then
    Paths := '';
  if PathHas(Paths, Dir) then
    exit;
  if (Paths <> '') and (Copy(Paths, Length(Paths), 1) <> ';') then
    Paths := Paths + ';';
  RegWriteExpandStringValue(HKCU, EnvKey, 'Path', Paths + Dir);
end;

procedure RemoveFromPath(Dir: string);
var
  Paths: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKCU, EnvKey, 'Path', Paths) then
    exit;
  Paths := ';' + Paths + ';';
  P := Pos(';' + Uppercase(Dir) + ';', Uppercase(Paths));
  if P = 0 then
    exit;
  Delete(Paths, P, Length(Dir) + 1);
  Paths := Copy(Paths, 2, Length(Paths) - 2);
  if Paths = '' then
    RegDeleteValue(HKCU, EnvKey, 'Path')
  else
    RegWriteExpandStringValue(HKCU, EnvKey, 'Path', Paths);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('addtopath') then
    AddToPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFromPath(ExpandConstant('{app}'));
end;
