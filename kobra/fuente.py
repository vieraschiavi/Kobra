"""Qué cartera está mirando el tablero: la demo o la del cliente.

**El problema.** Cargar la cartera propia servía para una sola pestaña.
«Probar mi cartera» la puntuaba, la negociaba y la mostraba ahí adentro;
las otras once seguían dibujando los 12.000 deudores sintéticos. El que
sube su cartera quiere ver SU cartera en el tablero, no un demo con su
archivo escondido en una pestaña.

La capacidad ya estaba escrita: `cartera_manual.importar_y_scorear`
—cuyo docstring dice, textual, «lista para reemplazar los datos de demo
del dashboard»— devuelve la cartera con ProbPago, decil, estrategia y
motivo. Lo que faltaba era enchufarla.

**Por qué esto es un módulo y no tres líneas en `app.py`.** Cambiar la
fuente de datos de un tablero entero no es sólo `df = otra_cosa`: hay
que saber QUÉ deja de ser cierto. Con la cartera del cliente no hay
historial de gestiones, no hay métricas de validación del modelo medidas
sobre ella, y su tamaño suele ser de decenas de filas y no de miles.
Dibujar la evolución de gestiones del demo encima de la cartera de un
cliente sería exactamente la clase de pantalla que este repo no entrega:
un gráfico plausible, sin error, y falso.

Así que la fuente no devuelve sólo el DataFrame: devuelve también qué se
puede afirmar con él.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

#: Clave de sesión donde la app guarda la cartera del cliente ya scoreada.
#: Vive acá y no en `app.py` para que el nombre sea uno solo: una pestaña
#: que la escriba con otra clave dejaría el tablero mirando la demo sin
#: que nada falle.
CLAVE_SESION = "cartera_propia"

#: Debajo de esto, los agregados del tablero (deciles, evolución, cortes
#: por gestor) describen el ruido de la muestra más que a la cartera. No
#: se bloquea nada —el que sube 12 contactos quiere verlos— pero se dice.
MINIMO_PARA_AGREGADOS = 30


@dataclass(frozen=True)
class Fuente:
    """La cartera activa y qué se puede afirmar sobre ella."""

    df: pd.DataFrame
    propia: bool
    #: Historial de gestiones. Vacío para una cartera propia: el cliente
    #: sube deudores, no el registro de lo que ya se les hizo.
    gestiones: pd.DataFrame = field(default_factory=pd.DataFrame)
    #: Métricas de validación del modelo. `None` cuando no se midieron
    #: sobre ESTA cartera — que es el caso de la del cliente: el modelo
    #: viene entrenado con la de referencia.
    metricas: dict | None = None

    @property
    def filas(self) -> int:
        return len(self.df)

    @property
    def hay_gestiones(self) -> bool:
        return not self.gestiones.empty

    @property
    def pocas_filas(self) -> bool:
        return self.propia and self.filas < MINIMO_PARA_AGREGADOS


def desde_demo(df: pd.DataFrame, gestiones: pd.DataFrame,
               metricas: dict) -> Fuente:
    """La de siempre: 12.000 deudores sintéticos con su historial."""
    return Fuente(df=df, propia=False, gestiones=gestiones, metricas=metricas)


def desde_propia(df: pd.DataFrame) -> Fuente:
    """La del cliente, ya scoreada por `importar_y_scorear`.

    Sin gestiones y sin métricas **a propósito**, no por falta de tiempo:
    no existen para esta cartera y rellenarlas con las del demo sería
    mostrarle al cliente la evolución de otra gente con el nombre de la
    suya.
    """
    return Fuente(df=df, propia=True)


def aviso(f: Fuente) -> str:
    """Una línea que diga qué se está mirando. Vacía para la demo.

    Se devuelve texto y no se dibuja acá: este módulo se importa y se
    testea sin levantar Streamlit.
    """
    if not f.propia:
        return ""
    partes = [f"Estás viendo **tu cartera**: {f.filas} deudor(es), "
              "puntuados con el mismo ProbPago que la demo."]
    if f.pocas_filas:
        partes.append(
            f"Con menos de {MINIMO_PARA_AGREGADOS} filas, los cortes por "
            "decil y los promedios describen más el ruido de la muestra "
            "que a la cartera: mirá los casos uno por uno.")
    return " ".join(partes)


def sin_historial(f: Fuente) -> str:
    """Qué decir en una pestaña que necesita gestiones y no las tiene."""
    if not f.propia or f.hay_gestiones:
        return ""
    return ("Esta pestaña se arma con el **historial de gestiones**, y tu "
            "cartera no lo trae: subiste deudores, no el registro de lo "
            "que ya se les hizo. Se muestra vacía a propósito — dibujar "
            "acá la evolución del demo sería mostrarte la actividad de "
            "otra gente con el nombre de tus clientes. Para llenarla, "
            "traé también tu tabla de gestiones desde «Integración ERP».")
