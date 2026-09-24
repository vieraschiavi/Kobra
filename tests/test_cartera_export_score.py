"""Un export de score real (65 columnas, fechas, centinelas 9999, punto
decimal) daba ProbPago 100 % para toda la cartera.

Tres causas, las tres silenciosas: `FechaScore` («31/03/2026») terminaba
de «score de buró» leído como 31.032.026; `1140273.482` se leía como
miles (deuda ×1000); y el modelo, que usa las numéricas tal cual, se
saturaba con esos valores. Los datos de acá son sintéticos con la MISMA
forma que el export, nunca el archivo del cliente.
"""
import warnings

import pandas as pd
import pytest

from kobra import cartera_manual as cm

warnings.filterwarnings("ignore")


def _export(n: int = 40) -> pd.DataFrame:
    filas = []
    for i in range(n):
        mora = [20, 60, 120, 200, 400, 900][i % 6]
        filas.append({
            "﻿FechaScore": "31/03/2026",
            "IdCliente": str(1000 + i),
            "Estado": "Jurídica",
            "DiasAtraso": str(mora),
            # 3 decimales en algunas filas: el caso ambiguo por valor suelto.
            "DeudaTotal": f"{50000 + i * 1234}.{482 if i % 2 else 8}",
            "Cuota": f"{2000 + i}.5",
            "IngresoLiquido": str(20000 + i * 500),
            "ScoreCash": "ABCDEFG"[i % 7] if i % 5 else "",
            "ScoreCash_Numerico": "9999" if i % 5 == 0 else f"{400 + i * 10}.1234",
            "AntiguedadDias": str(365 * (1 + i % 10)),
            "PPI_Cumplidas": str(i % 3),
            "PPI_Incumplidas": str(i % 2),
            "Cont_IntentosTotal": str(i % 9),
            "Cont_PctRespuesta": f"{(i * 7) % 100}.0",
            "PagosUlt3M_Cant": str(i % 4),
        })
    return pd.DataFrame(filas)


def test_una_fecha_no_es_un_numero():
    assert pd.isna(cm._a_numero("31/03/2026"))
    assert pd.isna(cm._a_numero("2026-03-31"))


def test_el_mapeo_no_confunde_fecha_letras_ni_periodos():
    df = _export()
    df.columns = [c.lstrip("﻿") for c in df.columns]
    m = cm.mapear_columnas(df.columns, df)
    assert "FechaScore" not in m
    assert m["ScoreCash_Numerico"] == "score_buro"     # no las letras
    assert "ScoreCash" not in m
    assert "PagosUlt3M_Cant" not in m                  # 3 meses no es 12
    assert m["PPI_Cumplidas"] == "promesas_cumplidas"
    assert m["PPI_Incumplidas"] == "promesas_incumplidas"
    assert m["Cont_IntentosTotal"] == "gestiones_previas"


def test_la_deuda_suma_lo_mismo_que_el_archivo():
    df = _export()
    out = cm.importar_y_scorear(df)
    esperado = pd.to_numeric(df["DeudaTotal"]).sum()
    assert out["monto_deuda"].sum() == pytest.approx(esperado)


def test_el_probpago_no_se_satura():
    out = cm.importar_y_scorear(_export(60))
    p = out["probpago"]
    assert (p >= 0.99).mean() < 0.2
    assert 0.05 < p.mean() < 0.95
    # A más mora, menos probabilidad de pago.
    assert out.loc[out.dias_mora <= 60, "probpago"].mean() > \
        out.loc[out.dias_mora >= 400, "probpago"].mean()


def test_centinelas_unidades_y_porcentajes():
    contactos = cm.desde_dataframe(_export())
    c0 = contactos[0]                       # ScoreCash_Numerico = 9999
    assert "score_buro" not in c0           # sin dato -> supuesto, no 9999
    assert contactos[1]["score_buro"] == pytest.approx(410.1234)
    assert contactos[0]["antiguedad_cliente_meses"] == pytest.approx(12.0, abs=0.1)
    assert all(0 <= c["contactabilidad"] <= 1 for c in contactos)


def test_miles_con_punto_siguen_siendo_miles():
    """La detección por columna no rompe el formato es: `5.000` = cinco mil."""
    df = pd.DataFrame({"deuda": ["5.000", "12.500", "1.234.567"]})
    montos = [c["monto_deuda"] for c in cm.desde_dataframe(df)]
    assert montos == [5000.0, 12500.0, 1234567.0]


def test_un_valor_fuera_de_rango_no_satura_el_modelo():
    df = cm.cargar_manual([{"monto_deuda": 1_140_273_482.0, "score_buro": 31_032_026,
                            "dias_mora": 120}])
    out = cm.puntuar(cm.modelo_prior(), df)
    assert out["probpago"].iloc[0] < 0.99
    assert out["monto_deuda"].iloc[0] == 1_140_273_482.0   # lo que se muestra, intacto
