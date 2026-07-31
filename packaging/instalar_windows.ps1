<#
    MV Kobra AI · Instalación en Windows (accesos, icono y desinstalador)
    ====================================================================
    Deja el programa instalado como un programa de verdad: icono propio,
    entrada en el Menú Inicio, acceso directo en el Escritorio y una entrada en
    «Aplicaciones y características» (Agregar o quitar programas) que lo
    desinstala.

    Antes esto no existía en las ediciones runnables: el ZIP traía un
    INICIAR_*.bat y nada más. El programa funcionaba, pero no aparecía instalado
    en ningún lado — para abrirlo había que acordarse de dónde se había
    descomprimido la carpeta, y para "desinstalarlo" había que borrarla a mano.

    Todo se registra en HKCU y en el perfil del usuario: **no pide permisos de
    administrador**. Esa es la razón de no usar HKLM ni Archivos de programa.

    Uso:
        powershell -ExecutionPolicy Bypass -File instalar_windows.ps1 `
            -Destino "C:\ruta\instalacion" -Codigo "C:\ruta\codigo" `
            -Python  "C:\ruta\entorno\Scripts\pythonw.exe"
#>
[CmdletBinding()]
param(
    # Carpeta donde queda instalado (accesos, icono, desinstalador, datos).
    [Parameter(Mandatory = $true)][string]$Destino,
    # Carpeta con el código (kobra_launcher.py y el resto del programa).
    [Parameter(Mandatory = $true)][string]$Codigo,
    # pythonw.exe del entorno: `w` = sin ventana negra de consola al abrir.
    [Parameter(Mandatory = $true)][string]$Python,
    [string]$Nombre  = "MV Kobra AI",
    [string]$Version = "1.3.0",
    [string]$Editor  = "MV Kobra AI",
    # Owner: sin licencia ni vencimiento. Para una edición de cliente va $false.
    [switch]$Owner,
    # Carpeta de datos del usuario. Por defecto, dentro de la instalación.
    [string]$Datos = ""
)

$ErrorActionPreference = "Stop"
$ClaveApp = "MVKobraAI"
if ($Owner) { $ClaveApp = "MVKobraAI_Owner"; $Nombre = "$Nombre (Owner)" }
if (-not $Datos) { $Datos = Join-Path $Destino "datos" }

New-Item -ItemType Directory -Force -Path $Destino, $Datos | Out-Null

# --- Dónde está el launcher -------------------------------------------------
# Hay dos layouts y los dos son válidos: el repo lo tiene en `packaging\` y el
# ZIP de una edición lo copia a la raíz de `kobra_software\`. Buscarlo evita
# que el acceso directo quede apuntando a un archivo que no existe — que es un
# fallo silencioso: el .lnk se crea igual y no abre nada al hacer clic.
$Launcher = $null
foreach ($cand in @((Join-Path $Codigo "kobra_launcher.py"),
                    (Join-Path $Codigo "packaging\kobra_launcher.py"))) {
    if (Test-Path -LiteralPath $cand) { $Launcher = $cand; break }
}
if (-not $Launcher) {
    throw "No encontre kobra_launcher.py en '$Codigo' (ni en packaging\). Revisa -Codigo."
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "No existe el ejecutable de Python indicado: '$Python'."
}

# La UI compilada puede venir en owner\ui_dist (repo y ZIP) — si no está, el
# launcher igual sirve la API, pero conviene avisarlo ahora y no en el arranque.
$UiDist = Join-Path $Codigo "owner\ui_dist"

# --- Icono ------------------------------------------------------------------
# El .lnk guarda la RUTA del icono, no el icono: si apunta a la carpeta del
# código y esa carpeta se mueve o se borra, el acceso directo queda en blanco.
# Por eso se copia a la carpeta de instalación, que es la que el desinstalador
# controla.
$Icono = Join-Path $Destino "MVKobraAI.ico"
foreach ($cand in @((Join-Path $Codigo "electron\build\icon.ico"),
                    (Join-Path $Codigo "assets\brand\mv.ico"),
                    (Join-Path $Codigo "MVKobraAI.ico"))) {
    if (Test-Path -LiteralPath $cand) { Copy-Item -LiteralPath $cand -Destination $Icono -Force; break }
}
if (-not (Test-Path -LiteralPath $Icono)) { $Icono = $Python }   # sin .ico, el de Python

