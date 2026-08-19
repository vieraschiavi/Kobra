# © 2026 Martín Viera. Todos los derechos reservados.

"""AutoML: que entrene, y sobre todo que el número que reporta sea honesto.

Probar cinco algoritmos y quedarse con el mejor son veinte líneas y no
justifican tests. Lo que sí los justifica es la parte que decide si el producto
sirve o miente: **de dónde sale el número que se le muestra al cliente**.

El error habitual —elegir el modelo por su métrica en un conjunto y después
reportar esa misma métrica— produce siempre un número optimista, y el cliente
descubre la diferencia en producción. Los tests de la segunda mitad existen
para que ese atajo no se cuele en una refactorización futura.

Todos los datasets son sintéticos y se arman en el test, con semilla fija.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import automl as ka  # noqa: E402


def _dataset(n=400, semilla=0, señal=True):
    """Cartera sintética donde `pago` depende de verdad de las columnas."""
    r = np.random.default_rng(semilla)
    dias = r.integers(0, 300, n)
    score = r.integers(300, 950, n)
    monto = r.gamma(2.0, 60000, n)
    # Probabilidad de pago con señal real pero no perfecta.
    if señal:
        z = 2.2 - 0.011 * dias + 0.004 * (score - 600) - 0.0000012 * monto
    else:
        z = np.zeros(n)
    p = 1 / (1 + np.exp(-z))
    return pd.DataFrame({
        "dias_mora": dias,
        "score_buro": score,
        "monto_deuda": monto.round(2),
        "segmento": r.choice(["Pyme", "Individuo", "Corp"], n),
        "pago": r.binomial(1, p),
    })


# ---------------------------------------------------------------------------
# Que entrene
# ---------------------------------------------------------------------------
def test_entrena_y_elige_un_modelo():
    r = ka.entrenar(_dataset(), "pago")
    assert r["modelo_elegido"] in [c["modelo"] for c in r["candidatos"]]
    assert 0.0 <= r["holdout"]["auc"] <= 1.0
    assert len(r["candidatos"]) >= 2, "no se compararon algoritmos distintos"


def test_aprende_la_senal_que_hay_en_los_datos():
    """Con una relación real entre columnas y resultado, el AUC tiene que
    despegarse claramente del azar. Si no, el módulo no sirve."""
    r = ka.entrenar(_dataset(n=800, semilla=1), "pago")
    assert r["holdout"]["auc"] > 0.65, r["holdout"]


def test_sin_senal_no_inventa_una():
    """Con datos sin relación, el AUC tiene que quedar cerca de 0.5. Un AutoML
    que 'encuentra' patrones en ruido es el que hace tomar decisiones malas."""
    r = ka.entrenar(_dataset(n=600, semilla=2, señal=False), "pago")
    assert r["holdout"]["auc"] < 0.68, \
        f"encontró señal donde no hay: AUC {r['holdout']['auc']}"


def test_maneja_columnas_de_texto():
    """Una cartera real trae categorías, no solo números."""
    r = ka.entrenar(_dataset(), "pago")
    assert "segmento" in r["columnas_usadas"]


# ---------------------------------------------------------------------------
# Que el número sea honesto
# ---------------------------------------------------------------------------
def test_hay_tres_cortes_y_no_dos():
    """El holdout tiene que existir separado del tramo donde se elige."""
    r = ka.entrenar(_dataset(n=500), "pago")
    f = r["filas"]
    assert f["entrenamiento"] > 0 and f["seleccion"] > 0 and f["holdout"] > 0
    assert f["entrenamiento"] + f["seleccion"] + f["holdout"] == 500


def test_se_reporta_la_brecha_entre_seleccion_y_holdout():
    """Es cuánto se hubiera exagerado con el método habitual. Informarla es lo
    que separa una medición honesta de una propaganda."""
    r = ka.entrenar(_dataset(n=600, semilla=3), "pago")
    esperada = round(r["en_seleccion"]["auc"] - r["holdout"]["auc"], 4)
    assert r["brecha_seleccion_holdout"] == esperada
    assert "en_seleccion" in r and "holdout" in r


def test_el_numero_reportado_no_es_el_del_tramo_donde_se_eligio():
    """El corazón del asunto: `holdout` se mide sobre datos que no se usaron
    para entrenar NI para elegir. Si alguien 'simplificara' el módulo a dos
    cortes, los dos valores pasarían a ser el mismo y esto lo agarra."""
    r = ka.entrenar(_dataset(n=700, semilla=4), "pago")
    assert r["holdout"]["auc"] != r["en_seleccion"]["auc"], (
        "el AUC del holdout coincide exacto con el de selección: parece que se "
        "está midiendo sobre el mismo tramo donde se eligió el modelo")


def test_avisa_cuando_el_resultado_es_sospechosamente_bueno():
    """Una columna que predice casi perfecto casi nunca es un logro: suele ser
    una consecuencia del resultado colada como causa. Es la fuga clásica."""
    df = _dataset(n=400, semilla=5)
    # `fecha_de_pago` solo existe si pagó: predice el resultado perfectamente.
    df["marca_de_pago"] = df["pago"] * 1.0 + np.random.default_rng(5).normal(0, 0.01, len(df))
    r = ka.entrenar(df, "pago")
    assert r["holdout"]["auc"] >= ka.UMBRAL_SOSPECHA
    assert any("sospechosamente alto" in a for a in r["avisos"]), r["avisos"]


def test_con_fecha_el_corte_es_temporal():
    """Entrenar con el futuro para predecir el pasado infla la métrica y no se
    puede repetir en producción, donde el futuro no está disponible."""
    df = _dataset(n=400, semilla=6)
    df["fecha"] = pd.date_range("2026-01-01", periods=len(df), freq="D")
    r = ka.entrenar(df, "pago", columna_fecha="fecha")
    assert r["corte_temporal"] is True
    assert "fecha" not in r["columnas_usadas"], \
        "la fecha entró como variable predictora"


def test_sin_fecha_el_corte_es_aleatorio_pero_reproducible():
    """Semilla fija: dos corridas sobre los mismos datos dan lo mismo. Sin
    esto, el cliente ve un número distinto cada vez que aprieta el botón."""
    df = _dataset(n=400, semilla=7)
    a = ka.entrenar(df, "pago")
    b = ka.entrenar(df, "pago")
    assert a["holdout"] == b["holdout"]
    assert a["modelo_elegido"] == b["modelo_elegido"]


def test_los_identificadores_se_descartan():
    """Un número de contrato tiene un valor distinto por fila: no aporta señal
    y hace explotar el one-hot."""
    df = _dataset(n=300, semilla=8)
    df["nro_contrato"] = [f"C-{i}" for i in range(len(df))]
    r = ka.entrenar(df, "pago")
    assert "nro_contrato" in r["columnas_descartadas"]
    assert "nro_contrato" not in r["columnas_usadas"]
    assert any("identificadores" in a for a in r["avisos"])


# ---------------------------------------------------------------------------
# Datos que no sirven: errores que se entienden
# ---------------------------------------------------------------------------
def test_pocas_filas_se_rechaza_con_un_motivo():
    with pytest.raises(ka.DatosInsuficientes) as e:
        ka.entrenar(_dataset(n=20), "pago")
    assert "filas" in str(e.value)


def test_una_columna_objetivo_que_no_existe():
    with pytest.raises(ka.DatosInsuficientes) as e:
        ka.entrenar(_dataset(), "no_existe")
    assert "no_existe" in str(e.value)


def test_un_objetivo_con_un_solo_valor():
    df = _dataset()
    df["pago"] = 1
    with pytest.raises(ka.DatosInsuficientes) as e:
        ka.entrenar(df, "pago")
    assert "un solo valor" in str(e.value)


def test_un_objetivo_con_muchas_categorias_se_explica():
    """Hoy solo se predicen columnas de dos valores. El mensaje tiene que
    decirlo, no fallar con un error de sklearn."""
    df = _dataset()
    df["pago"] = np.random.default_rng(9).integers(0, 7, len(df))
    with pytest.raises(ka.DatosInsuficientes) as e:
        ka.entrenar(df, "pago")
    assert "dos valores" in str(e.value)


def test_una_clase_muy_rara_genera_aviso():
    """Con 2% de positivos, un modelo que dice siempre 'no' acierta el 98%. El
    cliente tiene que saberlo antes de festejar el número."""
    df = _dataset(n=600, semilla=10)
    df["pago"] = 0
    df.loc[df.index[:12], "pago"] = 1
    try:
        r = ka.entrenar(df, "pago")
        assert any("menos frecuente" in a for a in r["avisos"]), r["avisos"]
    except ka.DatosInsuficientes as e:
        # También es aceptable: con tan pocos positivos puede no haber ninguno
        # en algún tramo, y decirlo es mejor que entrenar sobre nada.
        assert "clase" in str(e.value)


def test_un_objetivo_de_texto_funciona():
    """Un cliente sube 'sí'/'no', no 1/0."""
    df = _dataset(n=400, semilla=11)
    df["pago"] = df["pago"].map({1: "pagó", 0: "no pagó"})
    r = ka.entrenar(df, "pago")
    assert r["clase_positiva"] in ("pagó", "no pagó")
    assert 0.0 <= r["holdout"]["auc"] <= 1.0


# ---------------------------------------------------------------------------
# Explicabilidad
# ---------------------------------------------------------------------------
def test_se_puede_explicar_que_columnas_pesaron():
    """En cobranzas hay que poder justificar por qué se prioriza a alguien. Un
    modelo que nadie puede explicar no se usa para decidir sobre personas."""
    r = ka.entrenar(_dataset(n=600, semilla=12), "pago")
    imp = ka.importancias(r)
    assert imp, "no se pudo explicar el modelo elegido"
    assert all(0 <= x["peso"] <= 1 for x in imp)
    assert any("dias_mora" in x["columna"] or "score" in x["columna"] for x in imp)


def test_el_informe_no_lleva_el_objeto_del_modelo():
    """Lo que viaja al frontend tiene que ser serializable a JSON."""
    import json
    r = ka.entrenar(_dataset(n=300, semilla=13), "pago")
    inf = ka.informe(r)
    assert "pipeline" not in inf
    json.dumps(inf)          # no debe lanzar
