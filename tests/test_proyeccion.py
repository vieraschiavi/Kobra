# © 2026 Martín Viera. Todos los derechos reservados.

"""La proyección de cobranza: que el número tenga derecho a mostrarse.

Un módulo de proyección es fácil de probar mal. Se le pasa una serie, devuelve
catorce números, ninguno explota y todo parece andar. Lo que hay que probar no
es que devuelva números: es que **diga que no** cuando la serie no tiene señal,
porque una línea proyectada sobre ruido se lee como un compromiso y termina en
la meta del mes de alguien.

Por eso la mitad de estos tests son controles negativos.
"""
import ast
import os
import re
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import proyeccion as pr  # noqa: E402

# Las series de prueba se generan con semilla fija: un test de backtest que
# cambia de veredicto según la corrida no prueba nada.
SEMILLA = 42
N = 331   # el largo de la serie real de la demo


def _fechas(n=N):
    return pd.date_range("2025-08-01", periods=n, freq="D")


def _con_estructura(n=N, ruido=0.12):
    """Una semana con forma (los sábados se cobra poco), tendencia y pico de
    fin de mes: la serie que un modelo SÍ debería poder aprovechar."""
    rs = np.random.RandomState(SEMILLA)
    idx = _fechas(n)
    dow = np.array([1.35, 1.20, 1.15, 1.05, 0.95, 0.45, 0.35])
    base = 800_000 * (1 + 0.0012 * np.arange(n))
    return pd.Series(base * dow[idx.dayofweek] * (1 + 0.25 * (idx.day > 25))
                     * rs.lognormal(0, ruido, n), index=idx)


def _sin_estructura(n=N):
    """Ruido puro alrededor de un promedio: no hay nada que aprender."""
    rs = np.random.RandomState(SEMILLA)
    return pd.Series(800_000 * rs.lognormal(0, 0.9, n), index=_fechas(n))


# ---------------------------------------------------------------------------
# La serie
# ---------------------------------------------------------------------------

def test_los_dias_sin_cobranza_valen_cero_y_no_se_saltean():
    """Saltear los días vacíos desalinea la semana: el modelo pasa a creer que
    «el próximo punto» es el próximo día CON datos, que puede ser tres días
    después, y la forma de la semana desaparece."""
    s = pr.serie_diaria(pd.Series(["2026-01-01", "2026-01-05", "2026-01-05"]),
                        pd.Series([100.0, 30.0, 20.0]))
    assert len(s) == 5                       # del 1 al 5, sin huecos
    assert s.iloc[0] == 100 and s.iloc[-1] == 50   # el 5 suma las dos filas
    assert list(s[s == 0].index.day) == [2, 3, 4]


def test_la_serie_tolera_fechas_con_y_sin_hora_en_la_misma_columna():
    """La cartera real trae las dos formas en la misma columna, y con el
    formato inferido de la primera fila el resto se convierte en NaT: se
    perderían días enteros de cobranza sin ningún error a la vista."""
    s = pr.serie_diaria(pd.Series(["2026-01-01", "2026-01-02 23:50"]),
                        pd.Series([10.0, 20.0]))
    assert len(s) == 2 and s.sum() == 30


def test_una_fecha_ilegible_no_tira_abajo_la_serie():
    s = pr.serie_diaria(pd.Series(["2026-01-01", "vaya uno a saber"]),
                        pd.Series([10.0, 20.0]))
    assert s.sum() == 10


# ---------------------------------------------------------------------------
# Sin mirar el futuro
# ---------------------------------------------------------------------------

def test_ningun_modelo_ve_un_solo_dato_posterior_al_corte():
    """El leakage no rompe nada: mejora las métricas. Por eso se prueba
    mirando QUÉ recibió el modelo, no si el resultado parece razonable."""
    serie = np.arange(200, dtype="float64")
    vistos = []

    def espia(historia, n):
        vistos.append(historia.copy())
        return np.repeat(historia[-1], n)

    origenes = pr._origenes(len(serie), 14, 4)
    pr.evaluar(serie, espia, 14, origenes)
    assert vistos, "el espía no llegó a correr"
    for historia, corte in zip(vistos, origenes):
        assert len(historia) == corte
        assert historia[-1] == serie[corte - 1]      # termina justo en el corte
        assert historia.max() < serie[corte]         # y no hay nada de después


def test_los_origenes_no_se_pisan_entre_si():
    """Orígenes solapados comparten los mismos días reales: multiplican la
    apariencia de evidencia sin agregar un solo dato nuevo."""
    origenes = pr._origenes(400, 14, 6)
    assert len(origenes) == 6
    assert all(b - a >= 14 for a, b in zip(origenes, origenes[1:]))


