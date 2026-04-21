; industry_news.iss
; Inno Setup 6 script for Industry News — Company Reports and Information Engine
;
; Prerequisites:
;   1. Install Inno Setup 6 from https://jrsoftware.org/isinfo.php
;   2. Build the PyInstaller bundle first:
;        pip install pyinstaller
;        pyinstaller industry_news.spec
;      This produces:  dist\IndustryNews\
;   3. (Optional) Place a 256x256 icon at installer\icon.ico
;   4. Open this file in the Inno Setup IDE and click Build,
;      or run:  iscc installer\industry_news.iss
;
; Output:
;   installer\Output\IndustryNews-Setup.exe
;   (Upload this single file to your GitHub Release)

#define AppName      "Industry News"
#define AppVersion   "1.0.0"
#define AppPublisher "Your Name or Organization"
#define AppURL       "https://github.com/YOUR_USERNAME/Industry-News-MVP"
#define AppExeName   "IndustryNews.exe"
#define SourceDir    "..\dist\IndustryNews"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
; Desktop shortcut is optional — user can opt out during install
; Compression
Compression=lzma2/ultra64
SolidCompression=yes
; Installer output
OutputDir=Output
OutputBaseFilename=IndustryNews-Setup
; Icon — comment this line out if you don't have an icon yet
; SetupIconFile=icon.ico
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Offer a desktop shortcut during install (checked by default)
Name: "desktopicon"; \
  Description: "{cm:CreateDesktopIcon}"; \
  GroupDescription: "{cm:AdditionalIcons}"; \
  Flags: unchecked

[Files]
; Copy everything PyInstaller built into the install directory
Source: "{#SourceDir}\*"; \
  DestDir: "{app}"; \
  Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; Start Menu shortcut
Name: "{group}\{#AppName}"; \
  Filename: "{app}\{#AppExeName}"; \
  Comment: "Launch Industry News"

; Desktop shortcut (only if the user ticked the checkbox)
Name: "{autodesktop}\{#AppName}"; \
  Filename: "{app}\{#AppExeName}"; \
  Comment: "Launch Industry News"; \
  Tasks: desktopicon

; Start Menu uninstall link
Name: "{group}\Uninstall {#AppName}"; \
  Filename: "{uninstallexe}"

[Run]
; Offer to launch the app immediately after install finishes
Filename: "{app}\{#AppExeName}"; \
  Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; \
  Flags: nowait postinstall skipifsilent
