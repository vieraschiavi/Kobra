"""El scoring que corre en el navegador tiene que dar lo MISMO que scikit-learn.

La demo pública deja que un visitante suba su CSV y vea el scoring sin mandar el
archivo a ningún lado: se calcula en su navegador, con `dashboard_estatico/
scoring.js`. Eso solo sirve si los números son los de verdad. Acá se cierra la
cadena de punta a punta:

    scikit-learn  ↔  kobra.exportar_modelo_web.scorear (Python)  ↔  scoring.js (JS)

Si algún día `kobra.train` elige un modelo de árboles, el exportador se planta y
estos tests lo dicen en vez de dejar la demo mostrando números de otro modelo.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile

import pytest

from kobra import exportar_modelo_web as emw
from kobra import rutas as krutas

RAIZ = krutas.ROOT_REPO
DEMO = os.path.join(RAIZ, "dashboard_estatico")
SCORING_JS = os.path.join(DEMO, "scoring.js")
MODELO_JSON = os.path.join(DEMO, "modelo_web.json")
EJEMPLO_CSV = os.path.join(DEMO, "ejemplo_500_cuentas.csv")
# La cartera cruda, no `outputs/kobra_scored.csv`: el scoreado se guarda con las
# columnas de salida y le faltan ocho de las que come el modelo.
CARTERA = os.path.join(krutas.DIR_DATOS, "data", "kobra_cartera.csv")

NODE = shutil.which("node")
sin_node = pytest.mark.skipif(NODE is None, reason="node no está instalado")
sin_modelo = pytest.mark.skipif(
    not os.path.exists(emw.MODELO),
    reason="hace falta el modelo entrenado (python3 -m kobra.pipeline)")

# Tolerancia: es error de punto flotante, no "parecido". Al escribirlo se midió
# 1,2e-13 contra scikit-learn y 3,3e-15 entre Python y JS. Un umbral flojo acá
# dejaría pasar justo el bug que motivó el test —interpolar la isotónica sobre
# la sigmoide en vez de sobre z daba 0,525 de diferencia y "parecía bien"—.
TOLERANCIA = 1e-9


@pytest.fixture(scope="module")
def bundle():
    """Exporta a un temporal: el test no pisa el JSON versionado."""
    if not os.path.exists(emw.MODELO):
        pytest.skip("hace falta el modelo entrenado")
    with tempfile.TemporaryDirectory() as d:
        return emw.exportar(emw.MODELO, os.path.join(d, "modelo_web.json"))


@pytest.fixture(scope="module")
def muestra():
    """Filas reales de la cartera scoreada, tal como llegan de un CSV."""
    import pandas as pd
    if not os.path.exists(CARTERA):
        pytest.skip("hace falta data/kobra_cartera.csv (python3 -m kobra.pipeline)")
    return pd.read_csv(CARTERA).head(1500)


# --- El exportador no exporta cualquier cosa ---------------------------------

@sin_modelo
def test_exporta_un_pliegue_por_calibrador(bundle):
    """Cada pliegue lleva SU preprocesador.

    `CalibratedClassifierCV(cv=3)` reajusta el pipeline entero por pliegue, así
    que las medias y desvíos del escalador difieren entre los tres. Guardar uno
    solo y reusarlo da números parecidos y equivocados.
    """
    assert len(bundle["pliegues"]) >= 2
    medias = [tuple(p["pre"]["escala"]["media"]) for p in bundle["pliegues"]]
    assert len(set(medias)) == len(medias), (
        "los pliegues comparten escalador: se exportó uno solo para todos")


@sin_modelo
def test_el_calibrador_mapea_z_y_no_una_probabilidad(bundle):
    """Los nodos de la isotónica están en el dominio de `decision_function`.

    Es el detalle que rompe la reimplementación si se ignora: si uno supone que
    la isotónica recibe una probabilidad, mete un 1/(1+e^-z) antes de
    interpolar. Los nodos, que se salen del [0,1], prueban que no.
    """
    x = bundle["pliegues"][0]["calibrador"]["x"]
    assert min(x) < -1.0 or max(x) > 1.0, (
        f"los nodos caen dentro de [0,1] ({min(x):.3f}..{max(x):.3f}): "
        "si esto cambia, revisar si ahora la isotónica calibra la sigmoide")


@sin_modelo
def test_se_planta_si_el_modelo_no_es_lineal(monkeypatch, bundle):
    """Un modelo de árboles no se puede reimplementar en JS: hay que fallar.

    Es el caso que importa: si `kobra.train` un día elige un gradient boosting,
    exportar "los coeficientes" en silencio dejaría la demo mostrando números de
    un modelo que no existe. Preferible que reviente acá.
    """
    import joblib
    cal = joblib.load(emw.MODELO)

    class RandomForestClassifier:  # el nombre es lo que mira el chequeo
        pass

    # Dos detalles que hicieron fallar los primeros intentos: `exportar` recarga
    # del disco (hay que interceptar la carga, no mutar una copia en memoria) y
    # `named_steps` de scikit-learn es un Bunch que se reconstruye en cada
    # acceso — asignarle algo muta un objeto descartable. El estado vive en
    # `steps`.
    pipe = cal.calibrated_classifiers_[0].estimator
    pipe.steps = [(n, RandomForestClassifier() if n == "clf" else t)
                  for n, t in pipe.steps]
    monkeypatch.setattr(joblib, "load", lambda *a, **k: cal)
    with pytest.raises(emw.ModeloNoExportable, match="RandomForestClassifier"):
        with tempfile.TemporaryDirectory() as d:
            emw.exportar(emw.MODELO, os.path.join(d, "x.json"))


# --- sklearn ↔ Python --------------------------------------------------------

@sin_modelo
def test_python_reproduce_predict_proba(bundle, muestra):
    """La aritmética reimplementada da lo mismo que `predict_proba`."""
    import joblib
    cal = joblib.load(emw.MODELO)
    columnas = bundle["pre"]["numericas"] + bundle["pre"]["categoricas"]
    X = muestra[columnas]
    esperado = cal.predict_proba(X)[:, 1]
    obtenido = emw.scorear(bundle, X.to_dict("records"))
    peor = max(abs(a - b) for a, b in zip(esperado, obtenido))
    assert peor < TOLERANCIA, f"diferencia máxima contra scikit-learn: {peor}"


# --- Python ↔ JavaScript -----------------------------------------------------

def _node(script: str) -> dict:
    """Corre un script Node que imprime JSON en la última línea."""
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                     encoding="utf-8") as f:
        f.write(script)
        ruta = f.name
    try:
        r = subprocess.run([NODE, ruta], capture_output=True, text=True, timeout=180)
        assert r.returncode == 0, f"node falló:\n{r.stderr[:2000]}"
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(ruta)


@sin_node
@sin_modelo
def test_javascript_reproduce_a_python(bundle, muestra, tmp_path):
    """`scoring.js` da lo mismo que la implementación de Python.

    Se corre el archivo REAL que sirve la demo, no una copia del algoritmo: si
    alguien edita `scoring.js` y rompe el cálculo, este test lo agarra.
    """
    columnas = bundle["pre"]["numericas"] + bundle["pre"]["categoricas"]
    filas = muestra[columnas].astype(str).to_dict("records")
    esperado = emw.scorear(bundle, muestra[columnas].to_dict("records"))

    (tmp_path / "bundle.json").write_text(json.dumps(bundle), encoding="utf-8")
    (tmp_path / "filas.json").write_text(json.dumps(filas), encoding="utf-8")
    salida = _node(f"""
      import fs from 'node:fs';
      const g = {{}};
      new Function('window', fs.readFileSync({json.dumps(SCORING_JS)}, 'utf8'))(g);
      const b = JSON.parse(fs.readFileSync({json.dumps(str(tmp_path / 'bundle.json'))}, 'utf8'));
      const f = JSON.parse(fs.readFileSync({json.dumps(str(tmp_path / 'filas.json'))}, 'utf8'));
      console.log(JSON.stringify({{p: g.KobraScoring.scorear(b, f)}}));
    """)
    peor = max(abs(a - b) for a, b in zip(esperado, salida["p"]))
    assert peor < TOLERANCIA, f"diferencia máxima Python↔JS: {peor}"


# --- El CSV que sube el visitante -------------------------------------------

@sin_node
def test_el_parser_de_csv_aguanta_lo_que_sale_de_excel():
    """Punto y coma, comillas, comas adentro de comillas, CRLF y BOM.

    Un export de Excel en configuración regional española usa `;`. Sin
    detectarlo, el archivo entra como una sola columna y la demo contesta "te
    faltan todas las columnas", que no le dice nada a quien lo subió.
    """
    casos = {
        "coma": 'a,b\n1,2\n',
        "puntoycoma": 'a;b\n1;2\n',
        "tab": 'a\tb\n1\t2\n',
        "crlf": 'a,b\r\n1,2\r\n',
        "bom": '﻿a,b\n1,2\n',
        "comillas": 'a,b\n"uno, dos",2\n',
        "comilla_doble": 'a,b\n"di ""hola""",2\n',
        "final_sin_salto": 'a,b\n1,2',
        "linea_vacia": 'a,b\n1,2\n\n',
    }
    r = _node(f"""
      import fs from 'node:fs';
      const g = {{}};
      new Function('window', fs.readFileSync({json.dumps(SCORING_JS)}, 'utf8'))(g);
      const casos = {json.dumps(casos, ensure_ascii=False)};
      const out = {{}};
      for (const k in casos) out[k] = g.KobraScoring.parsearCSV(casos[k]);
      console.log(JSON.stringify(out));
    """)
    for nombre, r_ in r.items():
        assert r_["columnas"] == ["a", "b"], f"{nombre}: encabezado {r_['columnas']}"
        assert len(r_["filas"]) == 1, f"{nombre}: {len(r_['filas'])} filas"
    assert r["comillas"]["filas"][0]["a"] == "uno, dos"
    assert r["comilla_doble"]["filas"][0]["a"] == 'di "hola"'


