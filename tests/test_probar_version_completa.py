# © 2026 Martín Viera. Todos los derechos reservados.

"""El dueño tiene que poder correr la edición completa sin esperar a nadie.

El camino ya existía —`kobra/owner.py` desbloquea owner en CUALQUIER build,
incluido el instalador público— pero no estaba escrito en ningún lado. El
resultado previsible: se terminó buscando un instalador Owner separado, que no
hace falta y que además no puede commitearse.

Estos tests fijan que la guía diga lo correcto y que no invite a hacer
justamente lo que el repo prohíbe.
"""
import os
import pathlib

from kobra import ayuda as kayuda
from kobra import owner as kowner

ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GUIA = ROOT / "docs" / "PROBAR_VERSION_COMPLETA.md"


def _texto():
    return GUIA.read_text(encoding="utf-8")


def test_la_guia_existe():
    assert GUIA.exists(), "falta docs/PROBAR_VERSION_COMPLETA.md"


def test_el_asistente_de_ayuda_la_encuentra():
    """Si no está en las fuentes, el asistente no la va a ofrecer nunca — y el
    problema que resuelve es justamente que nadie sabía que el camino existía."""
    assert "docs/PROBAR_VERSION_COMPLETA.md" in kayuda.FUENTES_DOCS


def test_explica_el_formato_exacto_de_la_credencial():
    """`mail|codigo`, pegado y sin espacios. Es el detalle que hace que el
    desbloqueo funcione o no, y el que no se puede adivinar."""
    t = _texto()
    assert kowner.EMAIL in t, "la guía no dice con qué mail se desbloquea"
    assert kowner.SEPARADOR in t, "no muestra el separador entre mail y código"
    assert f"{kowner.EMAIL}{kowner.SEPARADOR}" in t, (
        "el ejemplo no muestra mail y código pegados por el separador")


def test_no_publica_el_codigo():
    """La guía explica CÓMO se usa el código, nunca cuál es. El código en claro
    no está en el repositorio y no puede estar (lo fija además
    tests/test_owner_desbloqueo.py)."""
    t = _texto()
    # El placeholder tiene que ser evidentemente un placeholder.
    assert "TU-CODIGO" in t
    # Y no puede haber una cadena de 25 caracteres del alfabeto del código
    # pegada al separador, que sería el código de verdad.
    import re
    sospechosas = re.findall(
        re.escape(kowner.EMAIL) + re.escape(kowner.SEPARADOR) + r"([A-Z2-9]{20,})", t)
    assert not sospechosas, f"la guía parece traer un código real: {sospechosas}"


def test_dice_como_rotar_el_codigo_si_se_perdio():
    assert "--nuevo-codigo" in _texto(), (
        "sin esto, perder el código deja al dueño sin forma de entrar")


def test_explica_por_que_no_hay_instalador_owner_en_el_repo():
    """La pregunta que originó la guía. Si no está contestada acá, se vuelve a
    hacer — y la respuesta correcta no es obvia: el instalador Owner en el repo
    es el producto completo regalado a cualquiera con acceso, ahora o después.
    """
    t = _texto()
    assert "test_owner_no_se_regala" in t, (
        "no menciona el test que impide publicar la edición Owner")
    assert "Owner.bat" in t and ".gitignore" in t, (
        "no explica por qué packaging/Owner.bat está ignorado")


def test_apunta_al_instalador_que_de_verdad_existe():
    """v1.5.0 con `MVKobraAI_Setup.exe` está publicado. La guía tiene que
    mandar ahí y no a una release Owner que hoy no existe."""
    t = _texto()
    assert "MVKobraAI_Setup.exe" in t
    assert "releases/tag/v1.5.0" in t


def test_no_promete_una_release_owner_que_no_existe():
    """`owner-v1.5.0` no está publicada. La guía puede explicar esa vía, pero
    tiene que decir que hoy está bloqueada y por qué — no mandar al dueño a
    buscar una descarga que no va a encontrar."""
    t = _texto()
    if "owner-v" in t:
        assert "cuota" in t.lower() or "bloquead" in t.lower(), (
            "menciona la release Owner sin aclarar que hoy no se puede generar")
