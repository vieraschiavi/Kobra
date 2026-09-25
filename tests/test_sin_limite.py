# © 2026 Martín Viera. Todos los derechos reservados.
"""Sin tope de filas por defecto en la carga de datos.

Pedido del dueño: «debe ser sin límite de tamaño cada módulo». Antes cada
lectura traía 50.000 filas (perfilado), el AutoML usaba las primeras 200.000
(`head`, que sesga por el orden del archivo) y la consulta en lenguaje
natural cortaba en 500 — y en los tres casos el resto quedaba afuera sin que
nadie lo viera. Todos los datos son sintéticos.
"""
from __future__ import annotations

import io
import sqlite3

import numpy as np
import pandas as pd
import pytest

from kobra import automl as kautoml
from kobra import fuentes_datos as fd

N = 120_000     # más que el tope viejo de perfilado (50.000)


class _Subido(io.BytesIO):
    """Lo mismo que entrega `st.file_uploader`: bytes con un `.name`."""

    def __init__(self, datos: bytes, nombre: str):
        super().__init__(datos)
        self.name = nombre


@pytest.fixture(scope="module")
def csv_grande(tmp_path_factory):
    r = np.random.default_rng(7)
    df = pd.DataFrame({"id": np.arange(N), "deuda": r.gamma(2, 5000, N).round(2),
                       "tramo": r.choice(["0-30", "31-90", "90+"], N)})
    ruta = tmp_path_factory.mktemp("sin_limite") / "cartera.csv"
    df.to_csv(ruta, sep=";", index=False)
    return ruta


@pytest.fixture(scope="module")
def sqlite_grande(tmp_path_factory):
    ruta = tmp_path_factory.mktemp("sin_limite_db") / "base.db"
    cx = sqlite3.connect(ruta)
    cx.execute("CREATE TABLE pagos (id INTEGER, monto REAL)")
    cx.executemany("INSERT INTO pagos VALUES (?, ?)",
                   ((i, i * 1.5) for i in range(N)))
    cx.commit()
    cx.close()
    return ruta


def test_el_default_es_sin_tope():
    assert fd.LIMITE_FILAS is None
    assert kautoml.MAX_FILAS is None


def test_csv_de_120000_filas_se_lee_entero_por_defecto(csv_grande):
    df = next(iter(fd.cargar(str(csv_grande)).values()))
    assert len(df) == N
    assert list(df.columns) == ["id", "deuda", "tramo"]      # separador «;» detectado
    subido = _Subido(csv_grande.read_bytes(), "cartera.csv")
    assert len(fd.leer_subida(subido)) == N


def test_sqlite_de_120000_filas_se_lee_entero_por_defecto(sqlite_grande):
    assert len(fd.cargar(str(sqlite_grande))["pagos"]) == N
    # Vía URL (el camino de «Base de datos»), con tabla y con consulta.
    url = f"sqlite:///{sqlite_grande}"
    assert len(fd.leer_base(url, tabla="pagos")["pagos"]) == N
    assert len(fd.leer_base(url, query="SELECT id, monto FROM pagos")["consulta"]) == N


def test_tope_explicito_recorta_y_avisa_con_el_total_real(csv_grande, sqlite_grande):
    subido = _Subido(csv_grande.read_bytes(), "cartera.csv")
    df = fd.leer_subida(subido, limite=50_000)
    assert len(df) == 50_000
    total = fd.contar_filas(subido)
    assert total == N
    aviso = fd.aviso_recorte(len(df), 50_000, total)
    assert f"{50_000:,}" in aviso and f"{N:,}" in aviso and f"{N - 50_000:,}" in aviso
    # Contar también funciona sobre una ruta.
    assert fd.contar_filas(str(csv_grande)) == N
    # Sin tope, o si el tope no llegó a recortar, no hay aviso.
    assert fd.aviso_recorte(N, None, None) == ""
    assert fd.aviso_recorte(10, 50_000, 10) == ""
    # Total desconocido (Excel): se dice «al menos», nunca se calla.
    assert "al menos" in fd.aviso_recorte(50_000, 50_000, None)
    # SQL con tope explícito: se respeta.
    url = f"sqlite:///{sqlite_grande}"
    assert len(fd.leer_base(url, tabla="pagos", limite=1_000)["pagos"]) == 1_000