@sin_node
@sin_modelo
def test_le_dice_al_visitante_que_columna_le_falta(bundle):
    """Y acepta cualquier capitalización, que es el error más común."""
    pedidas = bundle["pre"]["numericas"] + bundle["pre"]["categoricas"]
    mayus = [c.upper() for c in pedidas]
    r = _node(f"""
      import fs from 'node:fs';
      const g = {{}};
      new Function('window', fs.readFileSync({json.dumps(SCORING_JS)}, 'utf8'))(g);
      const b = {json.dumps(bundle)};
      console.log(JSON.stringify({{
        completo: g.KobraScoring.revisarColumnas(b, {json.dumps(mayus)}),
        incompleto: g.KobraScoring.revisarColumnas(b, {json.dumps(mayus[:-2])})
      }}));
    """)
    assert r["completo"]["faltan"] == [], (
        "no reconoce las columnas en mayúsculas: obligaría a renombrar el CSV")
    assert sorted(r["incompleto"]["faltan"]) == sorted(pedidas[-2:])


# --- Lo que se publica en la demo -------------------------------------------

@sin_modelo
def test_el_json_publicado_es_el_del_modelo_actual(bundle):
    """`dashboard_estatico/modelo_web.json` no puede quedar viejo.

    Si alguien reentrena y no reexporta, la demo scorea con coeficientes de otro
    modelo y nadie se entera hasta que un cliente compara.
    """
    assert os.path.exists(MODELO_JSON), (
        "falta dashboard_estatico/modelo_web.json: "
        "correr python3 -m kobra.exportar_modelo_web")
    publicado = json.load(open(MODELO_JSON, encoding="utf-8"))
    assert publicado["pliegues"] == bundle["pliegues"], (
        "el modelo_web.json publicado no coincide con el .joblib entrenado: "
        "correr python3 -m kobra.exportar_modelo_web")


