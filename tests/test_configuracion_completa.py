# © 2026 Martín Viera. Todos los derechos reservados.

"""La configuración que hace falta para vender tiene que estar escrita y ser
comprobable.

Las cuatro cosas que bloquean una venta —cobrar, firmar la licencia, mandarla
y dejar bajar el instalador— fallan de formas distintas y ninguna grita. Sin
`RESEND_FROM` el comprador no recibe nada y desde el lado del dueño se ve todo
bien, porque a él sí le llega la copia. Descubrirlo con un cliente adentro es
caro.

Lo que se fija acá: que la plantilla exista, que no se desincronice del código,
y —lo más importante— que NUNCA lleve un valor real.
"""
import os
import pathlib
import subprocess
import sys

import pytest

ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PLANTILLA = ROOT / "env.example"
VERIFICADOR = ROOT / "verificar_configuracion.py"

# Las que, sin ellas, alguien paga y algo se rompe.
CRITICAS = ("MP_ACCESS_TOKEN", "KOBRA_LICENSE_PRIVATE_KEY", "RESEND_API_KEY",
            "RESEND_FROM", "RELEASES_TOKEN")


def _plantilla():
    return PLANTILLA.read_text(encoding="utf-8")


def _pares(texto):
    """`{CLAVE: valor}` de la plantilla, ignorando comentarios."""
    out = {}
    for linea in texto.splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        k, _, v = linea.partition("=")
        out[k.strip()] = v.strip()
    return out


def test_la_plantilla_existe():
    assert PLANTILLA.exists(), "falta env.example"


@pytest.mark.parametrize("variable", CRITICAS)
def test_estan_todas_las_criticas(variable):
    """Si una falta en la plantilla, el que configura el proyecto no se entera
    de que existe hasta que un cliente paga y algo no llega."""
    assert variable in _plantilla(), (
        f"{variable} no está en env.example: sin ella alguien paga y algo se rompe")


@pytest.mark.parametrize("variable", CRITICAS)
def test_cada_critica_explica_que_pasa_si_falta(variable):
    """Un nombre de variable suelto no le dice a nadie qué se rompe. La
    plantilla tiene que traer la consecuencia, que es lo que hace que se
    configure ANTES de vender y no después."""
    texto = _plantilla()
    bloque = texto.split(variable)[0][-900:]
    assert "SIN ESTO" in bloque or "OJO" in bloque, (
        f"{variable} no explica qué se rompe si falta")


def test_la_plantilla_no_trae_ningun_valor_real():
    """El control que importa. La plantilla SE VERSIONA: un valor real acá es
    un secreto en el repositorio, y lo que entra al historial de git no se
    borra con un commit — hay que rotarlo.
    """
    vacias_obligatorias = set(CRITICAS) | {
        "KOBRA_LICENSE_SECRET", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
        "ELEVENLABS_API_KEY", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN",
        "KOBRA_BACKEND_ADMIN_TOKEN", "KOBRA_REALTIME_TOKEN",
    }
    for clave, valor in _pares(_plantilla()).items():
        if clave in vacias_obligatorias:
            assert valor == "", (
                f"{clave} tiene un valor en env.example: si es real, es un "
                "secreto commiteado y hay que rotarlo")


def test_los_defaults_documentados_son_los_del_codigo():
    """`MP_CURRENCY` y `MP_TASA_UYU` sí llevan valor porque son los defaults.
    Si el código cambia y la plantilla no, alguien configura mal creyendo que
    está copiando lo que hace el programa."""
    pares = _pares(_plantilla())
    checkout = (ROOT / "api" / "checkout.js").read_text(encoding="utf-8")
    assert f'|| "{pares["MP_CURRENCY"]}"' in checkout, (
        "la moneda por defecto de env.example no es la de api/checkout.js")
    assert f"|| {pares['MP_TASA_UYU']}" in checkout, (
        "la tasa por defecto de env.example no es la de api/checkout.js")