def test_consulta_nl_a_sql_no_corta_en_500(sqlite_grande):
    from kobra import consulta_bd as kcbd
    engine = kcbd.conectar(f"sqlite:///{sqlite_grande}")
    cols, filas, sql = kcbd.ejecutar_sql("SELECT id, monto FROM pagos", engine)
    assert len(filas) == N
    assert "limit" not in sql.lower()
    # El tope sigue disponible si alguien lo pide.
    _, filas, sql = kcbd.ejecutar_sql("SELECT id FROM pagos", engine, limite=7)
    assert len(filas) == 7 and "limit 7" in sql.lower()


def _dataset_automl(n: int) -> pd.DataFrame:
    r = np.random.default_rng(3)
    df = pd.DataFrame({"deuda": r.gamma(2, 5000, n),
                       "dias_mora": r.integers(0, 365, n).astype(float),
                       "canal": r.choice(["wa", "tel", "mail"], n)})
    lin = -0.00004 * df.deuda - 0.004 * df.dias_mora + r.normal(0, 1, n)
    df["pago"] = (lin > np.quantile(lin, 0.8)).astype(int)
    # Ordenado por la clase: un `head()` se quedaría con una sola.
    return df.sort_values("pago", kind="stable").reset_index(drop=True)


def test_automl_con_mas_de_200000_filas_mide_y_puntua_todas(monkeypatch):
    """210.000 filas (más que el tope viejo). El tope de AJUSTE se baja a
    3.000 sólo para que el test sea rápido: lo que se prueba es la mecánica
    —muestra aleatoria estratificada para ajustar, 100 % para medir y
    puntuar—, no el número."""
    monkeypatch.setattr(kautoml, "MAX_FILAS_AJUSTE", 3_000)
    monkeypatch.setattr(kautoml, "_modelos", lambda: {
        "Regresión logística": kautoml.LogisticRegression(max_iter=500)})
    df = _dataset_automl(210_000)
    r = kautoml.entrenar(df, "pago")
    f = r["filas"]
    assert f["total"] == 210_000
    assert f["tramo_entrenamiento"] + f["seleccion"] + f["holdout"] == 210_000
    assert f["entrenamiento"] <= 3_001 and r["muestreo_ajuste"]
    assert any("muestra aleatoria estratificada" in a for a in r["avisos"])
    assert not any("primeras" in a for a in r["avisos"])
    scores = kautoml.puntuar(r, df)
    assert len(scores) == 210_000 and scores.between(0, 1).all()


def test_la_muestra_de_ajuste_es_estratificada_y_no_head():
    df = _dataset_automl(50_000)          # ordenado: 40.000 ceros y después unos
    m = kautoml._muestra_estratificada(df, "pago", 5_000)
    assert abs(len(m) - 5_000) <= 1
    assert abs(m["pago"].mean() - df["pago"].mean()) < 0.002
    # Reproducible: misma semilla, misma muestra.
    assert m.index.equals(kautoml._muestra_estratificada(df, "pago", 5_000).index)
    # Si entra, no se toca.
    assert len(kautoml._muestra_estratificada(df, "pago", 60_000)) == 50_000


def test_exportar_mas_filas_que_una_hoja_de_excel_parte_en_varias():
    df = pd.DataFrame({"x": np.zeros(fd.MAX_FILAS_XLSX + 10, dtype=np.int8)})
    partes = fd.partir_para_xlsx("Cartera", df)
    assert [h for h, _ in partes] == ["Cartera", "Cartera (2)"]
    assert sum(len(t) for _, t in partes) == len(df)
    assert all(len(t) + 1 <= fd.MAX_FILAS_XLSX for _, t in partes)
    assert fd.partir_para_xlsx("Chica", df.head(3))[0][0] == "Chica"


def test_streamlit_acepta_subidas_sin_tope_practico():
    import pathlib
    import tomllib
    raiz = pathlib.Path(__file__).resolve().parents[1]
    cfg = tomllib.loads((raiz / ".streamlit" / "config.toml").read_text("utf-8"))
    assert cfg["server"]["maxUploadSize"] == 200_000
