# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Proyección de cobranza: cuánto se va a recuperar, y si se puede creer
===================================================================================
Predice la serie diaria de cobranza para los próximos días. Lo que distingue a
este módulo no es el modelo: es que **la proyección tiene que ganarse el
derecho a mostrarse**.

El problema con proyectar cobranzas
-----------------------------------
Una línea proyectada en un tablero se lee como un compromiso. El gerente arma
la meta del mes con ese número, y si la serie no tenía señal —muchas carteras
no la tienen: la cobranza diaria es ruido alrededor de un promedio— la línea
igual se dibuja, prolija y convincente, porque un modelo SIEMPRE devuelve
algo. Ese es el daño: no un error grande, sino un error con cara de dato.

Por eso acá el resultado del backtest puede ser «no hay señal», y ese
resultado se muestra tal cual en vez de una curva.

Cómo se elige el modelo
-----------------------
Origen rodante (walk-forward) sobre DOS ventanas separadas:

1. **Ventana de selección** — se prueban todos los modelos y se elige el mejor.
2. **Holdout ciego** — no se usó para elegir nada. Es el único número que se
   reporta como performance esperada.

La diferencia entre las dos es la parte más informativa del informe: si el
modelo elegido rinde mucho peor en el holdout, lo que se eligió fue ruido.
Reportar el error del tramo donde se eligió el modelo —el error más común en
proyecciones— es contar la nota del examen que uno mismo escribió.

La vara: MASE
-------------
El error absoluto medio dividido por el del ingenuo estacional. **MASE < 1 =
mejor que repetir la semana pasada; MASE >= 1 = el modelo no aporta.** Un MAE
en pesos no dice nada por sí solo: $400.000 de error es excelente en una
cartera que cobra 8 millones por día y ridículo en una que cobra 500.000.

Sobre los modelos
-----------------
Los baselines viven acá y no dependen de nada más que numpy. TimesFM (el
modelo fundacional de Google) es OPCIONAL y vive en `proyeccion_timesfm.py`:
pesa 925 MB y necesita PyTorch, así que el programa instalado no lo lleva y
funciona igual. Si está disponible, compite como un modelo más — y si no le
gana al ingenuo estacional en el holdout, no se usa.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

# Estacionalidad semanal: la cobranza tiene forma de semana (los lunes no se
# parecen a los domingos) mucho más que forma de mes.
PERIODO = 7

# Cuánto tiene que ganarle un modelo al ingenuo estacional para que valga la
# pena usarlo. Un 2% de mejora en el holdout es indistinguible de la suerte con
# pocas ventanas; pedir 10% es pedir una mejora que se note en la operación.
MARGEN_MINIMO = 0.10

HORIZONTE = 14          # dos semanas: el plazo con el que se arma una agenda
VENTANAS_SELECCION = 6  # orígenes para elegir modelo
VENTANAS_HOLDOUT = 4    # orígenes que NO se usaron para elegir


def serie_diaria(fechas: pd.Series, valores: pd.Series) -> pd.Series:
    """La serie diaria, con los días sin movimiento en cero y no salteados.

    Saltear los días vacíos desalinea la estacionalidad semanal: el modelo
    aprende que "el próximo punto" es el próximo día CON datos, que puede ser
    tres días después, y la forma de la semana desaparece.
    """
    f = pd.to_datetime(fechas, format="mixed", errors="coerce").dt.normalize()
    s = pd.Series(np.asarray(valores, dtype="float64"), index=f).dropna()
    if s.empty:
        return s
    s = s.groupby(level=0).sum().sort_index()
    return s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"),
                     fill_value=0.0)


# ---------------------------------------------------------------------------
# Los modelos. Cada uno: (historia, horizonte) -> predicción de largo horizonte
# ---------------------------------------------------------------------------
def _naive(h: np.ndarray, n: int) -> np.ndarray:
    """Repetir el último valor. La vara más baja que existe."""
    return np.repeat(h[-1], n)


