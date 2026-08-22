# © 2026 Martín Viera. Todos los derechos reservados.

"""Ningún control de la webapp puede quedar sin nombre.

Un `<input>` o un `<select>` sin nombre accesible es invisible para un lector
de pantalla: se anuncia como "edit" o "combo box" y nada más. Quien no ve la
pantalla no tiene forma de saber qué le están pidiendo.

Dos cosas que parecen un nombre y no lo son:

  * **El `placeholder`.** Desaparece apenas se escribe la primera letra, los
    lectores de pantalla lo tratan distinto según cuál sea, y varios no lo
    anuncian. Era el caso de los tres campos de contraseña del login y del de
    activación de licencia — literalmente lo primero que toca cualquiera que
    abre el producto.
  * **Un `<span>` al lado del control.** Se ve, pero no está asociado a nada:
    para la tecnología asistiva el `<select>` sigue sin nombre. Así estaban
    los filtros de Cartera y de Calidad.

Y una que SÍ lo es, y por eso este archivo la reconoce: un `<label>` que
ENVUELVE al control. Ahí agregar un `aria-label` sería peor que no ponerlo —
el `aria-label` pisa al texto visible, así que los dos se pueden desincronizar
y el lector termina diciendo algo distinto de lo que se ve en pantalla.

Nota sobre el conteo: la revisión de arquitectura decía "no hay ni un
`aria-label` en toda la app React". No era así — había 45 en 13 archivos. Lo
que faltaba de verdad se contó con este mismo detector, archivo por archivo,
antes de tocar nada.
"""
import os
import pathlib
import re

import pytest

ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PAGINAS = ROOT / "webapp" / "frontend" / "src"

_APERTURA = re.compile(r"<(input|select|textarea)\b")

# Componentes propios que renderizan un `<label>` envolviendo a sus hijos. Van
# acá solo después de leerlos: `Fila` (en Roi.jsx) hace
# `<label><span>{label}</span>{children}</label>`.
ENVOLTORIOS = ("label", "Fila")


def archivos_jsx():
    for archivo in sorted(PAGINAS.rglob("*.jsx")):
        if "node_modules" in archivo.parts:
            continue
        yield archivo


def _fin_de_etiqueta(texto: str, desde: int) -> int:
    """Dónde termina la etiqueta que abre en `desde`.

    A mano y no con una expresión regular porque JSX mete `>` adentro de los
    atributos todo el tiempo: `onChange={(e) => ...}`. Un regex que corta en el
    primer `>` se come la mitad de los atributos y reporta como "sin nombre" un
    control que tiene el `aria-label` en la línea siguiente. (Pasó: la primera
    versión de este archivo contó 62 controles y la mitad eran suyos.)
    """
    profundidad, comilla = 0, ""
    i = desde
    while i < len(texto):
        c = texto[i]
        if comilla:
            if c == comilla:
                comilla = ""
        elif c in "\"'":
            comilla = c
        elif c == "{":
            profundidad += 1
        elif c == "}":
            profundidad -= 1
        elif c == ">" and profundidad == 0:
            return i
        i += 1
    return len(texto)


def _regiones_envueltas(texto: str) -> list:
    regiones = []
    for etiqueta in ENVOLTORIOS:
        for m in re.finditer(rf"<{etiqueta}\b", texto):
            fin = texto.find(f"</{etiqueta}>", m.end())
            if fin != -1:
                regiones.append((m.start(), fin))
    return regiones


def _sin_comentarios(texto: str) -> str:
    """Blanquea los comentarios JSX conservando las posiciones.

    Un comentario que MENCIONA `<select>` no es un `<select>` — y en este
    repo los comentarios explican justamente eso, así que sin blanquearlos el
    detector se reporta a sí mismo. Se reemplaza por espacios en vez de
    borrarse para que los números de línea sigan siendo los del archivo.
    """
    def blanquear(m):
        return "".join(c if c == "\n" else " " for c in m.group(0))
    return re.sub(r"\{/\*.*?\*/\}", blanquear, texto, flags=re.DOTALL)


