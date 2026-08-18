# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Empaquetador de releases
=======================================
Arma los dos paquetes distribuibles, listos para entregar como software:

  dist/MVKobraAI_Demo_v{VERSION}.zip        → para prospectos: doble clic y corre
                                          (dashboard offline, sin instalar nada)
  dist/MVKobraAI_Produccion_v{VERSION}.zip  → software completo con instalador
                                          (Docker o Python), manual y licencia

Ambos incluyen lanzadores para Windows (.bat) y Linux/Mac (.sh), LEEME,
licencia, VERSION y checksums SHA-256. `referencia_R/`, `.git` y artefactos
pesados no distribuibles quedan fuera.

Uso:
    python packaging/build_release.py
"""
import hashlib
import os
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# La versión sale de `kobra/__init__.py` y no de una constante propia. Acá
# había un "1.4.0" escrito a mano, y el número que anuncia el paquete no puede
# ser distinto del que reporta el programa: el CI arma el instalador con
# `kobra.__version__` y este script escribía otro en el nombre del ZIP y en la
# licencia. Un cliente que reporta "tengo la 1.4.0" no sirve de nada si esa
# etiqueta no dice qué código tiene adentro.
sys.path.insert(0, ROOT)
from kobra import __version__ as VERSION  # noqa: E402

DIST = os.path.join(ROOT, "dist")

# ---------------------------------------------------------------------------
# Textos comunes
# ---------------------------------------------------------------------------
LICENCIA_DEMO = f"""MV KOBRA AI · LICENCIA DE EVALUACIÓN (DEMO) · v{VERSION}
=====================================================

Este paquete es una DEMOSTRACIÓN de MV Kobra AI, Plataforma de Cobranzas
Inteligentes, con DATOS 100% SINTÉTICOS (sin datos de personas reales).

1. Se concede permiso de uso únicamente para EVALUACIÓN interna del
   producto. No incluye derecho de uso productivo ni comercial.
2. Prohibida la redistribución, modificación, ingeniería inversa o
   publicación de este software sin autorización escrita del titular.
3. Las métricas de impacto y de modelo incluidas son ILUSTRATIVAS de la
   metodología; no constituyen resultados medidos ni promesa de resultados.
4. El software se entrega "TAL CUAL", sin garantías de ningún tipo.
5. Todos los derechos reservados al titular de MV Kobra AI.

(Borrador comercial: revisar con asesoría legal antes de distribuir.)
"""

LICENCIA_PROD = f"""MV KOBRA AI · CONTRATO DE LICENCIA DE USO (EULA) · v{VERSION}
========================================================

1. OBJETO. El titular de MV Kobra AI concede al cliente una licencia de uso, no
   exclusiva e intransferible, del software MV Kobra AI (Plataforma de Cobranzas
   Inteligentes) para uso interno, según la propuesta comercial acordada.
2. PROPIEDAD. El software, su código, diseño y documentación son propiedad
   del titular. Esta licencia no transfiere titularidad alguna.
3. DATOS. El cliente es responsable de los datos que cargue (incl. Ley
   18.331 de Protección de Datos Personales de Uruguay). El paquete se
   distribuye con datos sintéticos, sin información personal real.
4. ALCANCE HONESTO. Las métricas de la demo son ilustrativas de la
   metodología. El desempeño real (modelo e impacto) se mide durante el
   piloto/implementación con datos del cliente.
5. RESTRICCIONES. Prohibida la redistribución, sublicencia, ingeniería
   inversa y remoción de avisos de titularidad.
6. GARANTÍA Y RESPONSABILIDAD. Salvo pacto escrito, el software se entrega
   "TAL CUAL"; la responsabilidad total queda limitada a lo abonado por la
   licencia en los últimos 12 meses.
7. LEY APLICABLE. República Oriental del Uruguay.

(Borrador comercial: revisar y completar con asesoría legal antes de firmar.)
"""


def _write(path, content=None, crlf=False, **kw):
    """Escribe un archivo del paquete. `crlf` = destino Windows.

    El BOM va en los .txt y NO en los .bat. Los .txt lo necesitan para que el
    Bloc de notas muestre bien los acentos; en un .bat es un defecto: cmd.exe
    no lo saltea, se lo come como parte del primer comando y la ventana
    arranca con «'∩╗┐@echo' no se reconoce como un comando interno o externo».

    No se había notado porque los .bat que se venían usando son los del repo
    (sin BOM, escritos a mano). Los 8 .bat que genera este script sí lo
    llevaban — y son justamente los que va a abrir quien descargue un ZIP.
    """
    if content is None:
        content = kw["content"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if crlf:
        content = content.replace("\n", "\r\n")
    ejecutable = os.path.splitext(path)[1].lower() in (".bat", ".cmd")
    codec = "utf-8" if (ejecutable or not crlf) else "utf-8-sig"
    with open(path, "w", encoding=codec, newline="") as f:
        f.write(content)


def _ascii(texto):
    """Transliterá a ASCII el texto que va DENTRO de un .bat.

    Un .bat no se interpreta en UTF-8: cmd.exe lo lee en la code page de la
    consola (850/437 en un Windows en español). El archivo se escribe en UTF-8
    porque lo necesita el resto del contenido, así que la única forma de que la
    barra de título y los `echo` se lean bien es que ese texto sea ASCII de
    entrada — «Owner (dueño del producto · sin límites)» salía como
    «due├▒o ┬╖ sin l├¡mites».

    Se aplica a los títulos de edición, que es el único texto del .bat que no
    escribimos a mano acá (viene de EDICIONES y lleva ñ, tildes y «·»).
    """
    import unicodedata
    for viejo, nuevo in {"·": "-", "—": "-", "–": "-", "…": "...",
                         "“": '"', "”": '"', "‘": "'", "’": "'"}.items():
        texto = texto.replace(viejo, nuevo)
    return (unicodedata.normalize("NFKD", texto)
            .encode("ascii", "ignore").decode("ascii"))


def _copy(src_rel, dst):
    src = os.path.join(ROOT, src_rel)
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    elif os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def _zipdir(staging, zpath):
    os.makedirs(DIST, exist_ok=True)
    if os.path.exists(zpath):
        os.remove(zpath)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for base, _dirs, files in os.walk(staging):
            for fn in files:
                full = os.path.join(base, fn)
                z.write(full, os.path.relpath(full, staging))
    return zpath


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Bloques de batch compartidos por los instaladores
# ---------------------------------------------------------------------------
# Los instaladores que genera este script (INSTALAR.bat de cada edición e
# INSTALAR_Y_EJECUTAR.bat de producción) tienen que hacer lo mismo antes de
# escribir un solo byte: preguntar la carpeta, limpiar lo que el usuario tipeó,
# comprobar que se puede escribir ahí y medir el espacio de ESE disco.
#
# Se emiten desde acá en vez de copiarse a mano en cada string porque son las
# mismas decisiones que ya estaban peleadas en
# `owner/MVKobraAI_Owner_desde_codigo.bat` a golpe de bugs reportados desde
# instalaciones reales: medir el disco equivocado, no dejar elegir carpeta,
# romperse con una barra final, o descargar a `%TEMP%` (C:) y culpar a la red
# cuando lo que faltaba era espacio. Duplicarlas es garantizar que se arreglen
# en un lado y no en el otro.
#
# Todos los bloques asumen `setlocal enabledelayedexpansion` y dejan definidas
# `!DESTINO!`, `!DATOS!` y `!TRABAJO!`.

def _bat_elegir_carpeta(paso, total, memoria):
    """Pregunta la carpeta, la sanea, la crea y verifica que se pueda escribir.

    `memoria` es el nombre del archivo donde se recuerda la elección, para que
    la segunda vez alcance con dar Enter. Va en %LocalAppData% y no en la
    carpeta elegida: si estuviera adentro, no habría dónde leerlo antes de
    saber cuál es.
    """
    return f"""\
