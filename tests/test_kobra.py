"""
Kobra · Tests
=============
Pruebas rápidas del pipeline end-to-end: dataset, ProbPago, negociador y
copiloto de negociación. Corren en segundos con un dataset pequeño.

    pytest -q
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data.generate_dataset import generar
from kobra.probpago import ProbPagoModel
from kobra import negociador, copiloto


def _df():
    return generar(n=1500, seed=7)


def test_dataset_schema():
    df = _df()
    for col in ["id_deudor", "monto_deuda", "dias_mora", "pago", "tramo_mora"]:
        assert col in df.columns
    assert df["pago"].isin([0, 1]).all()
    assert (df["monto_deuda"] > 0).all()
    assert 0.2 < df["pago"].mean() < 0.9   # tasa de pago razonable


def test_probpago_entrena_y_scorea():
    df = _df()
    model = ProbPagoModel().fit(df)
    assert model.metrics["auc_roc"] > 0.7          # el modelo aprende señal
    scored = model.score(df)
    assert scored["probpago"].between(0, 1).all()
    assert set(scored["segmento_propension"].dropna().unique()) <= {"Alta", "Media", "Baja"}


def test_negociador_recomienda():
    df = _df()
    scored = ProbPagoModel().fit(df).score(df)
    full = negociador.recomendar(scored)
    assert (full["valor_esperado_recupero"] >= 0).all()
    assert full["prioridad"].nunique() == len(full)   # prioridad única
    assert full["guion"].str.len().gt(10).all()       # todos tienen guion


def test_copiloto_sentimiento():
    pos = copiloto.analizar_sentimiento("Perfecto, muchas gracias, acepto el plan")
    neg = copiloto.analizar_sentimiento("No puedo pagar, estoy sin trabajo y harto")
    assert pos.score > 0 and pos.etiqueta == "positivo"
    assert neg.score < 0 and neg.etiqueta == "negativo"


def test_copiloto_analisis_completo():
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "ejemplo_whatsapp.txt")
    texto = open(ruta, encoding="utf-8").read()
    res = copiloto.analizar_conversacion(texto, canal="whatsapp", probpago=0.7,
                                         estrategia="Plan de cuotas")
    assert res["meta"]["mensajes"] > 5
    assert 0 <= res["calidad"]["score_total"] <= 100
    assert any(res["tecnicas"].values())               # detecta alguna técnica
    assert len(res["copiloto"]["sugerencias"]) >= 1
    assert res["copiloto"]["proxima_frase"]


def test_copiloto_parser_plano():
    conv = copiloto.parsear_conversacion(
        "Gestor: Hola, buenos dias\nCliente: hola\nGestor: le ofrezco un plan",
        canal="llamada")
    assert conv.total_mensajes == 3
    assert conv.nombre_gestor == "Gestor"
