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
    [string]$Datos = "",
    # Archivo Python que arranca el programa. La app de escritorio usa
    # kobra_launcher.py (FastAPI embebido); la edición Producción sirve el
    # dashboard con Streamlit y pasa kobra_streamlit.py.
    [string]$Lanzador = "kobra_launcher.py",
    # Segundo lanzador, opcional: deja un acceso directo ADEMÁS del principal.
    # Se usa para instalar las dos vías de una sola vez — la app de escritorio
    # y el dashboard Streamlit—, que es lo que necesita el cliente cuyo
    # sistemas bloquea .exe pero no un script. Si no se pasa, no cambia nada.
    [string]$LanzadorAlterno = "",
    [string]$SufijoAlterno = "Dashboard Streamlit"
)

$ErrorActionPreference = "Stop"
$ClaveApp = "MVKobraAI"
if ($Owner) { $ClaveApp = "MVKobraAI_Owner"; $Nombre = "$Nombre (Owner)" }
if (-not $Datos) { $Datos = Join-Path $Destino "datos" }

# --- El disco, antes de copiar nada -----------------------------------------
# Instalar en D: no alcanza si los datos van a un C: lleno, y quedarse sin
# espacio a mitad deja una instalacion rota que nadie sabe interpretar: el
# error habla de un archivo, no del disco. Se pregunta al principio.
# Mismo minimo que MIN_LIBRE_MB en kobra/rutas.py.
$MinLibreMb = 500

function Test-Carpeta([string]$ruta, [string]$para) {
    try {
        New-Item -ItemType Directory -Force -Path $ruta -ErrorAction Stop | Out-Null
    } catch {
        throw "No se puede crear la carpeta de $para ('$ruta'): $($_.Exception.Message)"
    }
    # Prueba de escritura real y no Test-Path: en Windows los permisos
    # declarados dicen que si sobre carpetas donde escribir falla igual
    # (unidad de red caida, carpeta vigilada por el antivirus).
    $prueba = Join-Path $ruta ".kobra_prueba_escritura"
    try {
        Set-Content -LiteralPath $prueba -Value "ok" -Encoding ASCII -ErrorAction Stop
        Remove-Item -LiteralPath $prueba -Force -ErrorAction SilentlyContinue
    } catch {
        throw "La carpeta de $para ('$ruta') no se puede escribir: $($_.Exception.Message)"
    }

    $raiz = [System.IO.Path]::GetPathRoot((Resolve-Path -LiteralPath $ruta).Path)
    $libreMb = 0
    try {
        $libreMb = [int]((Get-PSDrive -Name $raiz.Substring(0, 1) -ErrorAction Stop).Free / 1MB)
    } catch { }
    if ($libreMb -gt 0 -and $libreMb -lt $MinLibreMb) {
        Write-Warning ("En $raiz quedan $libreMb MB libres, por debajo de los " +
                       "$MinLibreMb MB que necesita $para. Es muy probable que " +
                       "se quede sin espacio al importar una cartera o exportar.")
    }
    return $libreMb
}

Test-Carpeta $Destino "la instalacion" | Out-Null
Test-Carpeta $Datos "los datos" | Out-Null

# --- Dónde está el launcher -------------------------------------------------
# Hay dos layouts y los dos son válidos: el repo lo tiene en `packaging\` y el
# ZIP de una edición lo copia a la raíz de `kobra_software\`. Buscarlo evita
# que el acceso directo quede apuntando a un archivo que no existe — que es un
# fallo silencioso: el .lnk se crea igual y no abre nada al hacer clic.
function Buscar-Lanzador([string]$archivo) {
    foreach ($cand in @((Join-Path $Codigo $archivo),
                        (Join-Path $Codigo (Join-Path "packaging" $archivo)))) {
        if (Test-Path -LiteralPath $cand) { return $cand }
    }
    return $null
}

$Launcher = Buscar-Lanzador $Lanzador
if (-not $Launcher) {
    throw "No encontre $Lanzador en '$Codigo' (ni en packaging\). Revisa -Codigo."
}