set "MEMORIA=%LocalAppData%\\MV Kobra AI\\{memoria}"
set "SUGERIDO=%LocalAppData%\\MV Kobra AI"
if exist "!MEMORIA!" (
  for /f "usebackq delims=" %%D in ("!MEMORIA!") do if not "%%D"=="" set "SUGERIDO=%%D"
)

echo [{paso}/{total}] Carpeta de instalacion
echo       Ahi van el entorno de Python y tus datos ^(hacen falta ~3 GB^).
echo.
echo       Enter = usar:  !SUGERIDO!
set "DESTINO="
set /p "DESTINO=      O escribi otra ruta (ej. D:\\MVKobraAI): "
if "!DESTINO!"=="" set "DESTINO=!SUGERIDO!"
rem Sacar comillas si el usuario arrastro la carpeta a la ventana.
set "DESTINO=!DESTINO:"=!"
rem Sacar la barra final: "D:\\Kobra\\" rompe cualquier ruta que se le concatene.
if "!DESTINO:~-1!"=="\\" set "DESTINO=!DESTINO:~0,-1!"

mkdir "!DESTINO!" >nul 2>nul
if not exist "!DESTINO!\\" (
  echo.
  echo   No pude crear ni abrir esa carpeta:
  echo     !DESTINO!
  echo   Revisa que la ruta sea valida y que tengas permiso de escritura.
  echo.
  pause & exit /b 1
)
rem Prueba de escritura real: una carpeta puede existir y ser de solo lectura.
echo ok> "!DESTINO!\\.kobra_prueba" 2>nul
if not exist "!DESTINO!\\.kobra_prueba" (
  echo.
  echo   Esa carpeta existe pero no puedo escribir en ella:
  echo     !DESTINO!
  echo   Elegi otra ^(o ejecuta como administrador si es del sistema^).
  echo.
  pause & exit /b 1
)
del "!DESTINO!\\.kobra_prueba" >nul 2>nul

set "VENV=!DESTINO!\\entorno"
set "DATOS=!DESTINO!\\datos"
set "TRABAJO=!DESTINO!\\temp"
mkdir "!DATOS!" >nul 2>nul
mkdir "!TRABAJO!" >nul 2>nul
mkdir "%LocalAppData%\\MV Kobra AI" >nul 2>nul
>"!MEMORIA!" echo !DESTINO!
echo       Instalando en: !DESTINO!
"""


def _bat_espacio(paso, total, gb=3):
    """Mide el disco de la carpeta ELEGIDA y frena si no entra."""
    return f"""\
echo.
echo [{paso}/{total}] Espacio en disco
call :libres "!DESTINO!" LIBRE_DESTINO
if "!LIBRE_DESTINO!"=="?" (
  echo       No pude medir el espacio libre. Sigo igual.
) else (
  echo       Disponible en !DESTINO!: ~!LIBRE_DESTINO! GB
  if !LIBRE_DESTINO! LSS {gb} (
    echo.
    echo   ^(!^) Muy poco espacio ^(~!LIBRE_DESTINO! GB^). Hacen falta unos {gb} GB
    echo   para descargar e instalar las dependencias.
    echo   Volve a ejecutar y elegi una carpeta en un disco con mas lugar
    echo   ^(ej. D:\\MVKobraAI^).
    echo.
    pause & exit /b 1
  )
)
"""


def _bat_sub_libres():
    """Subrutina `:libres` — va al final del .bat, después de `exit /b 0`.

    PowerShell y no `dir`: el parseo de `dir` depende del idioma de Windows y
    del separador de miles. DriveInfo devuelve los bytes del volumen real de la
    ruta (sirve también con unidades de red y con subst).
    """
    return """\
rem =========================================================================
rem  :libres <ruta> <variable>  -> GB libres en el volumen de <ruta>, o "?"
rem  La ruta viaja por variable de entorno y no incrustada en el comando: asi
rem  no hay que escapar comillas, espacios ni parentesis de "C:\\Program Files".
rem =========================================================================
:libres
set "%~2=?"
set "KOBRA_RUTA_MEDIR=%~1"
set "KOBRA_RESP_MEDIR=%~1\\.kobra_libres.txt"
del "!KOBRA_RESP_MEDIR!" >nul 2>nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $p = (Get-Item -LiteralPath $env:KOBRA_RUTA_MEDIR).FullName; $d = New-Object System.IO.DriveInfo $p; [math]::Floor($d.AvailableFreeSpace/1GB) | Set-Content -LiteralPath $env:KOBRA_RESP_MEDIR } catch { }" >nul 2>nul
if exist "!KOBRA_RESP_MEDIR!" (
  for /f "usebackq delims= " %%G in ("!KOBRA_RESP_MEDIR!") do if not "%%G"=="" set "%~2=%%G"
)
del "!KOBRA_RESP_MEDIR!" >nul 2>nul
set "KOBRA_RUTA_MEDIR="
set "KOBRA_RESP_MEDIR="
exit /b 0
"""


def _bat_python(paso, total):
    """Busca Python; si no está, lo descarga AL DISCO ELEGIDO e instala.

    Al disco elegido y no a `%TEMP%`: con C: lleno, bajar a `%TEMP%` falla con
    un error de red engañoso ("¿sin internet?") cuando lo que falta es espacio.
    """
    return f"""\
