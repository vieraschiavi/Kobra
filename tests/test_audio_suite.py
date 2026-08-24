# © 2026 Martín Viera. Todos los derechos reservados.

"""El screencast de la suite salía MUDO.

Los otros dos videos de la landing no están en la misma situación: el del
Copiloto tiene narración y el `Demo_Real` tampoco tiene audio. El de la suite
sí la necesita porque es el que presenta seis módulos nuevos: sin voz, el
visitante mira pantallas pasar sin saber qué está viendo.

`marketing/voz_suite.py` ya sintetizaba los cues, pero los dejaba como MP3
sueltos en una carpeta —"mezclalos con cualquier editor", decía— así que el
paso que faltaba era el montaje, y había que rehacerlo a mano cada vez que se
regrabara el screencast. `marketing/audio_suite.py` lo cierra.

Este archivo fija las tres decisiones que, si se rompen, no se notan hasta
tener el video publicado y sonando mal.
"""
import os
import pathlib

import pytest

from marketing import audio_suite as A
from marketing.subtitulos import IDIOMAS, SUITE_CUES

ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# --- El motor de voz: cuál se usa y por qué ---------------------------------
def test_sin_clave_cae_a_piper(monkeypatch):
    """Sin `ELEVENLABS_API_KEY` no se puede usar la voz del producto. Antes de
    fallar, se usa el sintetizador offline: poder armar el corte y revisar los
    tiempos sin clave ni gastar créditos es la diferencia entre iterar y no."""
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert A.motor_disponible() == "piper"


def test_con_clave_usa_la_voz_del_producto(monkeypatch):
    """Y con la clave puesta gana ElevenLabs SIEMPRE. Es la misma voz de las
    llamadas reales y del video del Copiloto: que el video de la suite hable
    con otra voz es una inconsistencia que se escucha."""
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x" * 40)
    assert A.motor_disponible() == "elevenlabs"


def test_un_motor_inventado_se_rechaza():
    with pytest.raises(ValueError, match="motor desconocido"):
        A.construir(motor="robotito")


def test_elevenlabs_sin_voz_elegida_explica_que_falta(monkeypatch):
    """La clave sola no alcanza: hace falta saber QUÉ voz. Sin eso el error
    tiene que decir cuál es la variable, no reventar con un KeyError."""
    monkeypatch.setenv("ELEVENLABS_API_KEY", "x" * 40)
    monkeypatch.delenv("ELEVENLABS_VOICE_ID_GESTOR", raising=False)
    with pytest.raises(RuntimeError, match="ELEVENLABS_VOICE_ID_GESTOR"):
        A._wav_elevenlabs("hola")


def test_piper_sin_modelo_dice_como_bajarlo(monkeypatch, tmp_path):
    """El modelo de voz no está en el repo (110 MB). Si falta, el mensaje
    tiene que traer el comando exacto — no `FileNotFoundError` a secas."""
    pytest.importorskip("piper")
    monkeypatch.setattr(A, "PIPER_DIR", str(tmp_path))
    monkeypatch.setattr(A, "_PIPER_CACHE", {})
    with pytest.raises(RuntimeError, match="download_voices"):
        A._wav_piper("hola")


# --- El montaje -------------------------------------------------------------
def test_el_salto_de_linea_del_subtitulo_no_es_una_pausa(monkeypatch):
    """El `\\n` de un cue parte el texto en DOS RENGLONES en pantalla; no es
    una pausa del relato. Si se le pasa crudo al sintetizador, la voz corta a
    mitad de frase donde el subtítulo cambia de línea."""
    visto = {}
    monkeypatch.setattr(A, "_wav_piper",
                        lambda t, **kw: visto.setdefault("t", t) or b"")
    A.sintetizar_cue("una linea\ny la otra", "piper")
    assert visto["t"] == "una linea y la otra"


