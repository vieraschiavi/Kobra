# © 2026 Martín Viera. Todos los derechos reservados.
"""La INTERFAZ de la demo tiene que hablar los tres idiomas, no solo el guion.

`test_idiomas_demo.py` ya cubría los guiones de la llamada, el chat y los
subtítulos del video. Faltaba el resto de la pantalla, que es casi toda: el
selector ES/PT/EN funcionaba —recargaba con `?lang=`, resolvía `IDIOMA_DEMO`,
marcaba el botón activo— pero los KPIs, los filtros, los encabezados de tabla,
los botones, el copiloto y el bloque del ERP estaban escritos a mano en
castellano dentro de `index.html`. Medido en Chromium antes de arreglarlo:

    ?lang=pt → 429 de 469 líneas de texto IDÉNTICAS al español (91%)
    ?lang=en → 429 de 469 líneas de texto IDÉNTICAS al español (91%)

O sea: elegir otro idioma no cambiaba nada visible. Estos tests fijan las tres
formas en que eso se rompe.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

from kobra import rutas as krutas

DEMO = os.path.join(krutas.ROOT_REPO, "dashboard_estatico")
INDEX = os.path.join(DEMO, "index.html")
GUIONES = os.path.join(DEMO, "guiones.js")
COPILOTO = os.path.join(DEMO, "copiloto.js")
IDIOMAS = ("es", "pt", "en")

NODE = shutil.which("node")
sin_node = pytest.mark.skipif(NODE is None, reason="node no está instalado")


def _node(script: str):
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                     encoding="utf-8") as f:
        f.write(script)
        ruta = f.name
    try:
        r = subprocess.run([NODE, ruta], capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, f"node falló:\n{r.stderr[:2000]}"
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(ruta)


def _cargar(lang: str = "es") -> dict:
    """Carga `guiones.js` como lo cargaría el navegador, con su `?lang=`."""
    return _node(f"""
      import fs from 'node:fs';
      const w = {{location: {{search: '?lang={lang}'}},
                 localStorage: {{getItem: () => null}}}};
      globalThis.window = w;
      // En Node 22 `navigator` es de solo lectura: hay que redefinirla.
      Object.defineProperty(globalThis, 'navigator',
        {{value: {{language: 'es'}}, configurable: true}});
      new Function('window', fs.readFileSync({json.dumps(GUIONES)}, 'utf8')).call(w, w);
      console.log(JSON.stringify({{
        idioma: w.IDIOMA_DEMO,
        ui: Object.fromEntries(Object.entries(w.GUIONES).map(([k, v]) => [k, v.ui])),
        muestra: w.T('kpi_deudores'),
        conVars: w.T('t_info', {{n: 42}}),
        inexistente: w.T('no_existe_esta_clave'),
      }}));
    """)


# --- el diccionario ----------------------------------------------------------

@sin_node
def test_los_tres_idiomas_tienen_exactamente_las_mismas_claves():
    """Una clave que falta en un idioma es un hueco en blanco en pantalla.

    Es el modo de falla barato de este diseño: alguien agrega una etiqueta en
    español y se olvida de las otras dos, y la demo en inglés queda con un KPI
    sin título. Que reviente acá y no delante de un cliente.
    """
    ui = _cargar()["ui"]
    assert set(ui) == set(IDIOMAS), f"idiomas presentes: {sorted(ui)}"
    base = set(ui["es"])
    for lang in ("pt", "en"):
        faltan = base - set(ui[lang])
        sobran = set(ui[lang]) - base
        assert not faltan, f"a '{lang}' le faltan {len(faltan)} claves: {sorted(faltan)[:8]}"
        assert not sobran, f"'{lang}' tiene claves que el español no: {sorted(sobran)[:8]}"
    assert len(base) > 100, f"el diccionario tiene solo {len(base)} claves"


@sin_node
def test_ninguna_traduccion_quedo_vacia():
    """Traducir a cadena vacía es peor que no traducir: borra la etiqueta."""
    ui = _cargar()["ui"]
    for lang in IDIOMAS:
        vacias = [k for k, v in ui[lang].items() if not str(v).strip()]
        assert not vacias, f"'{lang}' tiene traducciones vacías: {vacias}"


@sin_node
def test_los_marcadores_de_variable_sobreviven_a_la_traduccion():
    """`{n}`, `{archivo}`, `{e}`… si un idioma pierde el marcador, el texto sale
    sin el número: "filtered records · showing top 300" sin el cuánto."""
    ui = _cargar()["ui"]
    for clave, texto in ui["es"].items():
        marcadores = set(re.findall(r"\{(\w+)\}", str(texto)))
        if not marcadores:
            continue
        for lang in ("pt", "en"):
            otros = set(re.findall(r"\{(\w+)\}", str(ui[lang][clave])))
            assert otros == marcadores, (
                f"'{lang}.{clave}' tiene los marcadores {sorted(otros)} y el "
                f"español {sorted(marcadores)}")


@sin_node
@pytest.mark.parametrize("lang", IDIOMAS)
def test_el_parametro_lang_de_la_url_manda(lang):
    """`?lang=` es lo que usa el selector al recargar, y lo único que funciona
    offline: en el paquete que se abre con doble clic no hay landing que haya
    dejado la preferencia en `localStorage`."""
    assert _cargar(lang)["idioma"] == lang


@sin_node
def test_el_traductor_reemplaza_variables_y_no_rompe_con_una_clave_inventada():
    r = _cargar()
    assert r["muestra"], "T() no devolvió la etiqueta de un KPI"
    assert "42" in r["conVars"] and "{n}" not in r["conVars"], (
        f"T() no reemplazó el marcador: {r['conVars']!r}")
    assert r["inexistente"] == "", (
        "una clave inexistente debe dar cadena vacía, no tirar la página abajo")


@sin_node
def test_las_traducciones_son_distintas_y_no_el_castellano_copiado():
    """El atajo tentador es copiar el bloque español en las otras dos tablas.

    Se miran solo las claves con prosa (>25 caracteres): las cortas coinciden
    de verdad entre idiomas —"WhatsApp", "SMS", "Retail"— y contarlas como
    falta de traducción daría un test que miente.
    """
    ui = _cargar()["ui"]
    largas = [k for k, v in ui["es"].items() if len(str(v)) > 25]
    assert len(largas) > 30, "muy pocas claves con prosa para que el test valga"
    for lang in ("pt", "en"):
        iguales = [k for k in largas if ui[lang][k] == ui["es"][k]]
        assert len(iguales) <= 2, (
            f"'{lang}' tiene {len(iguales)} textos largos idénticos al "
            f"español: {iguales[:6]}")


# --- que no vuelva el texto hardcodeado -------------------------------------

# Literales que estaban escritos a mano en index.html y hacían que elegir otro
# idioma no cambiara nada. Si alguno vuelve al archivo, volvió el bug.
FRASES_QUE_NO_PUEDEN_VOLVER = [
    "'Deudores'", "'Cartera (UYU)'", "'ProbPago promedio'", "'Mora promedio'",
    "'Cartera en riesgo'", "'Calidad de gestión'", "'Clima del cliente'",
    "'Emoción dominante'", "'Técnicas usadas'", "'Gestiones cerradas'",
    "'Sincronizadas al ERP'", "'Pendientes de sync'", "'Recuperado (30 días)'",
    "label:'Cartera'", "label:'Recupero esperado'", "label:'Recuperado (UYU)'",
    ">Todos<", "registros filtrados", "turnos analizados",
    "'Estado ERP'", "'Cuentas scoreadas'",
]


def test_las_etiquetas_de_la_interfaz_no_estan_hardcodeadas():
    html = open(INDEX, encoding="utf-8").read()
    vuelven = [f for f in FRASES_QUE_NO_PUEDEN_VOLVER if f in html]
    assert not vuelven, (
        f"volvieron a index.html textos sin traducir: {vuelven}. "
        "Van al diccionario de guiones.js y se leen con T('clave').")


def test_los_titulos_visibles_estan_marcados_para_traducir():
    """Cada `<h2>` de tarjeta lleva `data-i18n`, que es lo que aplica
    `traducirDOM()` al cargar la página."""
    html = open(INDEX, encoding="utf-8").read()
    # Sin los <script>: adentro hay <h2> que son parte de los documentos que se
    # exportan (Word/PDF), no elementos de la página.
    cuerpo = re.sub(r"<script\b.*?</script>", "", html.split("<body", 1)[1], flags=re.S)
    sin_marcar = []
    for m in re.finditer(r"<h2\b([^>]*)>(.*?)</h2>", cuerpo, re.S):
        texto = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if texto and "data-i18n" not in m.group(1):
            sin_marcar.append(texto[:50])
    assert not sin_marcar, f"títulos sin data-i18n: {sin_marcar}"


def test_la_pagina_aplica_las_traducciones_al_cargar():
    html = open(INDEX, encoding="utf-8").read()
    assert "window.traducirDOM()" in html, (
        "nadie llama a traducirDOM(): los data-i18n quedan decorativos")
    assert 'data-i18n="pie"' in html and 'data-i18n="badge"' in html


@sin_node
def test_todas_las_claves_que_usa_el_codigo_existen_en_el_diccionario():
    """El error opuesto al anterior: llamar a `T('clave_que_no_existe')`.

    No rompe la página —T() devuelve cadena vacía— y por eso es peor: deja un
    hueco mudo que solo se descubre mirando la pantalla.
    """
    claves = set(_cargar()["ui"]["es"])
    usadas, prefijos = set(), set()
    for ruta in (INDEX, COPILOTO):
        txt = open(ruta, encoding="utf-8").read()
        usadas |= set(re.findall(r"""\bT\(\s*['"]([\w.]+)['"]\s*[,)]""", txt))
        usadas |= set(re.findall(r"""data-i18n(?:-html)?=["']([\w.]+)["']""", txt))
        # Las que se arman concatenando: T('prop_'+v), T('emo_'+e), T('d_'+v).
        prefijos |= set(re.findall(r"""\bT\(\s*['"](\w+_)['"]\s*\+""", txt))
    for p in prefijos:
        assert any(k.startswith(p) for k in claves), (
            f"el código arma claves con el prefijo '{p}' y el diccionario no "
            "tiene ninguna")
    faltan = sorted(usadas - claves)
    assert not faltan, f"el código usa claves que no están en el diccionario: {faltan}"