echo.
set "PYEXE="
where python >nul 2>nul && set "PYEXE=python"
if not "!PYEXE!"=="" (
  echo [{paso}/{total}] Python: OK
) else (
  echo [{paso}/{total}] Python no encontrado. Descargando e instalando Python 3.11...
  echo       ^(usa PowerShell, incluido en Windows - no requiere winget^)
  set "PYINST=!TRABAJO!\\python311_kobra.exe"
  set "KOBRA_PY_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
  set "KOBRA_PY_DEST=!PYINST!"
  set "KOBRA_PY_ERR=!TRABAJO!\\python_descarga_error.txt"
  del "!KOBRA_PY_ERR!" >nul 2>nul
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try {{ Invoke-WebRequest -Uri $env:KOBRA_PY_URL -OutFile $env:KOBRA_PY_DEST -UseBasicParsing }} catch {{ $_.Exception.Message ^| Set-Content -LiteralPath $env:KOBRA_PY_ERR }}"
  if not exist "!PYINST!" (
    echo.
    echo   No pude descargar Python. Motivo exacto:
    if exist "!KOBRA_PY_ERR!" (type "!KOBRA_PY_ERR!") else (echo     ^(sin detalle^))
    echo.
    echo   Si habla de ESPACIO: libera lugar, o volve a ejecutar y elegi una
    echo   carpeta en un disco con mas lugar.
    echo   Si habla de RED: revisa la conexion, o instala Python a mano desde
    echo   https://www.python.org/downloads/ marcando "Add Python to PATH".
    echo.
    pause & exit /b 1
  )
  echo       Instalando Python en silencio ^(solo para tu usuario, sin admin^)...
  rem TargetDir: sin esto, el instalador oficial de python.org SIEMPRE pone el
  rem interprete en %LocalAppData%\\Programs\\Python\\Python311 - que vive en
  rem C: - sin importar que disco se haya elegido para todo lo demas. Con C:
  rem justo de espacio (el motivo original de este instalador), instalar ahi
  rem podia volver a fallar por lo mismo que se vino a arreglar. TargetDir es
  rem una propiedad documentada del instalador y funciona con o sin
  rem InstallAllUsers.
  set "PYDIR=!DESTINO!\\python311"
  "!PYINST!" /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 TargetDir="!PYDIR!"
  set "PYRC=!errorlevel!"
  rem PrependPath=0 e Include_launcher=0 a proposito: PrependPath tocaria el
  rem PATH del usuario con una ruta que vive dentro de la carpeta elegida (si
  rem el usuario la borra despues, el PATH queda roto) y el lanzador py.exe se
  rem registra fuera de TargetDir de cualquier forma. Ninguno de los dos hace
  rem falta: ya se guarda la ruta exacta a PYEXE.
  del "!PYINST!" >nul 2>nul
  rem Buscar el interprete: primero donde lo pedimos, y si el instalador
  rem ignoro TargetDir, en las rutas por defecto. Antes solo se miraba PYDIR.
  for %%P in (
    "!PYDIR!\\python.exe"
    "%LocalAppData%\\Programs\\Python\\Python311\\python.exe"
    "%ProgramFiles%\\Python311\\python.exe"
  ) do if not defined PYEXE if exist "%%~P" set "PYEXE=%%~P"
  rem Que exista el .exe no alcanza: una instalacion a medias deja el archivo
  rem pero el interprete no arranca. Se comprueba corriendolo.
  if defined PYEXE (
    "!PYEXE!" --version >nul 2>nul
    if not !errorlevel!==0 set "PYEXE="
  )
  if not defined PYEXE (
    echo.
    echo   Python no quedo usable. Codigo de salida del instalador: !PYRC!
    echo     0    = OK          1602 = lo cancelaste
    echo     1603 = error fatal ^(permisos o espacio^)
    echo     3010 = pide reiniciar Windows
    echo.
    echo   Busque el interprete en:
    echo     !PYDIR!\\python.exe
    echo     %LocalAppData%\\Programs\\Python\\Python311\\python.exe
    echo     %ProgramFiles%\\Python311\\python.exe
    echo.
    echo   Que hacer:
    echo     - Reintenta eligiendo otra carpeta ^(por ejemplo C:\\MVKobraAI^).
    echo     - O instala Python 3.11 a mano desde
    echo       https://www.python.org/downloads/ marcando "Add Python to PATH",
    echo       y volve a ejecutar: lo detecta solo.
    echo.
    rem exit /b 1 y NO /b 0: antes salia como si todo hubiera ido bien y pedia
    rem "volve a ejecutar para que Windows lo tome" - imposible, porque con
    rem PrependPath=0 Python nunca entra al PATH. El usuario reabria, se
    rem re-descargaba, se re-instalaba y volvia a salir por aca: un bucle que
    rem dejaba la carpeta elegida vacia (solo datos\\ y temp\\).
    pause & exit /b 1
  )
)
"""


def _bat_entorno_y_deps(paso_venv, paso_deps, total, req="!CODIGO!\\requirements.txt"):
    """Crea el venv en la carpeta elegida e instala dependencias ahí.

    TEMP/TMP/TMPDIR: pip descomprime en el temporal del sistema aunque se le
    pase --no-cache-dir. Si ese temporal queda en C:, elegir D: no cambia nada
    y el ENOSPC vuelve igual. Se ponen las tres porque `tempfile` de Python las
    mira en orden TMPDIR -> TEMP -> TMP y basta con que una apunte al disco
    lleno.
    """
    return f"""\
echo.
if not exist "!VENV!\\Scripts\\python.exe" (
  echo [{paso_venv}/{total}] Creando entorno propio...
  "!PYEXE!" -m venv "!VENV!"
) else (
  echo [{paso_venv}/{total}] Entorno propio: OK
)
set "VPY=!VENV!\\Scripts\\python.exe"
if not exist "!VPY!" (
  echo.
  echo   No se pudo crear el entorno en !VENV!.
  echo   Proba elegir otra carpeta al volver a ejecutar.
  echo.
  pause & exit /b 1
)