# --- Lanzador ---------------------------------------------------------------
# Un .lnk no puede definir variables de entorno, y el programa necesita saber
# que arranca en modo owner y dónde están los datos. Se resuelve con un .cmd
# que las define, y un .vbs que lo corre OCULTO: sin el .vbs, cada arranque
# parpadea una ventana de consola negra — la señal más clara de "esto es un
# script", no un programa.
$Cmd = Join-Path $Destino "MVKobraAI.cmd"
$lineas = @(
    "@echo off",
    "cd /d `"$Codigo`"",
    "set `"KOBRA_DATA_DIR=$Datos`"",
    "set `"KOBRA_UI_DIST=$UiDist`"",
    "set KOBRA_APP_WINDOW=1"
)
if ($Owner) { $lineas += "set KOBRA_OWNER=1" }
$lineas += "start `"`" `"$Python`" `"$Launcher`""
Set-Content -LiteralPath $Cmd -Value $lineas -Encoding ASCII

$Vbs = Join-Path $Destino "MVKobraAI.vbs"
Set-Content -LiteralPath $Vbs -Encoding ASCII -Value @(
    "' Arranca MV Kobra AI sin ventana de consola.",
    "CreateObject(`"WScript.Shell`").Run `"`"`"$Cmd`"`"`", 0, False"
)

# --- Accesos directos -------------------------------------------------------
$sh = New-Object -ComObject WScript.Shell

function Nuevo-Acceso([string]$ruta) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ruta) | Out-Null
    $lnk = $sh.CreateShortcut($ruta)
    # wscript.exe y no el .vbs directo: si el usuario tiene los .vbs asociados
    # a otro programa (o bloqueados por política), el acceso no abriría nada.
    $lnk.TargetPath       = Join-Path $env:WINDIR "System32\wscript.exe"
    $lnk.Arguments        = "`"$Vbs`""
    $lnk.WorkingDirectory = $Codigo
    $lnk.IconLocation     = "$Icono,0"
    $lnk.Description      = "$Nombre - Plataforma de Cobranzas Inteligentes"
    $lnk.Save()
}

$MenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\MV Kobra AI"
$AccesoMenu      = Join-Path $MenuDir "$Nombre.lnk"
$AccesoEscritorio = Join-Path ([Environment]::GetFolderPath("Desktop")) "$Nombre.lnk"
Nuevo-Acceso $AccesoMenu
Nuevo-Acceso $AccesoEscritorio

# --- Desinstalador ----------------------------------------------------------
$DesinstalaPs1 = Join-Path $Destino "desinstalar_windows.ps1"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "desinstalar_windows.ps1") `
          -Destination $DesinstalaPs1 -Force

$DesinstalaCmd = Join-Path $Destino "Desinstalar.cmd"
Set-Content -LiteralPath $DesinstalaCmd -Encoding ASCII -Value @(
    "@echo off",
    "powershell -NoProfile -ExecutionPolicy Bypass -File `"$DesinstalaPs1`" -Destino `"$Destino`" -ClaveApp `"$ClaveApp`" %*",
    "pause"
)

# Acceso al desinstalador también en el Menú Inicio, como cualquier programa.
$lnkDes = $sh.CreateShortcut((Join-Path $MenuDir "Desinstalar $Nombre.lnk"))
$lnkDes.TargetPath   = $DesinstalaCmd
$lnkDes.IconLocation = "$Icono,0"
$lnkDes.Save()

# --- «Agregar o quitar programas» -------------------------------------------
# HKCU y no HKLM: así la instalación no necesita permisos de administrador.
# Windows muestra las dos ramas juntas en Aplicaciones y características.
$Reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$ClaveApp"
New-Item -Path $Reg -Force | Out-Null
$tamanoKb = 0
try {
    $tamanoKb = [int]((Get-ChildItem -LiteralPath $Destino -Recurse -File -ErrorAction SilentlyContinue |
                        Measure-Object -Property Length -Sum).Sum / 1KB)
} catch { }
$props = @{
    DisplayName     = $Nombre
    DisplayVersion  = $Version
    Publisher       = $Editor
    DisplayIcon     = $Icono
    InstallLocation = $Destino
    UninstallString = "`"$DesinstalaCmd`""
    NoModify        = 1
    NoRepair        = 1
    EstimatedSize   = $tamanoKb
    InstallDate     = (Get-Date -Format "yyyyMMdd")
}
foreach ($k in $props.Keys) {
    $tipo = if ($props[$k] -is [int]) { "DWord" } else { "String" }
    New-ItemProperty -Path $Reg -Name $k -Value $props[$k] -PropertyType $tipo -Force | Out-Null
}

Write-Host ""
Write-Host "  $Nombre quedo instalado."
Write-Host "    Menu Inicio ...... MV Kobra AI"
Write-Host "    Escritorio ....... $Nombre"
Write-Host "    Desinstalar ...... Agregar o quitar programas (o Desinstalar.cmd)"
Write-Host "    Datos ............ $Datos"
Write-Host ""