def _estacional(h: np.ndarray, n: int) -> np.ndarray:
    """Repetir la última semana. Es el baseline SERIO en datos diarios."""
    if len(h) < PERIODO:
        return _naive(h, n)
    ultima = h[-PERIODO:]
    return np.array([ultima[i % PERIODO] for i in range(n)])


def _media(h: np.ndarray, n: int) -> np.ndarray:
    """El promedio de todo lo conocido. Imbatible cuando no hay señal."""
    return np.repeat(float(np.mean(h)), n)


def _media_movil(h: np.ndarray, n: int, ventana: int = 28) -> np.ndarray:
    """El promedio de las últimas 4 semanas: se adapta a un cambio de nivel."""
    return np.repeat(float(np.mean(h[-min(ventana, len(h)):])), n)


def _perfil_semanal(h: np.ndarray, n: int, semanas: int = 8) -> np.ndarray:
    """Media por día de la semana sobre las últimas semanas.

    Es el ingenuo estacional pero promediado: se queda con la FORMA de la
    semana y le saca el ruido de una semana puntual.
    """
    if len(h) < PERIODO * 2:
        return _estacional(h, n)
    recorte = h[-min(len(h), PERIODO * semanas):]
    # El último punto de la historia es el día (len-1); el primero del recorte
    # tiene que alinearse con el mismo día de la semana que tendría en la serie.
    desfasaje = (len(h) - len(recorte)) % PERIODO
    perfil = np.array([
        np.mean(recorte[(i - desfasaje) % PERIODO::PERIODO]) for i in range(PERIODO)
    ])
    return np.array([perfil[(len(h) + i) % PERIODO] for i in range(n)])


def _deriva(h: np.ndarray, n: int) -> np.ndarray:
    """Última observación más la pendiente promedio: tendencia, sin más."""
    if len(h) < 2:
        return _naive(h, n)
    paso = (h[-1] - h[0]) / (len(h) - 1)
    return h[-1] + paso * np.arange(1, n + 1)


MODELOS: dict[str, Callable[[np.ndarray, int], np.ndarray]] = {
    "ingenuo": _naive,
    "estacional_7": _estacional,
    "media": _media,
    "media_movil_28": _media_movil,
    "perfil_semanal": _perfil_semanal,
    "deriva": _deriva,
}

# La UNIDAD de medida: el MASE se escala con el ingenuo estacional. Cambiarlo
# cambia el significado de todos los números del informe, así que es una
# constante y no un parámetro suelto.
REFERENCIA = "estacional_7"

# La VARA de decisión, que no es lo mismo. Un modelo no se gana el derecho a
# mostrarse por ganarle a la referencia: se lo gana por ganarle al MEJOR de
# los modelos que no aprenden nada.
#
# La distinción no es teórica. En la cartera de demostración el ingenuo
# estacional rinde MASE 1,24 —es malo en esa serie— y contra esa vara casi
# cualquier cosa "mejora un 23%". Contra el promedio simple, que ahí rinde
# 0,80, no mejora ninguno: no hay señal. La primera lectura pone una línea
# proyectada en el tablero; la segunda dice la verdad.
TRIVIALES = ("ingenuo", "estacional_7", "media")


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------
def mase(real: np.ndarray, pred: np.ndarray, historia: np.ndarray) -> float:
    """Error absoluto medio escalado por el del ingenuo estacional EN LA
    HISTORIA (no en el tramo que se está evaluando: eso sería mirar la
    respuesta antes de contestar)."""
    if len(historia) <= PERIODO:
        return float("nan")
    escala = np.mean(np.abs(historia[PERIODO:] - historia[:-PERIODO]))
    if escala == 0:
        return float("nan")
    return float(np.mean(np.abs(real - pred)) / escala)


def smape(real: np.ndarray, pred: np.ndarray) -> float:
    """Simétrico y en porcentaje. Con ceros en la serie explota, por eso nunca
    se usa solo: acompaña al MASE, no lo reemplaza."""
    den = (np.abs(real) + np.abs(pred))
    with np.errstate(divide="ignore", invalid="ignore"):
        v = np.where(den == 0, 0.0, 2 * np.abs(real - pred) / den)
    return float(np.mean(v) * 100)