echo.
echo [{paso_deps}/{total}] Instalando dependencias ^(la 1a vez tarda unos minutos^)...
set "TEMP=!TRABAJO!"
set "TMP=!TRABAJO!"
set "TMPDIR=!TRABAJO!"
"!VPY!" -m pip install --no-cache-dir --upgrade pip >nul 2>nul
"!VPY!" -m pip install --no-cache-dir -r "{req}"
if not !errorlevel!==0 (
  echo.
  echo   Fallo la instalacion de dependencias.
  echo   Si dice "No space left on device": volve a ejecutar y elegi una
  echo   carpeta en un disco con mas lugar - todo (descarga incluida) va al
  echo   disco que elegis, asi que con eso alcanza.
  echo   Si es otro error, revisa tu conexion y reintenta: lo que ya se
  echo   instalo no se vuelve a bajar.
  echo.
  pause & exit /b 1
)
"""


# ---------------------------------------------------------------------------
# Paquete DEMO
# ---------------------------------------------------------------------------
def _prerenderizar_voz_demo():
    """Sintetiza el chatvoice de la demo con la voz del video oficial y lo deja
    en `dashboard_estatico/audio_demo/` para que _copy() lo incluya en el ZIP.

    Usa el clonador LOCAL si está instalado (gratis, sin mandar la voz a un
    tercero) y cae a ElevenLabs solo si no hay local y hay API key.

    El audio está versionado en el repo (lo sirve el sitio, no solo el ZIP), así
    que **no se borra si no hay con qué regenerarlo**: en una máquina sin motor
    de voz, limpiar primero dejaba el árbol de trabajo sin los MP3 y el paquete
    sin voz, por un build que no tenía nada que ver. Cuando sí hay motor se
    limpia, para no arrastrar audio de un guion viejo."""
    audio_dir = os.path.join(ROOT, "dashboard_estatico", "audio_demo")
    import sys as _sys
    if ROOT not in _sys.path:
        _sys.path.insert(0, ROOT)
    from data import generar_audio_demo_voz as gav
    modulo, _, motivo = gav.elegir_motor()
    if modulo is None:
        print(f"[SKIP] Voz del demo: {motivo} "
              "(se conserva el audio ya versionado).")
        return

    # Borrar y regenerar dentro del árbol de trabajo no es reversible: si el
    # build se corta a mitad —Ctrl-C, timeout, un error de síntesis— el audio
    # versionado queda destruido y el repo, roto. Pasó: una corrida
    # interrumpida dejó `en/` sin un solo MP3 y `pt/` con 6 de 9.
    # Por eso se guarda una copia antes y se restaura ante cualquier fallo.
    respaldo = None
    if os.path.isdir(audio_dir):
        respaldo = audio_dir + ".respaldo"
        shutil.rmtree(respaldo, ignore_errors=True)
        shutil.copytree(audio_dir, respaldo)
    try:
        shutil.rmtree(audio_dir, ignore_errors=True)
        # Los tres idiomas del producto: elegir portugués o inglés no cambiaba
        # el audio, que estaba pre-renderizado solo en castellano.
        resumen = gav.generar_todos()
    except BaseException:      # incluye KeyboardInterrupt y SystemExit
        if respaldo:
            shutil.rmtree(audio_dir, ignore_errors=True)
            shutil.move(respaldo, audio_dir)
            print("[AVISO] Falló la síntesis: se restauró el audio versionado.")
        raise
    finally:
        if respaldo and os.path.isdir(respaldo):
            shutil.rmtree(respaldo, ignore_errors=True)
    total = sum(r["generados"] for r in resumen.values())
    if total:
        costo = sum(r["costo_est_usd"] for r in resumen.values())
        detalle = next(iter(resumen.values())).get("detalle_motor", "")
        por_idioma = " · ".join(f"{k}: {v['generados']}" for k, v in resumen.items())
        print(f"[OK] Voz del demo ({detalle}): {total} audio(s) "
              f"[{por_idioma}], "
              + (f"costo est. USD {round(costo, 4)}." if costo else "sin costo."))
    else:
        primero = next(iter(resumen.values()), {})
        print(f"[SKIP] Voz del demo: {primero.get('motivo', 'sin generar')}")


def build_demo(tmp):
    stage = os.path.join(tmp, f"MVKobraAI_Demo_v{VERSION}")
    shutil.rmtree(stage, ignore_errors=True)

    _prerenderizar_voz_demo()
    # Dashboard offline completo (corre con doble clic, sin instalar nada)
    _copy("dashboard_estatico", os.path.join(stage, "dashboard"))
    # Reportes Excel de ejemplo
    _copy("outputs/kobra_scored.xlsx",
          os.path.join(stage, "reportes_excel", "MVKobraAI_Cartera_Scoreada.xlsx"))
    _copy("outputs/kobra_analitica_gestion.xlsx",
          os.path.join(stage, "reportes_excel", "MVKobraAI_Analitica_Gestion.xlsx"))
    # Presentación gerencial
    _copy("presentation/MVKobraAI_Presentacion_Gerencial.pptx",
          os.path.join(stage, "presentacion", "MVKobraAI_Presentacion_Gerencial.pptx"))
    # Capturas del producto completo
    for img in ("dashboard_overview.png", "dashboard_negociador.png",
                "realtime_copiloto.png", "dashboard_gestores.png"):
        _copy(f"assets/{img}", os.path.join(stage, "capturas", img))
    # Video demo del copiloto en vivo + identidad de marca
    _copy("assets/video/MVKobraAI_Copiloto_Demo.mp4",
          os.path.join(stage, "video", "MVKobraAI_Copiloto_Demo.mp4"))
    _copy("assets/brand/mv.ico", os.path.join(stage, "mv.ico"))
    _copy("assets/brand/mv_wordmark.png",
          os.path.join(stage, "mv_logo.png"))

    # Lanzadores
    _write(os.path.join(stage, "INICIAR_DEMO.bat"),
           "@echo off\r\n"
           "title MV Kobra AI - Demo\r\n"
           "echo Abriendo la demo de MV Kobra AI en su navegador...\r\n"
           "start \"\" \"%~dp0dashboard\\index.html\"\r\n"
           "exit\r\n")
    _write(os.path.join(stage, "iniciar_demo.sh"),
           "#!/usr/bin/env bash\n"
           "cd \"$(dirname \"$0\")\"\n"
           "xdg-open dashboard/index.html 2>/dev/null || open dashboard/index.html\n")
    # autorun.inf: solo surte efecto en CD/DVD (Windows lo bloquea en USB/carpetas
    # por seguridad desde Win7); se incluye por compatibilidad con medios ópticos.
    _write(os.path.join(stage, "autorun.inf"),
           "[autorun]\r\nopen=INICIAR_DEMO.bat\r\nicon=mv.ico\r\n"
           "label=MV Kobra AI Demo\r\n")

    _write(os.path.join(stage, "LEEME.txt"), crlf=True, content=f"""MV KOBRA AI · DEMO v{VERSION}
Plataforma de Cobranzas Inteligentes
=====================================

CÓMO VER LA DEMO (no requiere instalar nada):

  ► Windows : doble clic en  INICIAR_DEMO.bat
  ► Mac/Linux: ejecutar      ./iniciar_demo.sh
  ► Manual  : abrir          dashboard/index.html  en cualquier navegador

QUÉ INCLUYE
  dashboard/        Dashboard interactivo offline: KPIs, filtros, gráficos,
                    cartera priorizada, export a Excel/CSV y el Copiloto de
                    Negociación (análisis de sentimiento) corriendo en su
                    navegador, sin conexión.
  video/            Video demo del Copiloto EN VIVO asesorando durante una
                    llamada (KPIs, sentimiento y próxima frase en tiempo real).
  reportes_excel/   Reportes de ejemplo listos para abrir en Excel.
  presentacion/     Presentación gerencial (PPTX).
  capturas/         Vistas del producto completo (copiloto de voz en vivo,
                    analítica de gestores, integración telefónica).
  mv_logo.png / mv.ico   Identidad de marca.

IMPORTANTE — HONESTIDAD DE LOS DATOS
  Esta demo usa datos 100% SINTÉTICOS (sin personas reales). Las métricas de
  impacto y de modelo son ILUSTRATIVAS de la metodología: el desempeño real
  se mide con la cartera de su empresa durante un piloto.