def test_los_valores_del_dato_no_se_traducen_solo_su_etiqueta():
    """Traducir el VALOR rompería los filtros y los colores.

    `segmento_propension` vale 'Alta'/'Media'/'Baja' y con eso se filtra, se
    elige la clase CSS del pill y se pinta el gráfico. Lo que se traduce es lo
    que se muestra; el dato queda como viene del pipeline.
    """
    html = open(INDEX, encoding="utf-8").read()
    assert "opts:['Alta','Media','Baja']" in html, (
        "los valores del filtro de propensión dejaron de ser los del dataset")
    assert 'class="pill ${esc(r[c])}">${esc(propLabel(r[c]))}' in html, (
        "el pill de propensión tiene que llevar la clase del DATO y el texto "
        "traducido; si se traduce la clase, se pierden los colores")
    assert "<option value=\"${esc(o)}\">${esc(et(o))}</option>" in html, (
        "el <option> tiene que guardar el valor del dato y mostrar la etiqueta")


def test_el_copiloto_offline_no_impone_el_castellano():
    """`copiloto.js` también se sirve desde `backend_venta`, sin `guiones.js`.

    Por eso sus textos van con literal de respaldo en vez de depender del
    diccionario: traducido cuando hay diccionario, en castellano cuando no,
    nunca en blanco.
    """
    js = open(COPILOTO, encoding="utf-8").read()
    assert "window.T && window.T(" in js, (
        "copiloto.js dejó de consultar el diccionario: sus sugerencias vuelven "
        "a salir siempre en castellano")
    assert "const t = (clave, esp" in js, (
        "copiloto.js perdió el literal de respaldo: servido sin guiones.js "
        "mostraría las sugerencias vacías")