def controles_sin_nombre(texto: str) -> list:
    """Los controles que no tienen nombre por ningún camino.

    Vale `aria-label`, `aria-labelledby`, un `id` (que es lo que ata un
    `<label htmlFor>`) o estar envuelto por un `<label>`. `hidden`, `submit` y
    `button` no necesitan: el primero no se ve, los otros se nombran solos con
    su contenido.
    """
    texto = _sin_comentarios(texto)
    envueltos = _regiones_envueltas(texto)
    sin = []
    for m in _APERTURA.finditer(texto):
        attrs = texto[m.end():_fin_de_etiqueta(texto, m.end())]
        if re.search(r"""type=["']?(hidden|submit|button)""", attrs):
            continue
        if re.search(r"aria-label|aria-labelledby|\bid=", attrs):
            continue
        if any(ini < m.start() < fin for ini, fin in envueltos):
            continue
        sin.append((texto[:m.start()].count("\n") + 1,
                    " ".join(attrs.split())[:70]))
    return sin


@pytest.mark.parametrize(
    "archivo", [p.relative_to(PAGINAS).as_posix() for p in archivos_jsx()])
def test_cada_control_tiene_nombre(archivo):
    sin = controles_sin_nombre((PAGINAS / archivo).read_text(encoding="utf-8"))
    assert not sin, (
        f"{archivo}: controles sin nombre accesible — un placeholder no cuenta "
        f"y un <span> al lado tampoco: {sin}")


def test_el_detector_reconoce_un_label_que_envuelve():
    """Si esto se rompe, el archivo pide `aria-label` donde ya hay un `<label>`
    — y agregarlo ahí EMPEORA las cosas: el `aria-label` pisa al texto visible
    y los dos se desincronizan."""
    assert controles_sin_nombre(
        '<label>Monto <input type="number" /></label>') == []
    assert controles_sin_nombre('<div>Monto <input type="number" /></div>')


def test_un_comentario_que_menciona_un_control_no_es_un_control():
    """Los comentarios de este repo explican por qué tal `<select>` necesita
    nombre. Sin blanquearlos, el detector se reporta a sí mismo."""
    assert controles_sin_nombre(
        '{/* el <select> de abajo no tenia nombre */}'
        '<select aria-label="Canal"></select>') == []


def test_el_detector_no_se_corta_en_una_flecha():
    """`onChange={(e) => ...}` tiene un `>` adentro. Un detector que corta ahí
    reporta como sin nombre a un control que lo tiene."""
    jsx = ('<select onChange={(e) => setX(e.target.value)}\n'
           '        aria-label="Canal">')
    assert controles_sin_nombre(jsx) == []


def test_los_campos_de_contrasena_le_hablan_al_gestor_de_contrasenas():
    """`autoComplete` es la diferencia entre que el navegador ofrezca guardar
    la clave o no. Al crear la contraseña tiene que decir `new-password` y al
    entrar `current-password`: al revés, el gestor ofrece guardar la clave
    vieja o autocompleta donde no debe."""
    login = (PAGINAS / "pages" / "Login.jsx").read_text(encoding="utf-8")
    assert 'autoComplete="new-password"' in login
    assert 'autoComplete="current-password"' in login


def test_el_login_y_la_activacion_son_las_primeras_pantallas():
    """Las dos que ve cualquiera antes de entrar. Si alguien saca los nombres
    de acá, que falle con el motivo escrito."""
    for pagina in ("pages/Login.jsx", "pages/Activacion.jsx"):
        texto = (PAGINAS / pagina).read_text(encoding="utf-8")
        assert "aria-label" in texto, (
            f"{pagina} es la primera pantalla del producto y sus campos "
            "volvieron a quedar sin nombre")