VERSIÓN COMPLETA
  La versión de producción agrega: modelo ProbPago entrenable con su cartera,
  copiloto de voz EN VIVO (transcripción + emoción de voz), integración con
  su central telefónica (Avaya, Genesys, Twilio…), analítica por gestor/mes
  y despliegue con Docker. Solicite el paquete "MV Kobra AI Producción".

Licencia de evaluación: ver LICENCIA.txt
""")
    _write(os.path.join(stage, "LICENCIA.txt"), LICENCIA_DEMO, crlf=True)
    _write(os.path.join(stage, "VERSION.txt"),
           f"MV Kobra AI Demo v{VERSION}\nDatos sintéticos · sin información personal real\n",
           crlf=True)

    os.chmod(os.path.join(stage, "iniciar_demo.sh"), 0o755)
    return _zipdir(stage, os.path.join(DIST, f"MVKobraAI_Demo_v{VERSION}.zip"))


# ---------------------------------------------------------------------------
# Paquete PRODUCCIÓN
# ---------------------------------------------------------------------------
PROD_ITEMS = [
    "kobra", "app", "realtime", "tests", "dashboard_estatico",
    "data/generate_dataset.py", "data/generate_gestiones.py",
    "data/generate_audio_demo.py", "data/ejemplo_whatsapp.txt",
    "presentation/build_ppt.py", "assets/brand",
    "requirements.txt", "run.sh", "Dockerfile", "docker-compose.yml",
    "docker-entrypoint.sh", ".dockerignore", "README.md",
    "MANUAL_PUESTA_EN_MARCHA.md", ".github",
    # Instalación real en Windows (icono, Menú Inicio, desinstalador). Faltaban
    # acá: producción traía un .bat que levantaba Streamlit y nada más, así que
    # era la única edición que no quedaba "instalada" en ningún lado.
    "packaging/instalar_windows.ps1", "packaging/desinstalar_windows.ps1",
    "electron/build/icon.ico",
]


def build_prod(tmp):
    stage = os.path.join(tmp, f"MVKobraAI_Produccion_v{VERSION}")
    shutil.rmtree(stage, ignore_errors=True)

    for item in PROD_ITEMS:
        _copy(item, os.path.join(stage, "kobra_software", item))
    # Presentación lista para usar
    _copy("presentation/MVKobraAI_Presentacion_Gerencial.pptx",
          os.path.join(stage, "presentacion", "MVKobraAI_Presentacion_Gerencial.pptx"))

    # El lanzador de Streamlit va en la RAÍZ de kobra_software, igual que
    # kobra_launcher.py en las otras ediciones: es el destino del acceso directo.
    _copy("packaging/kobra_streamlit.py", os.path.join(stage, "kobra_software",
                                                       "kobra_streamlit.py"))

    # INSTALAR_Y_EJECUTAR.bat — antes levantaba Streamlit y nada más: no
    # preguntaba carpeta, no medía disco, no dejaba icono en ningún lado y
    # usaba el 8501 fijo (si otra app lo tenía, fallaba o se corría sin avisar).
    # Ahora la instalación normal es la de siempre del resto de las ediciones, y
    # Docker queda como opción explícita para servidor.
    N = 6
    _write(os.path.join(stage, "INSTALAR_Y_EJECUTAR.bat"), crlf=True, content=(
        "@echo off\n"
        "setlocal enabledelayedexpansion\n"
        "title MV Kobra AI - Instalador\n"
        "cd /d \"%~dp0\"\n"
        "set \"CODIGO=%CD%\\kobra_software\"\n"
        "\n"
        "echo ============================================================\n"
        "echo   MV Kobra AI - Produccion\n"
        "echo ============================================================\n"
        "echo.\n"
        "echo   Como queres instalarlo?\n"
        "echo     [1] Normal (recomendado): elegis la carpeta y queda con\n"
        "echo         icono en el Escritorio y en el Menu Inicio.\n"
        "echo     [2] Con Docker (servidor): dashboard + copiloto en contenedores.\n"
        "echo.\n"
        "set \"MODO=1\"\n"
        "set /p \"MODO=  Opcion [1]: \"\n"
        "if \"!MODO!\"==\"2\" goto :docker\n"
        "\n"
        + _bat_elegir_carpeta(1, N, "destino_produccion.txt")
        + _bat_espacio(2, N)
        + _bat_python(3, N)
        + _bat_entorno_y_deps(4, 5, N)
        + "\n"
        "echo.\n"
        f"echo [6/{N}] Dejando el programa instalado ^(icono, Menu Inicio, desinstalador^)...\n"
        "set \"PYW=!VENV!\\Scripts\\pythonw.exe\"\n"
        "if not exist \"!PYW!\" set \"PYW=!VPY!\"\n"
        "powershell -NoProfile -ExecutionPolicy Bypass -File "
        "\"!CODIGO!\\packaging\\instalar_windows.ps1\" -Destino \"!DESTINO!\" "
        "-Codigo \"!CODIGO!\" -Python \"!PYW!\" -Datos \"!DATOS!\" "
        f"-Version \"{VERSION}\" -Lanzador \"kobra_streamlit.py\"\n"
        "if errorlevel 1 (\n"
        "  echo.\n"
        "  echo   Fallo la instalacion de los accesos. El programa igual arranca\n"
        "  echo   volviendo a ejecutar este .bat.\n"
        ")\n"
        "\n"
        "echo.\n"
        "echo   Preparando datos sinteticos y modelo ^(solo la 1a vez^)...\n"
        "set \"KOBRA_DATA_DIR=!DATOS!\"\n"
        "\"!VPY!\" \"!CODIGO!\\data\\generate_dataset.py\" --n 12000 --seed 42\n"
        "\"!VPY!\" -m kobra.pipeline\n"
        "\n"
        "echo.\n"
        "echo   Iniciando el dashboard...\n"
        "rem kobra_streamlit.py y no `streamlit run`: elige un puerto libre en\n"
        "rem vez de asumir el 8501, que suele estar tomado por otra cosa.\n"
        "\"!VPY!\" \"!CODIGO!\\kobra_streamlit.py\"\n"
        "pause\n"
        "exit /b 0\n"
        "\n"
        ":docker\n"
        "cd /d \"!CODIGO!\"\n"
        "where docker >nul 2>nul\n"
        "if not %errorlevel%==0 (\n"
        "  echo.\n"
        "  echo   No encontre Docker. Instala Docker Desktop, o volve a ejecutar\n"
        "  echo   y elegi la opcion [1].\n"
        "  echo.\n"
        "  pause & exit /b 1\n"
        ")\n"
        "echo   Levantando dashboard y servicio de audio en contenedores...\n"
        "rem Docker publica 8501 y 8000 fijos (docker-compose.yml). Si otra app\n"
        "rem los tiene, `docker compose up` falla con un error claro de puerto\n"
        "rem ocupado - preferible a arrancar encima de la otra aplicacion.\n"
        "docker compose up --build -d\n"
        "if not %errorlevel%==0 (\n"
        "  echo.\n"
        "  echo   No pude levantar los contenedores. Si el error habla de un\n"
        "  echo   puerto ocupado ^(8501 o 8000^), libera ese puerto o usa la\n"
        "  echo   opcion [1], que elige un puerto libre sola.\n"
        "  echo.\n"
        "  pause & exit /b 1\n"
        ")\n"
        "echo.\n"
        "echo   Dashboard:  http://localhost:8501\n"
        "echo   Realtime :  http://localhost:8000\n"
        "start \"\" http://localhost:8501\n"
        "pause\n"
        "exit /b 0\n"
        "\n"
        + _bat_sub_libres()))
    _write(os.path.join(stage, "instalar_y_ejecutar.sh"),
           "#!/usr/bin/env bash\n"
           "set -e\n"
           "cd \"$(dirname \"$0\")/kobra_software\"\n"
           "if command -v docker >/dev/null 2>&1; then\n"
           "  echo '[MV Kobra AI] Docker detectado. Levantando servicios...'\n"
           "  docker compose up --build -d\n"
           "  echo '  Dashboard:  http://localhost:8501'\n"
           "  echo '  Realtime :  http://localhost:8000'\n"
           "else\n"
           "  echo '[MV Kobra AI] Docker no encontrado. Instalación con Python local...'\n"
           "  pip3 install -r requirements.txt\n"
           "  python3 data/generate_dataset.py --n 12000 --seed 42\n"
           "  python3 -m kobra.pipeline\n"
           "  streamlit run app/app.py\n"
           "fi\n")

    _write(os.path.join(stage, "LEEME_PRIMERO.txt"), crlf=True, content=f"""MV KOBRA AI · PRODUCCIÓN v{VERSION}