def test_la_mezcla_normaliza_el_volumen():
    """Guardia del defecto que se encontró midiendo: `amix` con `normalize=0`
    suma los cues tal cual, y la voz de piper ya viene cerca del tope — la
    primera mezcla salió con 486 muestras clavadas en 0 dBFS, o sea recortando.

    `loudnorm` lo lleva al estándar de locución (-16 LUFS, techo -1,5 dBTP).
    Sacarlo devuelve el clipping sin que ningún test falle si no es este.
    """
    fuente = (ROOT / "marketing" / "audio_suite.py").read_text(encoding="utf-8")
    assert "loudnorm" in fuente, "se sacó la normalización: la mezcla va a recortar"
    assert "normalize=0" in fuente


def test_el_cierre_tiene_pantalla_sobre_la_cual_sonar():
    """El defecto que motivó todo esto.

    El screencast dura 52,84 s y el último cue —el único que dice el dominio,
    o sea el ÚNICO llamado a la acción del video— arranca a los 55,0 s. Sonaba
    (y se subtitulaba) sobre un video que ya había terminado: nunca se veía.

    El módulo estira el video congelando el último cuadro. Acá se fija que el
    cálculo cubra al último cue, sea cual sea el motor de voz.
    """
    ini_ultimo = SUITE_CUES[-1][0]
    dur_video = 52.84                      # la del webm publicado
    assert ini_ultimo > dur_video, (
        "si el cierre ya entra en el video, este módulo perdió su razón de ser "
        "— revisar que el arreglo no se haya hecho dos veces")
    # Con cualquier duración de voz > 0, el final tiene que pasar el arranque
    # del último cue; si no, el cierre queda sin imagen otra vez.
    fin_audio = ini_ultimo + 0.1
    assert max(dur_video, fin_audio + A.COLA_S) > ini_ultimo


def test_hay_aire_despues_de_la_ultima_palabra():
    """Cortar el video en el mismo frame en que termina la voz se siente como
    un tirón. `COLA_S` es ese aire; que exista y no sea cero es la decisión."""
    assert A.COLA_S > 0


# --- La narración y los subtítulos son el MISMO texto -----------------------
def test_la_voz_lee_los_cues_de_los_subtitulos():
    """No hay un guion aparte. Si lo hubiera, alguien lo edita, se olvida del
    otro y el video termina diciendo algo distinto de lo que subtitula."""
    fuente = (ROOT / "marketing" / "audio_suite.py").read_text(encoding="utf-8")
    assert "from marketing.subtitulos import" in fuente
    assert "SUITE_CUES" in fuente


def test_narra_en_castellano_como_el_video_del_copiloto():
    """Los tres idiomas viajan por los SUBTÍTULOS, no doblando la voz: la
    interfaz que se ve dentro del video está en castellano, y una narración en
    inglés sobre pantallas en español confunde más de lo que ayuda (es el
    mismo criterio que ya explica marketing/subtitulos.py)."""
    import inspect
    assert inspect.signature(A.construir).parameters["idioma"].default == "es"
    for _ini, _fin, textos in SUITE_CUES:
        for idioma in IDIOMAS:
            assert textos.get(idioma), "falta un idioma en los subtítulos"


def test_toda_voz_declara_su_licencia():
    """La licencia es el dato que decide una voz, no cómo suena — así que
    ninguna puede estar en el catálogo sin declararla.

    Se eligió la rioplatense (`es_AR-daniela-high`) porque es la que suena
    como el mercado del producto, y es CC BY-SA 4.0: el ShareAlike sobre una
    pieza comercial es un riesgo asumido a sabiendas, no un descuido. La
    alternativa Apache-2.0 sigue disponible con `--voz`.
    """
    assert A.VOCES, "el catálogo de voces no puede quedar vacío"
    for nombre, datos in A.VOCES.items():
        assert datos.get("licencia"), f"{nombre} no declara licencia"
        assert isinstance(datos.get("copyleft"), bool), (
            f"{nombre} no dice si su licencia es copyleft — que es lo único "
            "que hay que mirar antes de publicar con ella")
    assert A.PIPER_VOZ in A.VOCES
    # La que está marcada copyleft tiene que seguir marcada: si alguien la
    # pasa a False para que no moleste el aviso, este test lo frena.
    assert A.VOCES["es_AR-daniela-high"]["copyleft"] is True
    assert A.VOCES["es_MX-claude-high"]["copyleft"] is False