@sin_node
def test_el_modelo_tambien_se_publica_como_js_para_abrir_offline():
    """El paquete de demo se abre con doble clic, o sea `file://`.

    Sobre `file://` el navegador bloquea `fetch()` de un archivo local, así que
    un `modelo_web.json` solo dejaría la demo offline sin scoring. Va también
    como `<script src>`, igual que `kobra_data.js`.
    """
    js = os.path.join(DEMO, "modelo_web.js")
    assert os.path.exists(js), (
        "falta dashboard_estatico/modelo_web.js: la demo offline no scorea")
    html = open(os.path.join(DEMO, "index.html"), encoding="utf-8").read()
    cabeza = html.split("<body", 1)[0]
    assert 'src="modelo_web.js"' in cabeza, (
        "index.html no carga modelo_web.js: sobre file:// el fetch falla")

    r = _node(f"""
      import fs from 'node:fs';
      const g = {{}};
      new Function('window', fs.readFileSync({json.dumps(js)}, 'utf8'))(g);
      console.log(JSON.stringify({{p: g.KOBRA_MODELO.pliegues}}));
    """)
    publicado = json.load(open(MODELO_JSON, encoding="utf-8"))
    assert r["p"] == publicado["pliegues"], (
        "modelo_web.js y modelo_web.json traen modelos distintos: "
        "correr python3 -m kobra.exportar_modelo_web")