Plataforma de Cobranzas Inteligentes
=====================================

INSTALACIÓN EN 1 PASO
  ► Windows : doble clic en  INSTALAR_Y_EJECUTAR.bat
  ► Linux/Mac: ejecutar      ./instalar_y_ejecutar.sh

  Con Docker instalado (recomendado) levanta todo solo:
    Dashboard gerencial ......... http://localhost:8501
    Copiloto de audio en vivo ... http://localhost:8000
  Sin Docker, usa Python 3.11+ local.

PRIMEROS PASOS (detalle en kobra_software/MANUAL_PUESTA_EN_MARCHA.md)
  1. Configurar API keys (una sola vez): Dashboard → pestaña Configuración.
  2. Cargar la cartera real (mismo esquema que data/generate_dataset.py)
     y correr:  python -m kobra.pipeline
  3. Conectar la central telefónica (Avaya/Genesys/Twilio):
     grabación dual-channel o streaming (SIPREC / Media Streams / DMCC)
     → ver sección "Integración con telefonía" del README.
  4. Ciclo con el CTI: GET /brief/{{id_deudor}} antes de llamar; el registro
     post-llamada alimenta la pestaña "Gestores & Evolución" con datos reales.

CONTENIDO
  kobra_software/   Código completo, tests, Docker, manual y README.
  presentacion/     Presentación gerencial (PPTX).

HONESTIDAD DE LOS DATOS
  El paquete llega con datos SINTÉTICOS de demostración. Las métricas
  ilustran la metodología; el desempeño real se mide con su cartera
  (ver README → "Honestidad de los números").