@dataclass(frozen=True)
class Resultado:
    """Lo que rindió un modelo en un conjunto de orígenes."""
    modelo: str
    mase: float
    smape: float
    mae: float
    ventanas: int


def _origenes(largo: int, horizonte: int, ventanas: int,
              reservar: int = 0) -> list[int]:
    """Los cortes de la historia donde se para el modelo a predecir.

    Van de atrás para adelante y separados por el horizonte: orígenes
    solapados comparten los mismos días reales y hacen parecer que hay más
    evidencia de la que hay.
    """
    fin = largo - reservar
    cortes = [fin - horizonte * (i + 1) for i in range(ventanas)]
    return sorted(c for c in cortes if c > PERIODO * 3)


def evaluar(serie: np.ndarray, modelo: Callable, horizonte: int,
            origenes: list[int]) -> Resultado | None:
    """Corre un modelo en cada origen y promedia. Sin ver nunca el futuro:
    en cada corte solo se le pasa `serie[:corte]`."""
    mases, smapes, maes = [], [], []
    for corte in origenes:
        historia, real = serie[:corte], serie[corte:corte + horizonte]
        if len(real) < horizonte:
            continue
        pred = np.asarray(modelo(historia, horizonte), dtype="float64")
        if pred.shape != real.shape or not np.all(np.isfinite(pred)):
            return None
        mases.append(mase(real, pred, historia))
        smapes.append(smape(real, pred))
        maes.append(float(np.mean(np.abs(real - pred))))
    if not mases:
        return None
    return Resultado("", float(np.nanmean(mases)), float(np.mean(smapes)),
                     float(np.mean(maes)), len(mases))


def comparar(serie: pd.Series | np.ndarray, horizonte: int = HORIZONTE,
             extra: dict[str, Callable] | None = None) -> dict:
    """El backtest completo, con doble ventana.

    Devuelve el veredicto: qué modelo ganó eligiendo sobre la ventana de
    selección, cuánto rindió DESPUÉS en el holdout ciego, y si eso alcanza
    para mostrarle una proyección a alguien.
    """
    y = np.asarray(serie, dtype="float64")
    modelos = {**MODELOS, **(extra or {})}
    minimo = horizonte * (VENTANAS_SELECCION + VENTANAS_HOLDOUT) + PERIODO * 3
    if len(y) < minimo:
        return {"suficiente": False, "n": len(y), "minimo": minimo,
                "motivo": (f"Hacen falta al menos {minimo} días de historia "
                           f"para evaluar honestamente y hay {len(y)}.")}

    reservado = horizonte * VENTANAS_HOLDOUT
    sel = _origenes(len(y), horizonte, VENTANAS_SELECCION, reservar=reservado)
    hold = _origenes(len(y), horizonte, VENTANAS_HOLDOUT)

    seleccion, holdout = {}, {}
    for nombre, fn in modelos.items():
        r = evaluar(y, fn, horizonte, sel)
        if r is None:
            continue
        seleccion[nombre] = Resultado(nombre, r.mase, r.smape, r.mae, r.ventanas)
        h = evaluar(y, fn, horizonte, hold)
        if h is not None:
            holdout[nombre] = Resultado(nombre, h.mase, h.smape, h.mae, h.ventanas)

    if not seleccion:
        return {"suficiente": False, "n": len(y),
                "motivo": "Ningún modelo pudo evaluarse sobre esta serie."}

    # El ganador se elige SOLO con la ventana de selección: mirar el holdout
    # para elegir lo convierte en otra ventana de selección y el número que se
    # reporta deja de ser ciego.
    ganador = min(seleccion, key=lambda k: seleccion[k].mase)
    gan_hold = holdout.get(ganador)

    # La vara: el mejor de los que no aprenden nada, medido en el holdout.
    triviales = {k: v for k, v in holdout.items() if k in TRIVIALES}
    mejor_trivial = (min(triviales, key=lambda k: triviales[k].mase)
                     if triviales else None)

    mejora = None
    if gan_hold and mejor_trivial and triviales[mejor_trivial].mase:
        mejora = 1 - gan_hold.mase / triviales[mejor_trivial].mase
    # Un trivial ganando es, por definición, "no hay nada que aprender acá".
    sirve = bool(gan_hold and ganador not in TRIVIALES
                 and mejora is not None and mejora >= MARGEN_MINIMO)

    return {
        "suficiente": True,
        "n": len(y),
        "horizonte": horizonte,
        "ganador": ganador,
        "referencia": REFERENCIA,
        "mejor_trivial": mejor_trivial,
        "seleccion": {k: vars(v) for k, v in seleccion.items()},
        "holdout": {k: vars(v) for k, v in holdout.items()},
        # La brecha selección→holdout: si el ganador rinde mucho peor en el
        # holdout, lo que se eligió fue ruido.
        "brecha": (None if not gan_hold else
                   gan_hold.mase - seleccion[ganador].mase),
        "mejora_vs_trivial": mejora,
        "sirve": sirve,
        # Con qué proyectar igual: cuando no hay señal, el mejor trivial es la
        # respuesta correcta —y hay que decir que es un promedio, no una
        # predicción.
        "modelo_a_usar": ganador if sirve else (mejor_trivial or REFERENCIA),
        # El veredicto va DOS veces: como código, para que la pantalla lo
        # traduzca a los tres idiomas sin que este módulo tenga que saber de
        # idiomas; y redactado en castellano, que es lo que se lee en el
        # informe de consola y en los logs.
        "codigo": _codigo(sirve, ganador, gan_hold),
        "veredicto": _veredicto(sirve, ganador, gan_hold, mejora, mejor_trivial),
    }