# El alterno NO es obligatorio: si se pidió y no está, se avisa y se sigue con
# el principal. Cortar la instalación entera por el segundo acceso directo
# sería peor que instalar con uno solo.
$LauncherAlterno = $null
if ($LanzadorAlterno) {
    $LauncherAlterno = Buscar-Lanzador $LanzadorAlterno
    if (-not $LauncherAlterno) {
        Write-Warning "No encontre $LanzadorAlterno: se instala solo el acceso principal."
    }
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
function Nuevo-Lanzador([string]$slug, [string]$destinoPy) {
    # Devuelve la ruta del .vbs que abre ESE lanzador. Un par .cmd/.vbs por
    # modo: comparten instalación, datos e icono, pero arrancan programas
    # distintos (app de escritorio / dashboard Streamlit).
    $cmd = Join-Path $Destino "$slug.cmd"
    $lineas = @(
        "@echo off",
        "cd /d `"$Codigo`"",
        "set `"KOBRA_DATA_DIR=$Datos`"",
        "set `"KOBRA_UI_DIST=$UiDist`"",
        "set KOBRA_APP_WINDOW=1"
    )
    if ($Owner) { $lineas += "set KOBRA_OWNER=1" }
    $lineas += "start `"`" `"$Python`" `"$destinoPy`""
    Set-Content -LiteralPath $cmd -Value $lineas -Encoding ASCII

    $vbs = Join-Path $Destino "$slug.vbs"
    Set-Content -LiteralPath $vbs -Encoding ASCII -Value @(
        "' Arranca MV Kobra AI sin ventana de consola.",
        "CreateObject(`"WScript.Shell`").Run `"`"`"$cmd`"`"`", 0, False"
    )
    return $vbs
}

$Vbs = Nuevo-Lanzador "MVKobraAI" $Launcher

# --- Accesos directos -------------------------------------------------------
$sh = New-Object -ComObject WScript.Shell

function Nuevo-Acceso([string]$ruta, [string]$vbs, [string]$descripcion) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ruta) | Out-Null
    $lnk = $sh.CreateShortcut($ruta)
    # wscript.exe y no el .vbs directo: si el usuario tiene los .vbs asociados
    # a otro programa (o bloqueados por política), el acceso no abriría nada.
    $lnk.TargetPath       = Join-Path $env:WINDIR "System32\wscript.exe"
    $lnk.Arguments        = "`"$vbs`""
    $lnk.WorkingDirectory = $Codigo
    $lnk.IconLocation     = "$Icono,0"
    $lnk.Description      = $descripcion
    $lnk.Save()
}

$MenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\MV Kobra AI"
$Escritorio = [Environment]::GetFolderPath("Desktop")
$desc = "$Nombre - Plataforma de Cobranzas Inteligentes"
Nuevo-Acceso (Join-Path $MenuDir "$Nombre.lnk") $Vbs $desc
Nuevo-Acceso (Join-Path $Escritorio "$Nombre.lnk") $Vbs $desc

# Segundo acceso (dashboard Streamlit): en el Escritorio Y en el Menú Inicio.
# Va en los dos lados a propósito — para el cliente cuyo sistemas no deja
# abrir .exe, ESTA es su puerta de entrada al producto, no una alternativa
# escondida. El nombre lo deja claro y el desinstalador lo borra igual.
$NombreAlterno = "$Nombre - $SufijoAlterno"
if ($LauncherAlterno) {
    $VbsAlterno = Nuevo-Lanzador "MVKobraAI_Alterno" $LauncherAlterno
    $descAlt = "$NombreAlterno - se abre en el navegador, sin ejecutables"
    Nuevo-Acceso (Join-Path $MenuDir "$NombreAlterno.lnk") $VbsAlterno $descAlt
    Nuevo-Acceso (Join-Path $Escritorio "$NombreAlterno.lnk") $VbsAlterno $descAlt
}

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