Licencia de uso: ver LICENCIA.txt
""")
    _write(os.path.join(stage, "LICENCIA.txt"), LICENCIA_PROD, crlf=True)
    _write(os.path.join(stage, "VERSION.txt"),
           f"MV Kobra AI Producción v{VERSION}\n", crlf=True)

    os.chmod(os.path.join(stage, "instalar_y_ejecutar.sh"), 0o755)
    sh = os.path.join(stage, "kobra_software", "run.sh")
    if os.path.exists(sh):
        os.chmod(sh, 0o755)
    ep = os.path.join(stage, "kobra_software", "docker-entrypoint.sh")
    if os.path.exists(ep):
        os.chmod(ep, 0o755)
    return _zipdir(stage, os.path.join(DIST, f"MVKobraAI_Produccion_v{VERSION}.zip"))


# ---------------------------------------------------------------------------
# Ediciones runnables: Demo (con límite de días) · Owner · una por plan
# ---------------------------------------------------------------------------
# Runtime standalone mínimo para correr la webapp con doble clic (sin Node):
# núcleo + backend + gateway de licencias + datos demo + UI compilada + launcher.
_RUNTIME_ITEMS = [
    "kobra", "webapp/backend", "backend_venta", "realtime",
    "data/generate_dataset.py", "data/generate_gestiones.py",
    "data/generate_audio_demo.py", "data/ejemplo_whatsapp.txt",
    "outputs/kobra_scored.csv", "data/kobra_gestiones.csv",
    "owner/ui_dist", "assets/brand", "requirements.txt",
    # Dashboard Streamlit: es la SEGUNDA vía de arranque de cada edición.
    # Muchas empresas bloquean por política la ejecución de .exe bajados de
    # internet, pero no un .bat que corre Python — sin `app/` acá, esa vía no
    # existía y el cliente con la política estricta se quedaba sin producto.
    "app",
    # Instalación real en Windows (icono, Menú Inicio, desinstalador). Sin
    # esto el paquete corría pero no quedaba "instalado" en ningún lado: para
    # abrirlo había que acordarse de dónde estaba la carpeta descomprimida.
    "packaging/instalar_windows.ps1", "packaging/desinstalar_windows.ps1",
    "electron/build/icon.ico",
]

DEMO_DIAS = 14   # límite de la versión de evaluación

# Las DOS vías de arranque que lleva cada edición. Existen las dos a propósito:
# muchas empresas bloquean por política ejecutar un .exe bajado de internet,
# pero no correr un .bat — así el cliente con TI restrictiva igual usa el
# producto, sin pedirle nada al área de sistemas.
#   (sufijo del archivo, script Python, qué abre)
_MODOS = [
    ("", "kobra_launcher.py",
     "la app de escritorio (interfaz React)"),
    ("_STREAMLIT", "kobra_streamlit.py",
     "el dashboard Streamlit (misma info, sin ningun .exe)"),
]


def _bat_lanzador(titulo: str, key: str, script: str, que_abre: str) -> str:
    """.bat que abre el programa con el intérprete que haya a mano.

    Orden a propósito: primero el entorno que dejó INSTALAR.bat (tiene las
    dependencias), después el Python del sistema. Al revés, quien instaló
    arrancaría con un Python sin uvicorn/streamlit y vería un ImportError.
    """
    memoria = f"%LocalAppData%\\MV Kobra AI\\destino_{key.lower()}.txt"
    return (
        "@echo off\n"
        "setlocal enabledelayedexpansion\n"
        f"title MV Kobra AI - {_ascii(titulo)}\n"
        f"rem Abre {_ascii(que_abre)}.\n"
        "cd /d \"%~dp0kobra_software\"\n"
        f"set \"MEMORIA={memoria}\"\n"
        "if exist \"!MEMORIA!\" (\n"
        "  for /f \"usebackq delims=\" %%D in (\"!MEMORIA!\") do "
        "if exist \"%%D\\entorno\\Scripts\\python.exe\" "
        f"(\"%%D\\entorno\\Scripts\\python.exe\" {script} & goto :eof)\n"
        ")\n"
        f"where python >nul 2>nul && (python {script} & goto :eof)\n"
        f"where py >nul 2>nul && (py {script} & goto :eof)\n"
        "echo Instala Python 3.11+ desde https://www.python.org y volve a ejecutar,\n"
        "echo o usa INSTALAR.bat que lo baja y prepara todo solo.\n"
        "pause\n")

# edition_key → (título, dias|None, plan|None, owner)
EDICIONES = {
    "Demo":       ("Demo (evaluación con límite de días)", DEMO_DIAS, "trial", False),
    "Owner":      ("Owner (dueño del producto · sin límites)", None, None, True),
    "Basico":     ("Plan Básico", 365, "basico", False),
    "Starter":    ("Plan Starter", 365, "starter", False),
    "Pro":        ("Plan Pro", 365, "pro", False),
    "Enterprise": ("Plan Enterprise", 365, "enterprise", False),
}


def build_edicion(tmp, key):
    """Arma un paquete runnable por edición. Cada uno trae `edicion.json` que el
    launcher lee al arrancar: owner → sin límites; demo/plan → licencia embebida
    (día límite / cupo / features del plan). Sin precios en la documentación."""
    import json as _json
    import secrets as _secrets
    import sys as _sys
    if ROOT not in _sys.path:
        _sys.path.insert(0, ROOT)
    from backend_venta import licencias as klic

    titulo, dias, plan, owner = EDICIONES[key]
    stage = os.path.join(tmp, f"MVKobraAI_{key}_v{VERSION}")
    shutil.rmtree(stage, ignore_errors=True)
    soft = os.path.join(stage, "kobra_software")
    for item in _RUNTIME_ITEMS:
        _copy(item, os.path.join(soft, item))
    # Los dos launchers van en la RAÍZ de kobra_software (los .bat corren
    # `python <launcher>.py` desde ahí), no bajo packaging/:
    #   kobra_launcher.py  → app de escritorio (React + FastAPI embebido)
    #   kobra_streamlit.py → dashboard Streamlit (la vía sin .exe)
    _copy("packaging/kobra_launcher.py", os.path.join(soft, "kobra_launcher.py"))
    _copy("packaging/kobra_streamlit.py", os.path.join(soft, "kobra_streamlit.py"))

    # UI compilada: si en esta máquina hay un build FRESCO de Vite
    # (`webapp/frontend/dist` — en CI lo genera el paso "Compilar la app
    # React"), gana sobre la copia versionada de `owner/ui_dist`. El .exe ya
    # compilaba el frontend en cada corrida, pero estos ZIP se servían del
    # build commiteado: cualquier cambio de interfaz que no se acordaran de
    # recopiar a mano viajaba viejo, y el cliente que baja el ZIP veía una app
    # distinta de la del instalador. El respaldo commiteado sigue existiendo
    # para poder armar el paquete en una máquina sin Node.
    fresco = os.path.join(ROOT, "webapp", "frontend", "dist")
    if os.path.isdir(fresco) and os.path.exists(os.path.join(fresco, "index.html")):
        destino_ui = os.path.join(soft, "owner", "ui_dist")
        shutil.rmtree(destino_ui, ignore_errors=True)
        shutil.copytree(fresco, destino_ui)

    # edicion.json (lo consume packaging/kobra_launcher.py::_activar_edicion)
    ed = {"edition": key, "plan": plan, "dias": dias, "owner": owner}
    if not owner:
        secreto = _secrets.token_hex(32)
        cfg = klic.PLANES[plan]
        token = klic.emitir_licencia(
            cliente_id=f"edicion-{key.lower()}", plan=plan, edicion=key.lower(),
            features=cfg["features"], dias=dias, secreto=secreto)
        ed.update(secreto=secreto, token=token, features=cfg["features"],
                  cupo_mensual=cfg["cupo_mensual"])
    _write(os.path.join(soft, "edicion.json"), _json.dumps(ed, ensure_ascii=False, indent=2))

    # Lanzadores (Windows + Unix): corren el launcher standalone.
    # Ojo con los saltos de línea: `_write(crlf=True)` ya convierte \n -> \r\n.
    # Escribirlos acá como \r\n dejaba \r\r\n en el archivo (doble CR).
    # Si el usuario ya instaló con INSTALAR.bat, hay un entorno propio con las
    # dependencias: usarlo antes que el Python del sistema, que puede no
    # tenerlas y hace fallar el arranque con un ImportError.
    for sufijo, script, que_abre in _MODOS:
        _write(os.path.join(stage, f"INICIAR_{key.upper()}{sufijo}.bat"), crlf=True,
               content=_bat_lanzador(titulo, key, script, que_abre))
        sh = os.path.join(stage, f"iniciar_{key.lower()}{sufijo.lower()}.sh")
        _write(sh, "#!/usr/bin/env bash\ncd \"$(dirname \"$0\")/kobra_software\"\n"
                   f"python3 {script}\n")
        os.chmod(sh, 0o755)

    # INSTALAR.bat — deja el programa instalado de verdad: icono propio, Menú
    # Inicio, Escritorio y entrada en «Agregar o quitar programas». Todo en
    # HKCU y en el perfil del usuario, así que NO pide administrador.
    # pythonw y no python: `w` es la variante sin consola, para que abrir el
    # programa no levante una ventana negra atrás.
    flag_owner = " -Owner" if owner else ""
    # El titulo va en ASCII: un .bat corre en la code page de la consola
    # (850/437), no en UTF-8, y "dueño ·" saldria como mojibake en la barra.
    #
    # Antes este .bat apuntaba los accesos directos al pythonw del SISTEMA, sin
    # crear entorno ni instalar dependencias: el icono quedaba creado pero al
    # hacer clic el programa moría con ImportError si ese Python no tenía
    # uvicorn/fastapi. Ahora arma un entorno propio en la carpeta elegida, deja
    # las dependencias adentro y recién entonces crea los accesos apuntando a
    # ESE pythonw — el mismo camino que el .bat de owner.
    N = 6
    _write(os.path.join(stage, "INSTALAR.bat"), crlf=True, content=(
        "@echo off\n"
        "setlocal enabledelayedexpansion\n"
        f"title MV Kobra AI - Instalar ({key})\n"
        "cd /d \"%~dp0\"\n"
        "set \"CODIGO=%CD%\\kobra_software\"\n"
        "\n"
        "echo ============================================================\n"
        f"echo   MV Kobra AI - {_ascii(titulo)}\n"
        "echo   Elegis la carpeta y queda instalado con icono propio.\n"
        "echo ============================================================\n"
        "echo.\n"
        "\n"
        + _bat_elegir_carpeta(1, N, f"destino_{key.lower()}.txt")
        + _bat_espacio(2, N)
        + _bat_python(3, N)
        + _bat_entorno_y_deps(4, 5, N)
        + "\n"
        "echo.\n"
        f"echo [6/{N}] Dejando el programa instalado ^(icono, Menu Inicio, desinstalador^)...\n"
        "rem pythonw y no python: `w` es la variante sin consola, para que abrir\n"
        "rem el programa no levante una ventana negra atras.\n"
        "set \"PYW=!VENV!\\Scripts\\pythonw.exe\"\n"
        "if not exist \"!PYW!\" set \"PYW=!VPY!\"\n"
        "powershell -NoProfile -ExecutionPolicy Bypass -File "
        "\"!CODIGO!\\packaging\\instalar_windows.ps1\" -Destino \"!DESTINO!\" "
        "-Codigo \"!CODIGO!\" -Python \"!PYW!\" -Datos \"!DATOS!\" "
        # Deja los accesos de las DOS vías: app de escritorio y dashboard
        # Streamlit. El cliente cuyo sistemas bloquea .exe usa el segundo.
        "-LanzadorAlterno \"kobra_streamlit.py\" "
        f"-Version \"{VERSION}\"{flag_owner}\n"
        "if errorlevel 1 (\n"
        "  echo.\n"
        "  echo   Fallo la instalacion de los accesos. El programa igual se puede\n"
        f"  echo   abrir con INICIAR_{key.upper()}.bat.\n"
        ")\n"
        "echo.\n"
        "echo   Listo. Buscalo como \"MV Kobra AI\" en el Menu Inicio o en el Escritorio.\n"
        "echo.\n"
        "pause\n"
        "exit /b 0\n"
        "\n"
        + _bat_sub_libres()))

    limite = ("Sin límite de tiempo (edición del dueño)." if owner
              else f"Evaluación por {dias} días." if plan == "trial"
              else f"Licencia por {dias} días · plan {plan} completo.")
    feats = "todas las funciones (owner)" if owner else ", ".join(ed.get("features", []))
    _write(os.path.join(stage, "LEEME.txt"), crlf=True, content=f"""MV KOBRA AI · {titulo} · v{VERSION}