def _codigo(sirve: bool, ganador: str, gan_hold: Resultado | None) -> str:
    if not gan_hold:
        return "sin_holdout"
    if sirve:
        return "sirve"
    return "sin_senal" if ganador in TRIVIALES else "sin_margen"


def _veredicto(sirve: bool, ganador: str, gan_hold: Resultado | None,
               mejora: float | None, mejor_trivial: str | None) -> str:
    if not gan_hold:
        return "No se pudo evaluar el modelo elegido en el holdout ciego."
    if sirve:
        return (f"{ganador} le gana a todos los modelos que no aprenden nada: "
                f"MASE {gan_hold.mase:.2f} en el holdout ciego, "
                f"{mejora * 100:.0f}% mejor que {mejor_trivial}.")
    if ganador in TRIVIALES:
        return (f"Sin señal aprovechable: el que mejor predice es «{ganador}», "
                f"que no aprende nada de la serie. Se proyecta con "
                f"«{mejor_trivial}» y se muestra como lo que es —un promedio, "
                f"no una predicción—: dibujar una curva acá sería ponerle cara "
                f"de dato al ruido.")
    return (f"Sin señal suficiente: {ganador} no le saca al menos "
            f"{MARGEN_MINIMO * 100:.0f}% a «{mejor_trivial}» en el holdout "
            f"({mejora * 100:+.0f}%). Con esta cantidad de ventanas, una "
            f"diferencia así no se distingue de la suerte.")


def proyectar(serie: pd.Series, horizonte: int = HORIZONTE,
              modelo: str | None = None,
              extra: dict[str, Callable] | None = None) -> pd.DataFrame:
    """La proyección para los próximos días, con su fecha.

    `modelo` sale normalmente de `comparar()`. Sin él se usa la referencia:
    nunca un modelo elegido a dedo.
    """
    modelos = {**MODELOS, **(extra or {})}
    fn = modelos[modelo or REFERENCIA]
    y = np.asarray(serie, dtype="float64")
    pred = np.asarray(fn(y, horizonte), dtype="float64")
    # La cobranza no es negativa: un modelo con tendencia a la baja puede
    # proyectar números negativos y eso no es una predicción, es un error.
    pred = np.clip(pred, 0, None)
    fechas = pd.date_range(serie.index[-1] + pd.Timedelta(days=1),
                           periods=horizonte, freq="D")
    return pd.DataFrame({"fecha": fechas, "proyeccion": pred,
                         "modelo": modelo or REFERENCIA})
