; Inno Setup Script for Curateur
; Creates a Windows installer with start menu shortcuts and uninstaller
;
; Usage:
;   1. Install Inno Setup from https://jrsoftware.org/isinfo.php
;   2. Build curateur.exe first: ./build/scripts/build-all.sh (or .bat on Windows)
;   3. Run: iscc build/windows/curateur-setup.iss
;
; Output:
;   build/installers/Curateur-Setup-1.0.0.exe

#define MyAppName "Curateur"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "jbruns"
#define MyAppURL "https://github.com/jbruns/curateur"
#define MyAppExeName "curateur.exe"

[Setup]
; App information
AppId={{8F3D9A2C-5E7B-4D1C-9A3E-2C7F8B4E1D6A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
AppCopyright=Copyright (C) 2025 {#MyAppPublisher}

; Installation directories
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Output settings
OutputDir=build\installers
OutputBaseFilename=Curateur-Setup-{#MyAppVersion}
SetupIconFile=build\icons\curateur.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

; Compression
Compression=lzma2
SolidCompression=yes
LZMAUseSeparateProcess=yes

; Appearance
WizardStyle=modern
WizardImageFile=build\icons\wizard-image.bmp
WizardSmallImageFile=build\icons\wizard-small.bmp

; Misc
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1; Check: not IsAdminInstallMode

[Files]
; Main executable
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Documentation
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "CHANGELOG.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

; Configuration template
Source: "config.yaml.example"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start menu shortcuts
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Comment: "ROM metadata scraper for ES-DE"
Name: "{group}\Configuration Example"; Filename: "{app}\config.yaml.example"
Name: "{group}\Documentation"; Filename: "{app}\README.md"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

; Desktop icon (if selected)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

; Quick launch icon (if selected)
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
; Offer to view help after installation
Filename: "{app}\{#MyAppExeName}"; Parameters: "--help"; Description: "View help"; Flags: postinstall shellexec skipifsilent nowait

; Offer to create initial config
Filename: "{cmd}"; Parameters: "/c copy ""{app}\config.yaml.example"" ""{userappdata}\curateur\config.yaml"""; Description: "Create initial configuration file"; Flags: postinstall skipifsilent

[UninstallDelete]
; Clean up user config on uninstall (optional, commented out by default)
; Type: filesandordirs; Name: "{userappdata}\curateur"

[Code]
// Custom code for installer behavior

procedure InitializeWizard;
var
  WelcomeLabel: TNewStaticText;
begin
  // Customize welcome page
  WelcomeLabel := TNewStaticText.Create(WizardForm);
  WelcomeLabel.Parent := WizardForm.WelcomePage;
  WelcomeLabel.Caption :=
    'This will install Curateur - a ROM metadata scraper for ES-DE.' + #13#10 +
    #13#10 +
    'Curateur downloads game information and media from ScreenScraper.fr' + #13#10 +
    'and generates EmulationStation gamelist.xml files.' + #13#10 +
    #13#10 +
    'You will need a ScreenScraper account to use this software.';
  WelcomeLabel.AutoSize := True;
  WelcomeLabel.WordWrap := True;
  WelcomeLabel.Width := WizardForm.WelcomePage.Width - 40;
  WelcomeLabel.Top := WizardForm.WelcomeLabel2.Top + WizardForm.WelcomeLabel2.Height + 20;
end;

function GetConfigPath(Param: String): String;
begin
  // Return user config directory
  Result := ExpandConstant('{userappdata}\curateur');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Create user config directory
    CreateDir(ExpandConstant('{userappdata}\curateur'));

    // Log installation location
    Log('Installed to: ' + ExpandConstant('{app}'));
    Log('Config will be in: ' + ExpandConstant('{userappdata}\curateur'));
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;

  // Warn about config files
  if FileExists(ExpandConstant('{userappdata}\curateur\config.yaml')) then
  begin
    if MsgBox('Do you want to keep your configuration files?' + #13#10 +
              '(They will be preserved in ' + ExpandConstant('{userappdata}\curateur') + ')',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      Log('User chose to keep configuration files');
    end;
  end;
end;