Plataforma de Cobranzas Inteligentes
=====================================

DOS FORMAS DE ABRIRLO — las dos hacen lo mismo, elegí la que te sirva:

  1) APP DE ESCRITORIO (interfaz nueva)
     Windows : doble clic en  INICIAR_{key.upper()}.bat
     Mac/Linux: ejecutar      ./iniciar_{key.lower()}.sh

  2) DASHBOARD STREAMLIT (sin ningún .exe)
     Windows : doble clic en  INICIAR_{key.upper()}_STREAMLIT.bat
     Mac/Linux: ejecutar      ./iniciar_{key.lower()}_streamlit.sh

     Esta segunda vía existe para las empresas donde el área de sistemas no
     permite ejecutar programas .exe bajados de internet. Acá no hay ningún
     ejecutable: es un .bat que abre el dashboard en el navegador con Python.
     Si tu empresa bloquea el instalador, usá esta y tenés el producto igual.

Las dos abren en el navegador (http://localhost) y corren 100% local en tu
equipo. Ninguna requiere Node; solo Python 3.11+.

DEJARLO INSTALADO EN WINDOWS (opcional pero recomendado):
  Doble clic en  INSTALAR.bat
  Te pregunta la carpeta y deja el programa instalado como cualquier otro:
    · icono propio y acceso directo en el Escritorio
    · entrada en el Menú Inicio
    · desinstalador en «Agregar o quitar programas»
  Deja los accesos de LAS DOS formas: «MV Kobra AI» (app de escritorio) y
  «MV Kobra AI - Dashboard Streamlit». No pide permisos de administrador
  (todo va a tu perfil de usuario).
  Al desinstalar, tus datos NO se borran salvo que lo pidas expresamente.

EDICIÓN
  {titulo}
  Alcance: {limite}
  Funciones habilitadas: {feats}

QUÉ INCLUYE
  Dashboard completo (KPIs, cartera priorizada, agenda, gestores), Originación,
  Calidad de gestión (audio + fichas de gestores), Asistente IA y el Gestor IA
  Negociador (voz/WhatsApp). Datos de demostración 100% sintéticos incluidos;
  podés cargar tu propia cartera desde Configuración.

HONESTIDAD DE LOS DATOS
  Datos sintéticos (sin personas reales). Las métricas de impacto son
  ILUSTRATIVAS de la metodología; el desempeño real se mide con tu cartera.
""")
    _write(os.path.join(stage, "VERSION.txt"), crlf=True,
           content=f"MV Kobra AI · {titulo} · v{VERSION}\n")
    return _zipdir(stage, os.path.join(DIST, f"MVKobraAI_{key}_v{VERSION}.zip"))


def main():
    # `--edicion Owner` arma una sola edición y saltea el paquete Demo, que
    # pre-renderiza la voz del chatvoice y tarda varios minutos. Para bajarse
    # la copia del dueño no hace falta pagar ese costo.
    import argparse
    ap = argparse.ArgumentParser(description="Empaquetador de releases")
    ap.add_argument("--edicion", choices=sorted(EDICIONES),
                    help="armar SOLO esta edición (rápido, sin Demo ni Producción)")
    args = ap.parse_args()

    tmp = os.path.join(DIST, "_staging")
    if args.edicion:
        paquetes = [build_edicion(tmp, args.edicion)]
        shutil.rmtree(tmp, ignore_errors=True)
        for p in paquetes:
            print(f"[OK] {os.path.basename(p)}  ({os.path.getsize(p) // 1024} KB)")
            print(f"     sha256: {_sha256(p)}")
        return

    paquetes = [build_demo(tmp), build_prod(tmp)]
    for key in EDICIONES:
        paquetes.append(build_edicion(tmp, key))
    shutil.rmtree(tmp, ignore_errors=True)

    lines = []
    for z in paquetes:
        mb = os.path.getsize(z) / 1e6
        digest = _sha256(z)
        lines.append(f"{digest}  {os.path.basename(z)}")
        print(f"[OK] {os.path.basename(z)}  ({mb:.1f} MB)  sha256={digest[:16]}…")
    with open(os.path.join(DIST, "SHA256SUMS.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print("[OK] Checksums: dist/SHA256SUMS.txt")


if __name__ == "__main__":
    main()
