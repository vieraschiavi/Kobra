<#
    MV Kobra AI · Desinstalación en Windows
    =======================================
    Quita los accesos directos, la entrada de «Agregar o quitar programas» y el
    entorno de Python.

    **Los datos NO se borran salvo que se pidan con -BorrarDatos.** Es el mismo
    criterio del instalador .exe (`deleteAppDataOnUninstall: false`): quien
    reinstala no pierde su cartera ni su configuración, y una desinstalación no
    puede ser la forma accidental de perder datos de cobranza.

    Uso:
        powershell -ExecutionPolicy Bypass -File desinstalar_windows.ps1 `
            -Destino "C:\ruta\instalacion" -ClaveApp "MVKobraAI_Owner" [-BorrarDatos]
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Destino,
    [string]$ClaveApp = "MVKobraAI",
    # Borra también la carpeta de datos. Sin esto, los datos se conservan.
    [switch]$BorrarDatos,
    # No preguntar nada (para desinstalación desatendida).
    [switch]$Silencioso
)

$ErrorActionPreference = "Continue"
$Nombre = if ($ClaveApp -eq "MVKobraAI_Owner") { "MV Kobra AI (Owner)" } else { "MV Kobra AI" }

Write-Host ""
Write-Host "  Desinstalando $Nombre..."

# --- 1) Accesos directos ----------------------------------------------------
$MenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\MV Kobra AI"
$DirEscritorio = [Environment]::GetFolderPath("Desktop")
$Escritorio = Join-Path $DirEscritorio "$Nombre.lnk"
# El acceso del segundo modo (dashboard Streamlit) se borra por PATRÓN y no
# por nombre exacto: el sufijo lo elige quien instala (`-SufijoAlterno`), así
# que buscarlo literal dejaría el .lnk huérfano, y con él la carpeta del Menú
# Inicio sin vaciar — o sea, el programa "desinstalado" seguiría apareciendo.
$alternos = @()
foreach ($dir in @($DirEscritorio, $MenuDir)) {
    if (Test-Path -LiteralPath $dir) {
        $alternos += (Get-ChildItem -LiteralPath $dir -Filter "$Nombre - *.lnk" `
                      -File -ErrorAction SilentlyContinue |
                      Where-Object { $_.Name -ne "Desinstalar $Nombre.lnk" } |
                      ForEach-Object { $_.FullName })
    }
}
foreach ($ruta in @($Escritorio, (Join-Path $MenuDir "$Nombre.lnk"),
                    (Join-Path $MenuDir "Desinstalar $Nombre.lnk")) + $alternos) {
    if (Test-Path -LiteralPath $ruta) {
        Remove-Item -LiteralPath $ruta -Force -ErrorAction SilentlyContinue
        Write-Host "    - acceso quitado: $ruta"
    }
}
# La carpeta del Menú Inicio solo se borra si quedó vacía: la edición Owner y
# la de cliente comparten esa carpeta, y desinstalar una no puede dejar a la
# otra sin su acceso.
if ((Test-Path -LiteralPath $MenuDir) -and
    -not (Get-ChildItem -LiteralPath $MenuDir -Force -ErrorAction SilentlyContinue)) {
    Remove-Item -LiteralPath $MenuDir -Force -Recurse -ErrorAction SilentlyContinue
}

# --- 2) Agregar o quitar programas ------------------------------------------
$Reg = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\$ClaveApp"
if (Test-Path $Reg) {
    Remove-Item -Path $Reg -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "    - quitado de Agregar o quitar programas"
}

# --- 3) Datos del usuario ---------------------------------------------------
$Datos = Join-Path $Destino "datos"
$borrar = $BorrarDatos.IsPresent
if ((-not $borrar) -and (-not $Silencioso) -and (Test-Path -LiteralPath $Datos)) {
    Write-Host ""
    Write-Host "    Tus datos (cartera, gestiones, configuracion) estan en:"
    Write-Host "      $Datos"
    $r = Read-Host "    Borrarlos tambien? Escribi BORRAR para eliminarlos, o Enter para conservarlos"
    $borrar = ($r -eq "BORRAR")
}
if ($borrar -and (Test-Path -LiteralPath $Datos)) {
    Remove-Item -LiteralPath $Datos -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "    - datos borrados"
} elseif (Test-Path -LiteralPath $Datos) {
    Write-Host "    - datos CONSERVADOS en $Datos"
}

# --- 4) Entorno y archivos de la instalación --------------------------------
# El script se está ejecutando desde $Destino, así que no puede borrarse a sí
# mismo mientras corre: se borra el contenido y se deja una tarea diferida que
# limpia la carpeta cuando el proceso termina.
foreach ($sub in @("entorno", "temp")) {
    $p = Join-Path $Destino $sub
    if (Test-Path -LiteralPath $p) {
        Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "    - $sub borrado"
    }
}
foreach ($f in @("MVKobraAI.cmd", "MVKobraAI.vbs", "MVKobraAI.ico",
                 "MVKobraAI_Alterno.cmd", "MVKobraAI_Alterno.vbs")) {
    $p = Join-Path $Destino $f
    if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue }
}

# La memoria de "dónde instalar" del .bat de código: si queda, la próxima
# instalación propone una carpeta que ya no existe.
$memoria = Join-Path $env:LOCALAPPDATA "MV Kobra AI\owner_destino.txt"
if (Test-Path -LiteralPath $memoria) { Remove-Item -LiteralPath $memoria -Force -ErrorAction SilentlyContinue }

Write-Host ""
Write-Host "  Listo. $Nombre fue desinstalado."
if (-not $borrar -and (Test-Path -LiteralPath $Datos)) {
    Write-Host "  Tus datos siguen en: $Datos"
    Write-Host "  (borra esa carpeta a mano si ya no los necesitas)"
}
Write-Host ""
