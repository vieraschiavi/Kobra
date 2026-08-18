# © 2026 Martín Viera. Todos los derechos reservados.

"""Las pantallas que ve un cliente no se ven como un chat.

Un producto de cobranzas se vende a un gerente de riesgo o a un CFO. El
pictograma a color —🤖 en un título, 🎯 en una sección, 🚀 en un botón— no
aporta información (la aporta la etiqueta) y sí aporta una lectura: "esto lo
escribió una IA". En una herramienta que va a manejar la cartera de una
empresa, eso resta.

Había 245 en el dashboard Streamlit y 313 en la demo estática. La app React
—que es el producto principal— tenía uno solo, porque su iconografía son SVG
propios: ese es el estándar que este test extiende al resto.

Qué SÍ se permite y por qué:

* **Marcas tipográficas** — → ← ⬇ ⬆ ✓ ✗ ★ ● ○ ▶ ⚠ ⚙. Son glifos de texto:
  heredan el color y el tamaño de la fuente, se imprimen bien y no cambian de
  dibujo entre Windows, Mac y Android.
* **Banderas de país** (🇺🇾 🇧🇷 🇲🇽) en el selector de país de la landing. Ahí
  el pictograma ES el dato, y no hay equivalente tipográfico.

Y una regla que salió de arreglar esto: el semáforo 🟢🟡🔴 pasó a no existir en
vez de convertirse en un ● único. Cuatro estados con el mismo dibujo es peor
que ninguno, y los títulos ("Cliente enojado", "Señal de compra") ya dicen lo
que el color decía. No depender del color para transmitir información es
además lo que pide WCAG 1.4.1.
"""
import os
import re
import subprocess

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Lo que ve un cliente. Los docs internos, los tests y CLAUDE.md quedan afuera
# a propósito: ahí el emoji es para nosotros y no le llega a nadie.
SUPERFICIES = (
    "webapp/frontend/src/",     # la app de escritorio (React + Electron)
    "app/app.py",               # el dashboard Streamlit
    "dashboard_estatico/",      # la demo web
    "landing/",                 # el sitio público
)

EXTS = (".py", ".js", ".jsx", ".json", ".html", ".css")
EXCLUIR = ("node_modules/", "package-lock", ".min.js", "chart.umd", "xlsx.full",
           "botid-init.js", "/audio_demo/", "/video/", "KEYS_MAP.md")

# El bloque de pictogramas a color. No incluye flechas, formas geométricas ni
# símbolos misceláneos, que son tipográficos.
PICTOGRAMA = re.compile("[\U0001F300-\U0001FAFF]")
# Indicadores regionales: los pares forman las banderas de país.
BANDERA = re.compile("[\U0001F1E6-\U0001F1FF]")


def _archivos():
    salida = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.splitlines()
    for rel in salida:
        if not any(rel.startswith(s) for s in SUPERFICIES):
            continue
        if not rel.endswith(EXTS) or any(x in rel for x in EXCLUIR):
            continue
        ruta = os.path.join(ROOT, rel)
        if not os.path.isfile(ruta):
            continue
        with open(ruta, encoding="utf-8", errors="ignore") as f:
            yield rel, f.read()


@pytest.mark.parametrize("superficie", SUPERFICIES)
def test_no_hay_pictogramas_de_chat(superficie):
    hallazgos = []
    for rel, texto in _archivos():
        if not rel.startswith(superficie):
            continue
        for linea_n, linea in enumerate(texto.splitlines(), 1):
            for m in PICTOGRAMA.finditer(linea):
                if BANDERA.match(m.group(0)):
                    continue          # el selector de país de la landing
                hallazgos.append(f"{rel}:{linea_n} → {m.group(0)}  «{linea.strip()[:60]}»")
    assert not hallazgos, (
        f"hay pictogramas a color en {superficie}, que es una pantalla de "
        "cliente:\n  " + "\n  ".join(hallazgos[:20]) +
        "\n\nUsá una marca tipográfica (→ ✓ ⚠ ● ▶) o, mejor, ninguna: la "
        "etiqueta ya dice qué es.")


def test_el_semaforo_no_quedo_en_un_unico_punto():
    """Regresión del arreglo: al sacar 🟢🟡🔴 quedaron cuatro estados del
    copiloto con el mismo `●`, que se ve prolijo y no dice nada. El título es
    el que informa."""
    ruta = os.path.join(ROOT, "dashboard_estatico", "copiloto.js")
    with open(ruta, encoding="utf-8") as f:
        js = f.read()
    puntos = js.count('"● ') + js.count("'● ")
    assert puntos == 0, (
        f"quedaron {puntos} títulos del copiloto empezando con '● '. Cuatro "
        "estados con el mismo dibujo no distinguen nada — sacá la marca.")


def test_la_app_react_sigue_usando_sus_iconos_propios():
    """El estándar del que salió todo esto: la app principal dibuja sus íconos
    con SVG en `icons.jsx`, no con pictogramas del sistema. Así heredan el
    color del tema y se ven igual en cualquier máquina."""
    ruta = os.path.join(ROOT, "webapp", "frontend", "src", "icons.jsx")
    assert os.path.isfile(ruta), "desapareció el set de íconos propio"
    with open(ruta, encoding="utf-8") as f:
        iconos = f.read()
    # Se cuentan los íconos exportados y no los `<svg>`: todos comparten un
    # único wrapper `<S>` que fija tamaño, trazo y `currentColor`, así que hay
    # un solo `<svg>` en el archivo por diseño.
    assert iconos.count("export const Ico") >= 10, \
        "el set de íconos quedó casi vacío"
    assert "currentColor" in iconos, \
        "los íconos dejaron de heredar el color del texto"
    assert not PICTOGRAMA.search(iconos), \
        "se coló un pictograma en el set de íconos"
