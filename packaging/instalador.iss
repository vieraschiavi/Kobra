; Kobra IA · Instalador Windows (Inno Setup 6)
; Envuelve el bundle standalone de PyInstaller (dist\Kobra) en un instalador
; Kobra_Setup_vX.exe con accesos directos en el menú Inicio y el escritorio.
;
; Construir (en Windows, con Inno Setup instalado):
;   iscc packaging\instalador.iss
; Requiere que antes exista dist\Kobra\ (salida de PyInstaller).

#define AppName "Kobra IA"
#ifndef AppVersion
  #define AppVersion "1.3.0"
#endif
#define AppPublisher "Kobra IA"
#define AppExe "Kobra.exe"

[Setup]
AppId={{B7E2C1A4-6F3D-4E2A-9C21-KOBRAIA00001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Kobra IA
DefaultGroupName=Kobra IA
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Kobra_Setup_v{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
SetupIconFile=..\assets\brand\kobra.ico
UninstallDisplayIcon={app}\{#AppExe}

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"

[Files]
Source: "..\dist\Kobra\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Kobra IA"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar Kobra IA"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Kobra IA"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir Kobra IA ahora"; Flags: nowait postinstall skipifsilent
