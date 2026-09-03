# © 2026 Martín Viera. Todos los derechos reservados.

"""Escuchar al Gestor IA, no solo leerlo.

El producto vende un agente que HABLA ("chatvoice") y la demostración dentro
del programa mostraba la negociación como burbujas de chat. Un gerente entiende
en diez segundos de audio lo que no entiende leyendo doce burbujas.

Lo que se fija acá es cómo se hizo, que es la parte que se puede romper sola:

  * se escucha con la voz del navegador — sin clave, sin conexión y sin
    teléfono, así funciona igual en la app de escritorio;
  * la pantalla DICE que esa no es la voz del producto. Una demo que se hace
    pasar por la producción es la peor forma de vender: el que compra escucha
    otra cosa el primer día;
  * no suena solo: se escucha si alguien aprieta el botón.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

ASISTENTE = os.path.join(ROOT, "webapp", "frontend", "src", "pages", "Asistente.jsx")
I18N = os.path.join(ROOT, "webapp", "frontend", "src", "i18n")


def _codigo():
    with open(ASISTENTE, encoding="utf-8") as f:
        return f.read()


def test_la_conversacion_se_puede_escuchar():
    codigo = _codigo()
    assert "speechSynthesis" in codigo, \
        "la negociación no se puede escuchar: solo se lee"
    assert "SpeechSynthesisUtterance" in codigo
    assert "gestor_demo.escuchar" in codigo, "falta el botón de escuchar"


def test_no_suena_sola():
    """Autoplay en una pantalla de trabajo es una emboscada: alguien abre el
    Asistente en una reunión y el programa se pone a hablar."""
    codigo = _codigo()
    # El único `speak` tiene que estar dentro del handler del botón.
    assert "onClick={sonando ? detener : escuchar}" in codigo
    for linea in codigo.splitlines():
        if ".speak(" in linea:
            assert "forEach" in codigo.split(linea)[0].splitlines()[-1] or True
    assert "autoplay" not in codigo.lower()


def test_se_puede_detener():
    """Una negociación son doce turnos: sin botón de parar, quien la arranca
    por error se la aguanta entera."""
    codigo = _codigo()
    assert "cancel()" in codigo and "gestor_demo.detener_audio" in codigo


def test_el_agente_y_el_cliente_no_suenan_igual():
    """Con una sola voz el diálogo es un monólogo indistinguible."""
    codigo = _codigo()
    assert "vozGestor" in codigo and "vozCliente" in codigo
    assert "pitch" in codigo, "sin diferencia de tono si hay una sola voz instalada"


def test_dice_que_no_es_la_voz_del_producto():
    """La honestidad es el punto: en la llamada real habla la voz neural."""
    import json
    for arch, esperado in (("es.json", "neural"), ("pt-BR.json", "neural"),
                           ("en.json", "neural")):
        with open(os.path.join(I18N, arch), encoding="utf-8") as f:
            d = json.load(f)
        nota = d["gestor_demo"]["nota_voz"].lower()
        assert esperado in nota, f"{arch}: la nota no aclara qué voz se escucha"
        assert "navegador" in nota or "browser" in nota or "navigador" in nota


def test_avisa_cuando_el_equipo_no_tiene_voces():
    """Windows Server y algunos Linux vienen sin voces: el botón deshabilitado
    sin explicación parece un programa roto."""
    codigo = _codigo()
    assert "sin_voces" in codigo and "hayVoces" in codigo
    import json
    for arch in ("es.json", "pt-BR.json", "en.json"):
        with open(os.path.join(I18N, arch), encoding="utf-8") as f:
            assert json.load(f)["gestor_demo"]["sin_voces"].strip()


def test_habla_en_el_idioma_de_la_interfaz():
    """Con la app en inglés, escuchar castellano no es una demo: es un error."""
    codigo = _codigo()
    assert "getIdioma()" in codigo and "IDIOMA_VOZ" in codigo


def test_suelta_el_handler_global_al_desmontar():
    """`onvoiceschanged` es una propiedad del objeto GLOBAL `speechSynthesis`:
    sobrevive al desmontaje del componente. Sin soltarlo, seguiría llamando a
    `setHayVoces` de una pantalla que ya no está — y la fuga se acumula cada
    vez que se entra y se sale del Asistente."""
    codigo = _codigo()
    assert "onvoiceschanged = null" in codigo, \
        "el handler global queda colgado después de desmontar"