def test_una_voz_copyleft_avisa_en_pantalla(capsys, monkeypatch):
    """Elegir una voz con ShareAlike es legítimo, pero no puede pasar en
    silencio: el que corre esto tiene que enterarse antes de publicar."""
    monkeypatch.setattr(A, "construir", lambda **kw: {
        "salida": "x.webm", "motor": "piper", "voz": "es_AR-daniela-high",
        "licencia": "CC BY-SA 4.0", "duracion_video_original": 52.8,
        "duracion_final": 58.4, "congelado_s": 5.6, "cues": 8, "avisos": [],
        "hueco_max_s": 2.9, "wpm": [160], "wpm_promedio": 160.0})
    A.main([])
    salida = capsys.readouterr().out
    assert "CC BY-SA 4.0" in salida and "LICENCIA" in salida


def test_una_voz_inventada_se_rechaza():
    with pytest.raises(ValueError, match="voz desconocida"):
        A.construir(motor="piper", voz="la-de-mi-primo")


# --- El ritmo ---------------------------------------------------------------
def test_el_ritmo_apunta_a_locucion_y_no_a_llenar_el_hueco():
    """La voz rioplatense sale de fábrica a ~203 palabras/min, muy por encima
    del rango de una locución explicativa (140-160). Ahí la frase termina mucho
    antes que su pantalla y quedan pozos de silencio: el sube y baja entre
    atropello y silencio es lo que se escucha como narración entrecortada.

    El objetivo es el RITMO, medido en palabras por minuto, no un porcentaje
    de la ventana — así sirve para cualquier voz sin recalibrar nada.
    """
    assert 140 <= A.WPM_OBJETIVO <= 160
    # 18 palabras al ritmo objetivo son ~7 s. Con ventana de sobra, manda el
    # ritmo.
    texto = " ".join(["palabra"] * 18)
    assert A.duracion_objetivo(texto, ventana=30.0) == pytest.approx(
        18 / A.WPM_OBJETIVO * 60, rel=0.01)


def test_la_ventana_le_gana_al_ritmo():
    """Pero el ritmo ideal no puede pisar la pantalla siguiente: una frase
    larga en una ventana corta se dice al ritmo que entre."""
    texto = " ".join(["palabra"] * 40)      # ~15 s al ritmo ideal
    assert A.duracion_objetivo(texto, ventana=5.0) <= 5.0


def test_nunca_se_acelera_una_frase_para_que_entre():
    """Solo se afloja. Atropellar una frase para meterla en su ventana suena
    peor que medio segundo de solape con la pantalla siguiente."""
    assert A.ESCALA_MIN >= 1.0


def test_el_ajuste_de_velocidad_no_supone_que_sea_lineal():
    """`length_scale` no responde de forma lineal: medido en esta misma voz,
    subirla de 1,0 a 1,5 alarga un 32%, no un 50%. Por eso cada pasada parte
    de lo MEDIDO y corrige, en vez de calcular la escala una sola vez."""
    fuente = (ROOT / "marketing" / "audio_suite.py").read_text(encoding="utf-8")
    assert "CORRECCIONES_MAX" in fuente
    assert A.CORRECCIONES_MAX >= 2, "sin reintentos, una sola pasada no llega"


def test_un_texto_vacio_no_divide_por_cero():
    assert A.duracion_objetivo("", ventana=8.0) == 0.0
    assert A.palabras("   ") == 0


def test_falta_el_screencast_y_lo_dice(tmp_path):
    with pytest.raises(FileNotFoundError, match="screencast_suite"):
        A.construir(entrada=str(tmp_path / "no_existe.webm"), motor="piper")