def test_la_ventana_de_seleccion_termina_antes_de_que_empiece_el_holdout():
    """Si se tocan, el número «ciego» deja de serlo."""
    horizonte, largo = 14, 400
    reservado = horizonte * pr.VENTANAS_HOLDOUT
    sel = pr._origenes(largo, horizonte, pr.VENTANAS_SELECCION, reservar=reservado)
    hold = pr._origenes(largo, horizonte, pr.VENTANAS_HOLDOUT)
    assert max(sel) + horizonte <= min(hold)


# ---------------------------------------------------------------------------
# El veredicto: lo que de verdad importa
# ---------------------------------------------------------------------------

def test_sobre_ruido_puro_no_se_muestra_una_proyeccion():
    """El control negativo. Ningún modelo puede ganarle al promedio acá, y el
    módulo tiene que decirlo en vez de dibujar una curva."""
    r = pr.comparar(_sin_estructura())
    assert r["suficiente"]
    assert not r["sirve"]
    assert r["ganador"] in pr.TRIVIALES
    assert r["modelo_a_usar"] in pr.TRIVIALES
    assert "promedio" in r["veredicto"]


def test_sobre_una_serie_con_forma_de_semana_si_se_proyecta():
    """El control positivo. Sin esto, un módulo que dijera «no hay señal»
    siempre pasaría todos los tests negativos y no serviría para nada."""
    r = pr.comparar(_con_estructura())
    assert r["sirve"], r["veredicto"]
    assert r["ganador"] not in pr.TRIVIALES
    assert r["holdout"][r["ganador"]]["mase"] < 1


def test_una_mejora_chica_no_alcanza_para_creerle():
    """Con pocas ventanas, un 5% no se distingue de la suerte. El margen es lo
    que evita vender ruido como señal."""
    serie = _sin_estructura()
    y = np.asarray(serie, dtype="float64")

    def apenas_mejor(historia, n):
        # El promedio corrido apenas hacia el valor real: imita a un modelo
        # que mejora un poquito, sin llegar al margen exigido.
        return np.repeat(float(np.mean(historia)) * 1.01, n)

    r = pr.comparar(serie, extra={"apenas_mejor": apenas_mejor})
    assert not r["sirve"]
    assert len(y) == pr.VENTANAS_SELECCION * 0 + len(serie)   # serie intacta


def test_un_modelo_que_de_verdad_predice_se_acepta():
    """La contracara del test anterior: si la mejora es grande y sobrevive al
    holdout, el módulo tiene que decir que sí."""
    serie = _con_estructura(ruido=0.05)
    y = np.asarray(serie, dtype="float64")

    def casi_oraculo(historia, n):
        # Ve el futuro con un 3% de error. No es honesto como modelo: es un
        # control de que el gate NO está trabado en "no".
        i = len(historia)
        return y[i:i + n] * 1.03

    r = pr.comparar(serie, extra={"casi_oraculo": casi_oraculo})
    assert r["sirve"]
    assert r["ganador"] == "casi_oraculo"
    assert r["mejora_vs_trivial"] > pr.MARGEN_MINIMO


def test_la_mejora_se_mide_contra_el_mejor_trivial_y_no_contra_uno_elegido():
    """En la cartera de demostración el ingenuo estacional rinde MASE 1,24 —es
    malo ahí— y contra esa vara casi cualquier cosa «mejora un 23%». Medir
    contra el mejor de los triviales es lo que impide ese titular."""
    r = pr.comparar(_sin_estructura())
    triviales = {k: v["mase"] for k, v in r["holdout"].items()
                 if k in pr.TRIVIALES}
    assert r["mejor_trivial"] == min(triviales, key=triviales.get)


def test_con_poca_historia_se_dice_que_no_alcanza_en_vez_de_inventar():
    r = pr.comparar(_sin_estructura(n=60))
    assert not r["suficiente"]
    assert "historia" in r["motivo"]
    assert "ganador" not in r


def test_la_brecha_entre_seleccion_y_holdout_se_informa():
    """Es el número que delata haber elegido ruido, y el que casi nunca se
    publica."""
    r = pr.comparar(_con_estructura())
    assert r["brecha"] is not None
    assert r["holdout"][r["ganador"]]["mase"] - \
        r["seleccion"][r["ganador"]]["mase"] == pytest.approx(r["brecha"])


