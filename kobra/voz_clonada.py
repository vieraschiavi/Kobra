# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Voz clonada en tres pasos
=======================================
Clonar la voz del gestor para que el Gestor IA hable con ella en las llamadas
pedía cuatro pasos fuera del programa: entrar a elevenlabs.io, clonar ahí,
copiar el `voice_id`, volver y elegirlo. Y aun así no llegaba a las llamadas
(ver `voz_activa`). Este módulo lo deja en tres pasos sin salir de Kobra:
**grabar o subir una muestra → clonar → escucharla**.

Dos motores:

  * **ElevenLabs** (Instant Voice Cloning, `POST /v1/voices/add`): el de las
    llamadas en vivo. Es el único con latencia de conversación telefónica.
  * **Gratis, en el equipo** (`voz_clon_local`, Chatterbox de Resemble AI,
    licencia MIT): clona sin costo y sin que la voz salga de la máquina. Tarda
    segundos por frase en CPU, así que sirve para escuchar la voz y para las
    demos, no para una conversación por teléfono: NO cambia la voz de las
    llamadas. La muestra queda en la carpeta de datos y se puede borrar.

Consentimiento: clonar una voz ajena sin permiso es suplantación. Por eso
`clonar` exige que quien clona declare tener el consentimiento de la persona
dueña de la voz, y el endpoint lo deja en la auditoría.
"""
from __future__ import annotations

import os
import threading
import time

from kobra import config as kconfig
from kobra import rutas as krutas
from kobra import voz_tts

MOTORES = ("elevenlabs", "local")
# El modelo local ocupa varios GB de RAM y la CPU entera: dos pruebas a la vez
# lo cargarían dos veces o se pisarían. Va de a una.
_LOCK_LOCAL = threading.Lock()

# Formatos que acepta la subida. El navegador graba en webm/opus, pero la
# pantalla lo pasa a WAV antes de mandarlo, así que el servidor no necesita
# ffmpeg para recibir una grabación hecha en la propia app.
FORMATOS_MUESTRA = (".wav", ".mp3", ".m4a")
# Tope propio por muestra. Una muestra de 2 minutos en WAV mono 16 bits a
# 44,1 kHz pesa ~10 MB; 25 MB deja margen para una en estéreo.
MAX_MB_MUESTRA = 25
# Debajo de esto el clon sale con poco parecido a la voz. Se mide solo en WAV
# (el único formato cuya duración se lee sin decodificar).
DURACION_MINIMA_S = 10
DURACION_RECOMENDADA_S = 60
# La prueba es para escuchar la voz, no para sintetizar un guion entero con
# costo por carácter.
MAX_CARACTERES_PRUEBA = 300
FRASE_PRUEBA = ("Hola, le habla el área de cobranzas. Lo llamo para ofrecerle "
                "una forma cómoda de ponerse al día con su cuenta.")

_URL_CLONAR = f"{voz_tts._BASE_URL}/voices/add"

# `voz_activa` corre en CADA frase de una llamada, y leer lo guardado es
# descifrar el almacén (o ir al keyring del sistema). Se cachea unos segundos:
# un cambio hecho desde otra pantalla (otro proceso) rige a lo sumo así de
# tarde, y uno hecho desde este proceso, en el acto.
_TTL_EXTRAS_S = 5.0
_cache_extras: tuple[float, dict] | None = None


def _extras() -> dict:
    global _cache_extras
    ahora = time.monotonic()
    if _cache_extras is None or ahora - _cache_extras[0] > _TTL_EXTRAS_S:
        _cache_extras = (ahora, kconfig.cargar())
    return _cache_extras[1]


def _olvidar_cache() -> None:
    global _cache_extras
    _cache_extras = None


class MuestraInvalida(ValueError):
    """La muestra de voz no sirve para clonar; el mensaje es para el usuario."""


def api_key_elevenlabs(api_key: str | None = None) -> str:
    """La key de ElevenLabs: la explícita, la del entorno o la guardada.

    La guardada importa: el servidor de llamadas es otro proceso, arrancado
    antes de que alguien cargara la key en Configuración, así que su entorno
    no la tiene.
    """
    return (voz_tts.api_key_configurada(api_key)
            or voz_tts.api_key_configurada(_extras().get("ELEVENLABS_API_KEY", "")))


def voz_activa() -> str:
    """El `voice_id` con el que habla el Gestor IA en las llamadas, o '' si
    habla con la voz de Twilio/Polly.

    Bug que corrige: `realtime/server.py` leía `TTS_PROVIDER` y
    `ELEVENLABS_VOICE_ID` UNA vez, del entorno, al importar el módulo. Lo que
    se elegía en Configuración se guardaba en el almacén cifrado y nunca se
    leía, así que la voz elegida no sonaba jamás. Y aun configurando el
    entorno como dice `env.example` tampoco andaba: ahí figura
    `ELEVENLABS_VOICE_ID` pero no `TTS_PROVIDER`, que por defecto es "twilio".

    Ahora se resuelve en cada frase (entorno primero, después lo guardado), y
    tener una voz elegida alcanza para usarla. `TTS_PROVIDER=twilio` sigue
    siendo la forma explícita de apagarla.
    """
    extras = _extras()
    proveedor = (os.getenv("TTS_PROVIDER") or extras.get("TTS_PROVIDER") or "").strip().lower()
    if proveedor == "twilio":
        return ""
    return (os.getenv("ELEVENLABS_VOICE_ID") or extras.get("ELEVENLABS_VOICE_ID") or "").strip()


def duracion_wav(contenido: bytes) -> float | None:
    """Duración en segundos de un WAV, o None si no se puede leer."""
    import io

    import soundfile as sf
    try:
        info = sf.info(io.BytesIO(contenido))
    except Exception:
        return None
    return float(info.frames) / float(info.samplerate or 1)


def validar_muestra(nombre_archivo: str, contenido: bytes) -> dict:
    """Valida la muestra y devuelve {"duracion_s", "aviso"}; levanta
    `MuestraInvalida` si no sirve."""
    nombre = (nombre_archivo or "").lower()
    if not nombre.endswith(FORMATOS_MUESTRA):
        raise MuestraInvalida("La muestra tiene que ser .wav, .mp3 o .m4a.")
    if not contenido:
        raise MuestraInvalida("La muestra llegó vacía.")
    if len(contenido) > MAX_MB_MUESTRA * 1024 * 1024:
        raise MuestraInvalida(f"La muestra supera los {MAX_MB_MUESTRA} MB.")
    duracion = duracion_wav(contenido) if nombre.endswith(".wav") else None
    if nombre.endswith(".wav") and duracion is None:
        raise MuestraInvalida("No pude leer ese WAV: está dañado o no es audio.")
    if duracion is not None and duracion < DURACION_MINIMA_S:
        raise MuestraInvalida(
            f"La muestra dura {duracion:.0f} s: hacen falta al menos "
            f"{DURACION_MINIMA_S} s de voz para que el clon se parezca.")
    aviso = None
    if duracion is not None and duracion < DURACION_RECOMENDADA_S:
        aviso = (f"La muestra dura {duracion:.0f} s. Con un minuto o más de "
                 "voz natural, sin música ni ruido, el clon se parece más.")
    return {"duracion_s": duracion, "aviso": aviso}


def clonar(nombre: str, muestras: list[tuple[str, bytes]], api_key: str | None = None,
           quitar_ruido: bool = False, timeout: int = 120) -> dict:
    """Clona una voz en ElevenLabs a partir de una o más muestras.

    Devuelve {"ok", "voice_id", "requiere_verificacion", "error"}. Nunca
    levanta excepción: un fallo de red o de cuenta se informa, no tumba el
    endpoint.
    """
    import requests

    fallo = {"ok": False, "voice_id": None, "requiere_verificacion": False}
    key = api_key_elevenlabs(api_key)
    if not key:
        return {**fallo, "error": "Falta ELEVENLABS_API_KEY: cargala arriba, en la tabla de claves."}
    nombre = (nombre or "").strip()[:100]
    if not nombre:
        return {**fallo, "error": "Ponele un nombre a la voz."}
    if not muestras:
        return {**fallo, "error": "Falta la muestra de voz."}
    try:
        r = requests.post(
            _URL_CLONAR, headers={"xi-api-key": key},
            data={"name": nombre,
                  "description": "Voz clonada desde MV Kobra AI",
                  "remove_background_noise": "true" if quitar_ruido else "false"},
            files=[("files", (archivo, contenido)) for archivo, contenido in muestras],
            timeout=timeout)
    except requests.RequestException as e:
        return {**fallo, "error": f"No pude conectar con ElevenLabs ({type(e).__name__})."}
    if r.status_code in (401, 403):
        return {**fallo, "error": "ElevenLabs rechazó la key, o tu plan no incluye clonado de voz."}
    if not r.ok:
        return {**fallo, "error": f"ElevenLabs respondió {r.status_code}: {_detalle(r)}"}
    datos = r.json() if r.content else {}
    voice_id = (datos or {}).get("voice_id")
    if not voice_id:
        return {**fallo, "error": "ElevenLabs no devolvió el id de la voz."}
    return {"ok": True, "voice_id": voice_id,
            "requiere_verificacion": bool(datos.get("requires_verification")), "error": None}


def _detalle(r) -> str:
    """El motivo del error que manda ElevenLabs, acotado."""
    try:
        detalle = r.json().get("detail")
    except Exception:
        detalle = None
    if isinstance(detalle, dict):
        detalle = detalle.get("message") or detalle.get("status")
    if isinstance(detalle, list) and detalle:
        detalle = detalle[0].get("msg") if isinstance(detalle[0], dict) else detalle[0]
    return str(detalle or r.text or "sin detalle")[:200]


def activar(voice_id: str, nombre: str = "") -> None:
    """Deja `voice_id` como la voz de las llamadas. Rige desde la próxima frase."""
    kconfig.guardar_extra("ELEVENLABS_VOICE_ID", voice_id)
    kconfig.guardar_extra("ELEVENLABS_VOICE_NOMBRE", (nombre or "").strip()[:100])
    kconfig.guardar_extra("TTS_PROVIDER", "elevenlabs")
    _olvidar_cache()


def desactivar() -> None:
    """Vuelve a la voz de Twilio/Polly sin borrar la voz clonada de ElevenLabs."""
    kconfig.guardar_extra("TTS_PROVIDER", "twilio")
    _olvidar_cache()


def probar(texto: str | None = None, api_key: str | None = None) -> dict:
    """Sintetiza una frase corta con la voz activa, para escucharla.

    Mismo dict que `voz_tts.sintetizar`. Usa el modelo de llamadas a
    propósito: lo que se escucha es lo que va a sonar en el teléfono.
    """
    texto = (texto or FRASE_PRUEBA).strip()[:MAX_CARACTERES_PRUEBA]
    voice_id = voz_activa()
    if not voice_id:
        return {"ok": False, "audio": None, "caracteres": len(texto), "costo_est_usd": 0.0,
                "error": "No hay voz clonada activa: clonala o elegí una primero."}
    return voz_tts.sintetizar(texto, voice_id, api_key=api_key_elevenlabs(api_key),
                              modelo=voz_tts.MODELO_LLAMADAS)


def ruta_muestra_local() -> str:
    """Dónde queda la muestra del motor gratis: en la carpeta de datos del
    cliente, nunca en el repo ni en una carpeta temporal que se borra sola."""
    return os.path.join(krutas.DIR_DATOS, "voz", "muestra_local.wav")


def guardar_muestra_local(nombre_archivo: str, contenido: bytes, nombre: str) -> None:
    """Guarda la muestra para el motor gratis como WAV mono.

    Un WAV (lo que graba la pantalla) se convierte acá mismo, sin ffmpeg: el
    instalador no lo trae. Un .mp3/.m4a sí necesita ffmpeg para decodificarse.
    """
    import io
    import shutil
    import subprocess
    import tempfile

    import soundfile as sf
    destino = ruta_muestra_local()
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    temporal = destino + ".tmp.wav"
    if nombre_archivo.lower().endswith(".wav"):
        datos, sr = sf.read(io.BytesIO(contenido), always_2d=True)
        sf.write(temporal, datos.mean(axis=1), sr, format="WAV")
    else:
        if shutil.which("ffmpeg") is None:
            raise MuestraInvalida("Con el motor gratis, grabá desde acá o subí un .wav: "
                                  "un .mp3 o .m4a necesita ffmpeg instalado.")
        with tempfile.TemporaryDirectory() as tmp:
            origen = os.path.join(tmp, "muestra" + os.path.splitext(nombre_archivo)[1].lower())
            with open(origen, "wb") as f:
                f.write(contenido)
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", origen,
                                "-vn", "-ac", "1", "-ar", "24000", temporal],
                               capture_output=True)
        if r.returncode != 0:
            raise MuestraInvalida("No pude leer ese audio: está dañado o no es audio.")
    os.replace(temporal, destino)   # atómico: una muestra a medio escribir nunca queda como la vigente
    kconfig.guardar_extra("VOZ_LOCAL_NOMBRE", (nombre or "").strip()[:100])
    _olvidar_cache()


def borrar_muestra_local() -> None:
    """Borra la muestra del equipo. Es la voz de una persona: se tiene que
    poder sacar del disco tan fácil como se puso."""
    try:
        os.remove(ruta_muestra_local())
    except FileNotFoundError:
        pass
    kconfig.guardar_extra("VOZ_LOCAL_NOMBRE", None)
    _olvidar_cache()


def probar_local(texto: str | None = None, idioma: str = "es") -> dict:
    """Una frase con la voz clonada gratis, en WAV. Mismo dict que `probar`."""
    from kobra import voz_clon_local
    texto = (texto or FRASE_PRUEBA).strip()[:MAX_CARACTERES_PRUEBA]
    fallo = {"ok": False, "audio": None, "caracteres": len(texto), "costo_est_usd": 0.0}
    if not voz_clon_local.motor_disponible():
        return {**fallo, "error": "El motor gratis no está instalado en este equipo "
                                  "(pip install chatterbox-tts)."}
    if not os.path.exists(ruta_muestra_local()):
        return {**fallo, "error": "Primero grabá o subí la muestra de tu voz."}
    with _LOCK_LOCAL:
        return voz_clon_local.sintetizar(texto, referencia=ruta_muestra_local(),
                                         idioma=idioma, formato="wav")


def estado() -> dict:
    """Lo que necesita la pantalla para saber en qué paso está quien configura."""
    import shutil

    from kobra import voz_clon_local
    _olvidar_cache()
    extras = _extras()
    voice_id = voz_activa()
    hay_muestra_local = os.path.exists(ruta_muestra_local())
    return {
        "hay_key": bool(api_key_elevenlabs()),
        "motor_llamadas": "elevenlabs" if voice_id else "twilio",
        "voice_id": voice_id or None,
        "nombre": (extras.get("ELEVENLABS_VOICE_NOMBRE") or None) if voice_id else None,
        # Una variable de entorno le gana a lo elegido en pantalla (misma
        # prioridad que el resto de la config del servidor de llamadas): si
        # está, clonar desde acá no cambia la voz y la pantalla lo avisa.
        "forzada_por_entorno": bool(os.getenv("ELEVENLABS_VOICE_ID") or os.getenv("TTS_PROVIDER")),
        "clonador_local": voz_clon_local.motor_disponible() or None,
        "local": {"hay_muestra": hay_muestra_local,
                  "nombre": (extras.get("VOZ_LOCAL_NOMBRE") or None) if hay_muestra_local else None,
                  "ffmpeg": shutil.which("ffmpeg") is not None},
        "duracion_minima_s": DURACION_MINIMA_S,
        "duracion_recomendada_s": DURACION_RECOMENDADA_S,
        "max_mb": MAX_MB_MUESTRA,
        "frase_prueba": FRASE_PRUEBA,
    }