def test_el_csv_de_ejemplo_trae_las_columnas_que_pide_el_modelo():
    """El botón "bajar CSV de ejemplo" tiene que producir un archivo que ande.

    Es la primera cosa que prueba alguien que no tiene su cartera a mano.
    """
    assert os.path.exists(EJEMPLO_CSV), "falta el CSV de ejemplo de la demo"
    with open(EJEMPLO_CSV, encoding="utf-8") as f:
        cabecera = f.readline().strip().split(",")
        filas = sum(1 for _ in f)
    publicado = json.load(open(MODELO_JSON, encoding="utf-8"))
    pedidas = publicado["pre"]["numericas"] + publicado["pre"]["categoricas"]
    faltan = [c for c in pedidas if c not in cabecera]
    assert not faltan, f"al CSV de ejemplo le faltan columnas: {faltan}"
    assert filas == 500, f"el ejemplo dice 500 cuentas y trae {filas}"


def test_el_ejemplo_no_lleva_datos_personales():
    """Datos sintéticos, sin PII: es la línea que no se cruza (Ley 18.331)."""
    with open(EJEMPLO_CSV, encoding="utf-8") as f:
        cabecera = f.readline().lower()
    prohibidas = ("nombre", "apellido", "cedula", "documento", "email",
                  "correo", "telefono", "celular", "direccion", "ci_")
    encontradas = [p for p in prohibidas if p in cabecera]
    assert not encontradas, f"el CSV de ejemplo expone campos de PII: {encontradas}"


# --- La demo se ve sin registrarse ------------------------------------------

def test_la_demo_no_tiene_una_pantalla_que_tape_todo():
    """Sin demo verificable el scoring es una promesa.

    Antes la página se tapaba con un overlay `position:fixed; inset:0` hasta
    registrarse. Este test existe para que no vuelva por descuido.
    """
    html = open(os.path.join(DEMO, "index.html"), encoding="utf-8").read()
    assert "position:fixed;inset:0;z-index:9999" not in html.replace(" ", ""), (
        "volvió el overlay que tapa la demo hasta registrarse")
    assert "documentElement.style.overflow='hidden'" not in html, (
        "algo vuelve a bloquear el scroll de la página")


def test_el_dato_crudo_del_visitante_va_escapado():
    """El id de cuenta del CSV es texto libre: no puede entrar sin escapar.

    Un CSV con `<img src=x onerror=...>` en una celda lo ejecutaría el navegador
    de quien lo sube. Se comprueba sobre el bloque real que arma la tabla.
    """
    html = open(os.path.join(DEMO, "index.html"), encoding="utf-8").read()
    ini = html.index("function pintar(csv, filas, probs")
    bloque = html[ini:html.index("})();", ini)]

    # Se comprueba la propiedad, no una escritura concreta: cada línea que
    # arma HTML y menciona un dato del visitante tiene que pasar por esc().
    # Escrito así porque la versión anterior exigía literalmente `esc(nombre)`
    # y se rompió sola al pasar el resumen por el traductor —a pesar de que el
    # escape seguía estando—. Un test que se rompe con un refactor inocuo
    # entrena a ignorarlo.
    riesgosas = []
    for linea in bloque.splitlines():
        if "html" not in linea and "innerHTML" not in linea:
            continue
        if not re.search(r"\b(id|nombre)\b", linea):
            continue
        # El dato tiene que estar dentro de un esc(...) en esa misma línea.
        if not re.search(r"esc\([^)]*\b(id|nombre)\b", linea):
            riesgosas.append(linea.strip()[:110])
    assert not riesgosas, (
        "hay datos del archivo del visitante entrando a innerHTML sin esc(): "
        + " | ".join(riesgosas))
    assert "esc(" in bloque and bloque.count("esc(") >= 5, (
        "el bloque que pinta la tabla dejó de escapar")