# ---------------------------------------------------------------------------
# La proyección que se muestra
# ---------------------------------------------------------------------------

def test_la_proyeccion_nunca_es_negativa():
    """Un modelo con tendencia a la baja proyecta cobranza negativa, y eso no
    es una predicción: es un error de tipeo con forma de gráfico."""
    serie = pd.Series(np.linspace(1_000_000, 1_000, 100), index=_fechas(100))
    p = pr.proyectar(serie, horizonte=30, modelo="deriva")
    assert (p["proyeccion"] >= 0).all()


def test_la_proyeccion_arranca_al_dia_siguiente_del_ultimo_dato():
    serie = _con_estructura(n=100)
    p = pr.proyectar(serie, horizonte=14)
    assert len(p) == 14
    assert p["fecha"].iloc[0] == serie.index[-1] + pd.Timedelta(days=1)
    assert (p["fecha"].diff().dropna() == pd.Timedelta(days=1)).all()


def test_sin_modelo_explicito_se_usa_la_referencia_y_no_uno_a_dedo():
    p = pr.proyectar(_con_estructura(n=100), horizonte=7)
    assert (p["modelo"] == pr.REFERENCIA).all()


# ---------------------------------------------------------------------------
# Las métricas
# ---------------------------------------------------------------------------

def test_el_mase_se_escala_con_la_historia_y_no_con_el_tramo_evaluado():
    """Escalarlo con el tramo que se está evaluando es mirar la respuesta
    antes de contestar: el denominador saldría del futuro."""
    historia = np.arange(100, dtype="float64")
    real = np.arange(100, 114, dtype="float64")
    assert pr.mase(real, real, historia) == 0.0
    peor = pr.mase(real, real + 10, historia)
    assert peor > 0
    # Duplicar el error duplica el MASE: la escala no depende del error.
    assert pr.mase(real, real + 20, historia) == pytest.approx(peor * 2)


def test_el_smape_no_explota_con_ceros():
    ceros = np.zeros(5)
    assert pr.smape(ceros, ceros) == 0.0
    assert np.isfinite(pr.smape(ceros, np.ones(5)))


def test_todos_los_triviales_existen_como_modelo():
    """Un nombre mal escrito en TRIVIALES dejaría la vara sin uno de los
    modelos que tiene que superar, sin que nada falle."""
    assert set(pr.TRIVIALES) <= set(pr.MODELOS)
    assert pr.REFERENCIA in pr.MODELOS


# ---------------------------------------------------------------------------
# TimesFM: opcional de verdad, y con la licencia que corresponde
# ---------------------------------------------------------------------------

def _fuente_adaptador():
    with open(os.path.join(ROOT, "kobra", "proyeccion_timesfm.py"),
              encoding="utf-8") as f:
        return f.read()


def _codigo_sin_comentarios(texto):
    """El código EFECTIVO: sin comentarios y sin docstrings.

    Los dos módulos explican en prosa por qué no se usa la 3.0 y por qué el
    núcleo no importa el adaptador. Un grep crudo se encuentra esa prosa a sí
    mismo y el test pasa a medir la documentación en vez del código — que es
    exactamente al revés de lo que sirve.
    """
    sin_comentarios = "\n".join(re.sub(r"#.*$", "", ln)
                                for ln in texto.splitlines())
    arbol = ast.parse(sin_comentarios)
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)) and ast.get_docstring(nodo):
            nodo.body = nodo.body[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(arbol))


def test_el_adaptador_solo_carga_pesos_con_licencia_comercial():
    """Los pesos de la 3.0 son `timesfm-non-commercial-license-v1.0`: prohíben
    el uso en producción. MV Kobra AI se vende. Este test es la diferencia
    entre poder venderlo y no poder."""
    from kobra import proyeccion_timesfm as ptf
    assert ptf.LICENCIA_PESOS == "Apache-2.0"
    assert "2.5" in ptf.REPO_25
    codigo = _codigo_sin_comentarios(_fuente_adaptador())
    prohibido = "timesfm-" + "3.0"
    assert prohibido not in codigo, "no se pueden cargar los pesos de la 3.0"


def test_sin_pesos_en_disco_el_adaptador_no_sale_a_internet(monkeypatch):
    """El programa instalado corre sin internet —es una de las respuestas al
    área de seguridad del cliente—: bajar 925 MB en el primer arranque no es
    una opción, y menos en silencio."""
    from kobra import proyeccion_timesfm as ptf
    monkeypatch.delenv("KOBRA_TIMESFM_DIR", raising=False)
    assert ptf.disponible(permitir_descarga=False) is False
    assert ptf.predictor(permitir_descarga=False) is None


