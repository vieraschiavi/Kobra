# © 2026 Martín Viera. Todos los derechos reservados.

r"""
MV Kobra AI · Carpeta de datos escribibles (y en qué disco)
===========================================================
El programa instalado en Windows vive en una carpeta de solo lectura para
un usuario sin privilegios de administrador (típicamente Program Files) —
cualquier escritura relativa a esa carpeta (subidas de audio, cartera y
outputs generados, logs de auditoría, backups, datos por tenant) fallaba
con PermissionError: [WinError 5] Acceso denegado.

`DIR_DATOS` resuelve SIEMPRE a un lugar escribible por el usuario actual:

  1. `KOBRA_DATA_DIR` fuerza cualquier ubicación explícita (mismo criterio
     que `KOBRA_CONFIG_DIR` en `kobra/config.py`).
  2. **La carpeta que eligió el usuario**, si eligió una — ver abajo.
  3. Corriendo empaquetado (PyInstaller, `sys.frozen`): `%LOCALAPPDATA%\MV
     Kobra AI` en Windows, `~/.mv_kobra_ai` en Linux/Mac — independiente de
     dónde esté instalado el programa.
  4. Corriendo desde el código fuente (dev, tests, CI): la raíz del propio
     repo, exactamente como siempre — cero cambios en el flujo de desarrollo
     ni en los tests existentes.

Por qué se puede elegir el disco
--------------------------------
Instalar en `D:\` no alcanzaba. La carpeta de instalación era elegible desde
el primer día (el asistente tiene botón Examinar), pero los DATOS iban
siempre a `%LOCALAPPDATA%`, o sea al disco del perfil de Windows, o sea C: en
la práctica totalidad de las máquinas. El que instalaba en D: porque C: estaba
lleno chocaba con el mismo disco lleno en el primer import de cartera, y el
error aparecía lejos de la causa: un `OSError: [Errno 28] No space left on
device` a mitad de un pipeline, no un "elegiste un disco sin lugar".

Ahora la elección se guarda en un puntero de texto —`carpeta_datos.txt`— y se
lee acá. El puntero vive en la ubicación POR DEFECTO (no en la elegida: si
viviera en el disco elegido y ese disco se desconecta, no habría forma de
saber a dónde apuntaba). Lo escriben tres lugares, y todos usan esta misma
función: el instalador de Windows, el script `instalar_windows.ps1` y la
pantalla de Configuración del propio programa.

Y se valida antes de usarla. Una carpeta elegida que ya no se puede escribir
—disco desconectado, pendrive sacado, permisos cambiados, disco lleno— NO
tumba el arranque: se cae a la ubicación por defecto y el motivo queda en
`MOTIVO_FALLBACK`, que la pantalla de Configuración muestra. Un programa de
cobranzas que no abre es peor que uno que abre avisando dónde está guardando.

`sembrar_si_hace_falta()` copia una sola vez, en el primer arranque
empaquetado, los datos de demo bundleados (`data/`, `outputs/`) desde la
carpeta de instalación hacia `DIR_DATOS` — así la demo sigue funcionando
"out of the box" sin que el usuario tenga que cargar nada.
"""
from __future__ import annotations

import os
import shutil
import sys

ROOT_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# El puntero a la carpeta elegida. Texto plano, una línea, sin encoding
# exótico: lo escriben Python, PowerShell y NSIS, y lo tiene que poder abrir
# el usuario con el Bloc de notas para ver qué pasó.
ARCHIVO_ELECCION = "carpeta_datos.txt"

# Espacio mínimo para dejar operar. No es el tamaño del programa: es lo que
# consume trabajar — importar una cartera, entrenar, exportar Excel y PDF, y
# el backup que se hace antes de pisar nada. Por debajo de esto el usuario se
# va a chocar con el disco en la primera operación pesada, así que conviene
# decírselo cuando elige y no cuando falla.
MIN_LIBRE_MB = 500


def _instalado() -> bool:
    return bool(getattr(sys, "frozen", False))