def test_no_promete_variables_que_el_codigo_no_lee():
    """Una plantilla con variables inventadas manda a configurar cosas que no
    hacen nada, y esconde las que sí importan."""
    fuentes = []
    for sub in ("kobra", "backend_venta", "api", "webapp", "realtime"):
        for ruta in (ROOT / sub).rglob("*"):
            if ruta.suffix in (".py", ".js") and "node_modules" not in str(ruta):
                fuentes.append(ruta.read_text(encoding="utf-8", errors="replace"))
    todo = "\n".join(fuentes)
    for clave in _pares(_plantilla()):
        assert clave in todo, (
            f"env.example nombra {clave}, que no aparece en el código")


# --- El verificador ---------------------------------------------------------
def test_el_verificador_corre_y_avisa_lo_que_falta():
    """Sin ninguna variable puesta tiene que salir 1 y nombrar las críticas."""
    entorno = {k: v for k, v in os.environ.items() if k not in CRITICAS}
    entorno["PATH"] = os.environ.get("PATH", "")
    r = subprocess.run([sys.executable, str(VERIFICADOR)], cwd=ROOT,
                       capture_output=True, text=True, env=entorno)
    assert r.returncode == 1, "no marcó que falta configuración"
    for variable in CRITICAS:
        assert variable in r.stdout


def test_el_verificador_nunca_imprime_un_valor():
    """Se corre compartiendo pantalla y su salida se pega en un chat. Que
    imprima aunque sea un fragmento de una clave la filtra."""
    secreto = "APP_USR-secreto-que-no-debe-aparecer-1234567890"
    entorno = dict(os.environ)
    entorno["MP_ACCESS_TOKEN"] = secreto
    r = subprocess.run([sys.executable, str(VERIFICADOR), "--todas"], cwd=ROOT,
                       capture_output=True, text=True, env=entorno)
    assert secreto not in r.stdout
    for trozo in (secreto[:12], secreto[-12:]):
        assert trozo not in r.stdout, "imprimió parte del valor de la variable"


def test_el_verificador_reconoce_una_variable_puesta():
    entorno = dict(os.environ)
    entorno["MP_ACCESS_TOKEN"] = "APP_USR-loquesea"
    r = subprocess.run([sys.executable, str(VERIFICADOR)], cwd=ROOT,
                       capture_output=True, text=True, env=entorno)
    linea = [x for x in r.stdout.splitlines() if "MP_ACCESS_TOKEN" in x][0]
    assert "[ok]" in linea


def test_las_de_twilio_no_se_piden_en_el_servidor_del_dueno():
    """Modelo BYO: las pone cada cliente en su instalación. Listarlas como
    'falta configurar' mandaría al dueño a cargar credenciales de telefonía
    que no son suyas."""
    salida = subprocess.run([sys.executable, str(VERIFICADOR)], cwd=ROOT,
                            capture_output=True, text=True).stdout
    assert "BYO" in salida
    bloque_vender = salida.split("OPCIONALES")[0]
    assert "TWILIO" not in bloque_vender, (
        "Twilio aparece entre las que bloquean la venta, y no lo es")


def test_el_gitignore_sigue_cubriendo_el_env_de_verdad():
    """La plantilla se versiona; el `.env` que sale de copiarla, no."""
    r = subprocess.run(["git", "check-ignore", "-q", ".env"], cwd=ROOT)
    assert r.returncode == 0, "`.env` dejó de estar ignorado"
    r2 = subprocess.run(["git", "check-ignore", "-q", "env.example"], cwd=ROOT)
    assert r2.returncode != 0, "la plantilla quedó ignorada y no se versiona"


def test_la_guia_de_produccion_menciona_el_verificador():
    """Si el script no está en la guía, nadie lo corre."""
    guia = (ROOT / "docs" / "PUESTA_EN_PRODUCCION_VERCEL.md").read_text(encoding="utf-8")
    assert "verificar_configuracion.py" in guia