def test_el_modulo_de_proyeccion_no_importa_timesfm():
    """Si el núcleo lo importara, el programa entero dependería de PyTorch."""
    codigo = _codigo_sin_comentarios(
        open(os.path.join(ROOT, "kobra", "proyeccion.py"), encoding="utf-8").read())
    assert "import timesfm" not in codigo
    assert "proyeccion_timesfm" not in codigo


def test_el_instalador_no_engorda_con_torch():
    """`requirements.txt` es lo que viaja en el .exe. TimesFM son ~1,1 GB entre
    pesos y PyTorch, para una función que en muchas carteras no mejora nada."""
    with open(os.path.join(ROOT, "requirements.txt"), encoding="utf-8") as f:
        reqs = f.read().lower()
    assert "torch" not in reqs
    assert "timesfm" not in reqs


# ---------------------------------------------------------------------------
# La pantalla y el endpoint
# ---------------------------------------------------------------------------

def _fuente(*partes):
    with open(os.path.join(ROOT, *partes), encoding="utf-8") as f:
        return f.read()


def test_el_endpoint_devuelve_el_veredicto_y_no_solo_la_curva():
    """Una API que devuelve solo la proyección obliga a la pantalla a
    dibujarla: el «no le creas» tiene que viajar con los datos."""
    import importlib

    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    cli = TestClient(api.app)
    cli.headers.update({"Authorization":
                        f"Bearer {api._emitir_token('admin', api.EMPRESA_DEFAULT)}"})
    r = cli.get("/api/proyeccion-cobranza?dias=14")
    assert r.status_code == 200
    d = r.json()
    assert len(d["proyeccion"]) == 14
    assert d["veredicto"]["codigo"] in {"sirve", "sin_senal", "sin_margen",
                                        "sin_holdout"}
    assert "sirve" in d["veredicto"]
    # La cartera de demostración es ruido: el panel no puede decir que sí.
    assert d["veredicto"]["sirve"] is False, (
        "la demo sintética no tiene señal temporal; decir que sí sería vender "
        "ruido como predicción")


def test_el_endpoint_acota_el_horizonte_que_le_piden():
    """`?dias=100000` no puede reservar memoria ni tardar un minuto."""
    import importlib

    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    cli = TestClient(api.app)
    cli.headers.update({"Authorization":
                        f"Bearer {api._emitir_token('admin', api.EMPRESA_DEFAULT)}"})
    assert len(cli.get("/api/proyeccion-cobranza?dias=99999").json()["proyeccion"]) == 60
    assert len(cli.get("/api/proyeccion-cobranza?dias=0").json()["proyeccion"]) == 1


def test_sin_sesion_no_se_ve_la_proyeccion():
    import importlib

    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    assert TestClient(api.app).get(
        "/api/proyeccion-cobranza").status_code in (401, 403)


def test_la_pantalla_esta_enchufada_en_la_aplicacion():
    app = _fuente("webapp", "frontend", "src", "App.jsx")
    assert "pages/Proyeccion.jsx" in app
    assert "app.nav.proyeccion" in app
    assert 'path="/proyeccion"' in app


def test_la_pantalla_distingue_a_ojo_una_prediccion_de_un_promedio():
    """El texto no alcanza: la línea punteada y gris es lo que se ve primero,
    y tiene que decir lo mismo que el texto."""
    pagina = _fuente("webapp", "frontend", "src", "pages", "Proyeccion.jsx")
    assert "strokeDasharray" in pagina
    assert "titular_promedio" in pagina and "titular_sirve" in pagina


@pytest.mark.parametrize("archivo", ["es.json", "en.json", "pt-BR.json"])
def test_los_tres_idiomas_tienen_los_cuatro_veredictos(archivo):
    """Un veredicto sin traducir deja la clave cruda en pantalla justo cuando
    el panel está diciendo que no le crean al número."""
    import json
    dic = json.loads(_fuente("webapp", "frontend", "src", "i18n", archivo))
    for codigo in ("sirve", "sin_senal", "sin_margen", "sin_holdout"):
        assert dic["proyeccion"][f"veredicto_{codigo}"].strip()
    for modelo in pr.MODELOS:
        assert dic["proyeccion"][f"modelo_{modelo}"].strip()
    assert dic["proyeccion"]["modelo_timesfm_2p5"].strip()
    assert dic["app"]["nav"]["proyeccion"].strip()