# --- la landing, que es por donde se entra -----------------------------------

LANDING = os.path.join(krutas.ROOT_REPO, "landing", "index.html")


def test_la_landing_tambien_respeta_el_lang_de_la_url():
    """Era el bug simétrico al del demo.

    El demo leía `?lang=` y no tenía diccionario; la landing tenía diccionario
    completo (`I18N` + `data-i`) y **no leía `?lang=`**: solo miraba
    `localStorage`. Resultado medido en Chromium: abrir `/?lang=en` dejaba la
    página 100% en castellano, con `html.lang="es"`. Compartir el link en otro
    idioma no servía para nada, y como el link al demo se reescribe recién
    cuando alguien toca el selector, el visitante tampoco llegaba al demo
    traducido.
    """
    html = open(LANDING, encoding="utf-8").read()
    assert "URLSearchParams(location.search).get('lang')" in html, (
        "la landing volvió a ignorar ?lang= de la URL")
    # langRuta (agregado para /en/ y /pt/, ver marketing/generar_paginas_idioma.py)
    # pesa más que lo guardado pero menos que un ?lang= explícito.
    assert "var lang=langURL||langRuta||langGuardado||langNav||'es';" in html, (
        "cambió la prioridad del idioma en la landing; tiene que ser "
        "URL > ruta (/en//pt/) > guardado > navegador > castellano")


def test_la_landing_le_pasa_el_idioma_al_demo():
    """Son dos páginas distintas: si el link no lleva el idioma, elegir inglés
    en la landing y entrar al demo lo abre igual en castellano."""
    html = open(LANDING, encoding="utf-8").read()
    assert "'/demo/?lang=' + lang" in html