def dir_preferencias() -> str:
    """Dónde vive el puntero: SIEMPRE la ubicación por defecto del sistema.

    Nunca la elegida — el puntero tiene que seguir siendo legible justo
    cuando el disco elegido no está.
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return os.path.join(base, "MV Kobra AI")
    return os.path.expanduser("~/.mv_kobra_ai")


def _default_dir_datos() -> str:
    if not _instalado():
        return ROOT_REPO
    return dir_preferencias()


# ---------------------------------------------------------------------------
# Espacio y permisos: preguntar antes, no descubrirlo a mitad de un pipeline
# ---------------------------------------------------------------------------
def espacio(ruta: str) -> tuple[int, int]:
    """(libre_mb, total_mb) del disco donde cae `ruta`. (0, 0) si no se puede
    averiguar — un disco que no responde no debe tirar una excepción acá."""
    # Se sube hasta el primer ancestro que exista: preguntar por una carpeta
    # que todavía no se creó devuelve error, y justamente se quiere saber si
    # HAY lugar para crearla.
    p = os.path.abspath(ruta)
    while p and not os.path.exists(p):
        padre = os.path.dirname(p)
        if padre == p:
            break
        p = padre
    try:
        uso = shutil.disk_usage(p)
    except OSError:
        return (0, 0)
    return (uso.free // (1024 * 1024), uso.total // (1024 * 1024))


def revisar(ruta: str) -> dict:
    """¿Sirve esta carpeta para guardar los datos?

    Devuelve `{"ok", "motivo", "libre_mb", "total_mb", "poco_espacio"}`. No
    lanza: la respuesta es el diagnóstico, para poder mostrarlo tal cual.

    La prueba de escritura es real —se crea un archivo y se borra—, no
    `os.access`: en Windows `os.access` mira los permisos declarados y no el
    resultado, así que dice que sí sobre carpetas donde escribir falla igual
    (unidad de red caída, carpeta controlada por el antivirus).
    """
    libre_mb, total_mb = espacio(ruta)
    base = {"ok": False, "motivo": "", "libre_mb": libre_mb,
            "total_mb": total_mb, "poco_espacio": False}
    if not ruta.strip():
        return {**base, "motivo": "No indicaste ninguna carpeta."}
    try:
        os.makedirs(ruta, exist_ok=True)
    except OSError as e:
        return {**base, "motivo": f"No se puede crear la carpeta: {e.strerror or e}."}
    if not os.path.isdir(ruta):
        return {**base, "motivo": "La ruta existe pero no es una carpeta."}

    prueba = os.path.join(ruta, ".kobra_prueba_escritura")
    try:
        with open(prueba, "w", encoding="ascii") as f:
            f.write("ok")
        os.remove(prueba)
    except OSError as e:
        return {**base, "motivo": f"La carpeta no se puede escribir: {e.strerror or e}."}

    libre_mb, total_mb = espacio(ruta)
    poco = 0 < total_mb and libre_mb < MIN_LIBRE_MB
    return {"ok": True, "motivo": "", "libre_mb": libre_mb, "total_mb": total_mb,
            "poco_espacio": poco}


def discos() -> list[dict]:
    """Los discos donde se podría guardar, con su espacio libre.

    Es lo que necesita la pantalla que deja elegir: sin ver cuánto queda en
    cada uno, "elegir disco" es adivinar.
    """
    salida, vistos = [], set()
    if sys.platform == "win32":
        candidatos = [f"{chr(letra)}:\\" for letra in range(ord("A"), ord("Z") + 1)]
    else:
        candidatos = [os.path.expanduser("~"), "/"]
    for raiz in candidatos:
        if not os.path.isdir(raiz):
            continue
        try:
            # Dedup por dispositivo: en Linux `~` y `/` suelen ser el mismo
            # disco y listarlo dos veces confunde más de lo que informa.
            dev = os.stat(raiz).st_dev
        except OSError:
            continue
        if dev in vistos:
            continue
        libre_mb, total_mb = espacio(raiz)
        if not total_mb:
            continue        # unidad vacía (lector de tarjetas sin tarjeta)
        vistos.add(dev)
        salida.append({"unidad": raiz, "libre_mb": libre_mb, "total_mb": total_mb,
                       "suficiente": libre_mb >= MIN_LIBRE_MB})
    return salida


# ---------------------------------------------------------------------------
# El puntero a la carpeta elegida
# ---------------------------------------------------------------------------
def _ruta_puntero() -> str:
    return os.path.join(dir_preferencias(), ARCHIVO_ELECCION)


def carpeta_elegida() -> str:
    """La carpeta que el usuario eligió, o "" si nunca eligió ninguna."""
    try:
        with open(_ruta_puntero(), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def guardar_eleccion(ruta: str) -> None:
    """Anota la elección. `ruta` vacía la borra y vuelve al default."""
    puntero = _ruta_puntero()
    if not ruta.strip():
        try:
            os.remove(puntero)
        except OSError:
            pass
        return
    os.makedirs(os.path.dirname(puntero), exist_ok=True)
    with open(puntero, "w", encoding="utf-8") as f:
        f.write(os.path.abspath(ruta.strip()))


# ---------------------------------------------------------------------------
# Resolución final
# ---------------------------------------------------------------------------
# Por qué la elección se honra solo empaquetado: en el repo, DIR_DATOS es la
# raíz del repo y eso es un contrato del que dependen los tests y todo el
# flujo de desarrollo. Un puntero que quedó en la máquina de alguien no puede
# cambiar en silencio a dónde escribe la suite. En dev el override sigue
# siendo KOBRA_DATA_DIR, explícito y por proceso.
MOTIVO_FALLBACK = ""


def _resolver() -> tuple[str, str]:
    forzado = os.environ.get("KOBRA_DATA_DIR")
    if forzado:
        return forzado, ""
    default = _default_dir_datos()
    if not _instalado():
        return default, ""
    elegida = carpeta_elegida()
    if not elegida or os.path.abspath(elegida) == os.path.abspath(default):
        return default, ""
    diag = revisar(elegida)
    if not diag["ok"]:
        # No se corta el arranque: se sigue con la carpeta de siempre y el
        # motivo queda a la vista en Configuración.
        return default, (f"La carpeta elegida ({elegida}) no está disponible: "
                         f"{diag['motivo']} Se está usando {default}.")
    return elegida, ""


DIR_DATOS, MOTIVO_FALLBACK = _resolver()

# Carpeta de recursos bundleados de SOLO LECTURA (el propio bundle de
# PyInstaller, vía sys._MEIPASS) — separada de DIR_DATOS a propósito: nunca
# hay que escribir ahí, solo leer lo que trae la instalación (demo, docs).
DIR_BUNDLE = getattr(sys, "_MEIPASS", ROOT_REPO)


def estado() -> dict:
    """Lo que muestra la pantalla de Configuración: dónde se está guardando,
    por qué, cuánto queda y qué discos hay."""
    diag = revisar(DIR_DATOS)
    return {
        "dir_datos": DIR_DATOS,
        "elegida": carpeta_elegida(),
        "default": _default_dir_datos(),
        "forzada_por_entorno": bool(os.environ.get("KOBRA_DATA_DIR")),
        "motivo_fallback": MOTIVO_FALLBACK,
        "libre_mb": diag["libre_mb"],
        "total_mb": diag["total_mb"],
        "poco_espacio": diag["poco_espacio"],
        "minimo_mb": MIN_LIBRE_MB,
        "discos": discos(),
    }


def mover_datos(destino: str, origen: str = "") -> dict:
    """Copia los datos a la carpeta nueva y deja anotada la elección.

    Copia y DESPUÉS borra, nunca `move` directo: si el destino se queda sin
    espacio a mitad —el escenario exacto que trae acá al usuario— un `move`
    interrumpido deja los datos partidos entre dos discos, sin original al que
    volver. Copiando, el original sigue intacto hasta que la copia terminó.

    Devuelve `{"ok", "motivo", "movido_mb"}`.
    """
    origen = origen or DIR_DATOS
    if os.path.abspath(origen) == os.path.abspath(destino):
        guardar_eleccion(destino)
        return {"ok": True, "motivo": "Ya estaba en esa carpeta.", "movido_mb": 0}

    diag = revisar(destino)
    if not diag["ok"]:
        return {"ok": False, "motivo": diag["motivo"], "movido_mb": 0}

    copiadas, bytes_totales = [], 0
    try:
        for carpeta in ("data", "outputs"):
            desde = os.path.join(origen, carpeta)
            hacia = os.path.join(destino, carpeta)
            if not os.path.isdir(desde):
                continue
            shutil.copytree(desde, hacia, dirs_exist_ok=True)
            copiadas.append((desde, hacia))
            for raiz, _, archivos in os.walk(hacia):
                bytes_totales += sum(os.path.getsize(os.path.join(raiz, a))
                                     for a in archivos)
    except OSError as e:
        # Copia a medias: se borra lo copiado y NO se toca el original ni el
        # puntero. El usuario queda exactamente como estaba.
        for _, hacia in copiadas:
            shutil.rmtree(hacia, ignore_errors=True)
        return {"ok": False, "movido_mb": 0,
                "motivo": f"No se pudo copiar todo ({e.strerror or e}). "
                          f"No se cambió nada: los datos siguen en {origen}."}

    guardar_eleccion(destino)
    # El original se deja donde está a propósito. Borrar datos de cobranzas
    # como efecto secundario de cambiar una carpeta es exactamente el tipo de
    # cosa que no se puede deshacer; el usuario los borra cuando quiera.
    return {"ok": True, "movido_mb": bytes_totales // (1024 * 1024),
            "motivo": f"Copiado a {destino}. El original quedó en {origen} "
                      f"por las dudas — podés borrarlo cuando verifiques."}


def sembrar_si_hace_falta() -> None:
    """Primera vez que corre empaquetado: copia data/ y outputs/ bundleados
    (demo sintética) a DIR_DATOS, si todavía no existen ahí. Nunca pisa datos
    reales que el usuario ya haya cargado."""
    if not _instalado() or DIR_DATOS == ROOT_REPO:
        return
    for carpeta in ("data", "outputs"):
        origen = os.path.join(DIR_BUNDLE, carpeta)
        destino = os.path.join(DIR_DATOS, carpeta)
        if os.path.isdir(origen) and not os.path.isdir(destino):
            shutil.copytree(origen, destino)
