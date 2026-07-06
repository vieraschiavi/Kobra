; MV Kobra AI · Instalador Windows (Inno Setup 6)
; Envuelve el bundle standalone de PyInstaller (dist\MVKobraAI) en un instalador
; MVKobraAI_Setup_vX.exe con accesos directos en el menú Inicio y el escritorio.
;
; Construir (en Windows, con Inno Setup instalado):
;   iscc packaging\instalador.iss
; Requiere que antes exista dist\MVKobraAI\ (salida de PyInstaller).

#define AppName "MV Kobra AI"
#ifndef AppVersion
  #define AppVersion "1.3.0"
#endif
#define AppPublisher "MV Kobra AI"
#define AppExe "MVKobraAI.exe"

[Setup]
AppId={{B7E2C1A4-6F3D-4E2A-9C21-KOBRAIA00001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\MV Kobra AI
DefaultGroupName=MV Kobra AI
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=MVKobraAI_Setup_v{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
SetupIconFile=..\assets\brand\mv.ico
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\MVKobraAI\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MV Kobra AI"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar MV Kobra AI"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MV Kobra AI"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir MV Kobra AI ahora"; Flags: nowait postinstall skipifsilent
