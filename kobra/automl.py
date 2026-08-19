# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · AutoML — el cliente entrena con su propio dataset
===============================================================
Módulo de la suite (`plan.exigir("automl")`). El cliente sube una tabla suya,
elige qué columna quiere predecir, y Kobra prueba varios algoritmos y se queda
con el mejor. Sin escribir código y sin contratar un desarrollo.

La parte difícil no es probar modelos
--------------------------------------
Probar cinco algoritmos y quedarse con el de mayor AUC son veinte líneas. Lo
que hace que un AutoML sirva o mienta es **de dónde sale el número que se le
muestra al cliente**, y ahí casi todos fallan del mismo modo:

    se parte en entrenamiento y prueba
    se entrenan cinco modelos
    se elige el de mejor AUC en prueba
    se reporta ESE AUC

El último paso está mal. Al elegir el máximo entre cinco mediciones sobre el
mismo conjunto, ese máximo ya no es una estimación imparcial: incorpora la
suerte del modelo ganador en ese corte puntual. El número reportado sale
siempre optimista, y el cliente descubre la diferencia en producción, que es
el peor momento y el que rompe la confianza.

Acá se parte en **tres**:

    entrenamiento (60%)  — ajusta los modelos
    selección     (20%)  — decide cuál gana
    holdout       (20%)  — SOLO se mide, nunca se usa para decidir nada

El número que se reporta sale del holdout. Y se informa además la **brecha**
entre selección y holdout: es cuánto se hubiera exagerado con el método
habitual, y es información honesta que el cliente puede usar.

Series temporales
-----------------
Si el cliente indica una columna de fecha, los cortes se hacen **por tiempo**,
no al azar: entrenar con datos de agosto para predecir julio infla cualquier
métrica y no se puede reproducir en producción, donde el futuro no está
disponible. Un `train_test_split` aleatorio sobre datos con orden temporal es
la fuga de información más común que existe.

Detección de fuga
-----------------
Una columna que predice casi perfecto casi nunca es una buena señal: suele ser
una consecuencia del resultado que se coló como si fuera una causa (la fecha
de pago para predecir si paga, el saldo final para predecir la mora). Se avisa
en vez de celebrarlo.

Sobre los datos del cliente
---------------------------
Este módulo procesa datos que sube el cliente, que son suyos y pueden ser
reales. El archivo se lee, se entrena y **no se guarda**: solo persiste el
modelo y las métricas. Si además tiene el módulo de gobernanza, la
clasificación de columnas corre sobre la tabla subida y queda registrada.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

SEMILLA = 42          # reproducible, igual que el resto del repo

# Topes para que un archivo grande no cuelgue la máquina del cliente.
MAX_FILAS = 200_000
MAX_COLUMNAS = 200
MIN_FILAS = 60        # por debajo de esto, tres cortes no tienen sentido

# Una columna con casi tantos valores distintos como filas es un identificador
# (número de cliente, de contrato). No aporta señal y hace explotar el
# one-hot; se descarta con aviso.
UMBRAL_IDENTIFICADOR = 0.9

# Por encima de esto, un AUC es sospechoso de fuga y no un logro.
UMBRAL_SOSPECHA = 0.98


class DatosInsuficientes(ValueError):
    """El dataset no permite entrenar. El mensaje va a la pantalla."""


def _modelos() -> dict:
    """Los candidatos. Deliberadamente pocos y distintos entre sí.

    Probar treinta variantes del mismo algoritmo no mejora el resultado y sí
    empeora el sesgo de selección: cuantas más mediciones, más alto el máximo
    por puro azar. Cinco familias distintas cubren el espacio real.
    """
    return {
        "Regresión logística": LogisticRegression(max_iter=1000, random_state=SEMILLA),
        "Árbol de decisión": DecisionTreeClassifier(max_depth=6, random_state=SEMILLA),
        "Bosque aleatorio": RandomForestClassifier(
            n_estimators=200, max_depth=10, random_state=SEMILLA, n_jobs=-1),
        "Gradient boosting": GradientBoostingClassifier(random_state=SEMILLA),
    }


def _preparador(X: pd.DataFrame) -> ColumnTransformer:
    """Numéricas: imputar + escalar. Categóricas: imputar + one-hot.

    Va dentro del Pipeline a propósito, no antes: si se escalara sobre la tabla
    entera, la media y el desvío del conjunto de prueba se filtrarían al
    entrenamiento. Es una fuga chica pero real, y de las que nadie ve.
    """
    numericas = [c for c in X.columns if pd.api.types.is_numeric_dtype(X[c])]
    categoricas = [c for c in X.columns if c not in numericas]
    bloques = []
    if numericas:
        bloques.append(("num", Pipeline([
            ("imputar", SimpleImputer(strategy="median")),
            ("escalar", StandardScaler()),
        ]), numericas))
    if categoricas:
        bloques.append(("cat", Pipeline([
            ("imputar", SimpleImputer(strategy="most_frequent")),
            ("codificar", OneHotEncoder(handle_unknown="ignore", max_categories=20)),
        ]), categoricas))
    return ColumnTransformer(bloques, remainder="drop")


def _revisar(df: pd.DataFrame, objetivo: str) -> list[str]:
    """Chequeos previos. Devuelve avisos; levanta si no se puede seguir."""
    avisos = []
    if objetivo not in df.columns:
        raise DatosInsuficientes(
            f"la columna a predecir ({objetivo!r}) no está en el archivo")
    if len(df) < MIN_FILAS:
        raise DatosInsuficientes(
            f"hacen falta al menos {MIN_FILAS} filas para entrenar y medir "
            f"por separado; el archivo tiene {len(df)}")
    if len(df) > MAX_FILAS:
        avisos.append(f"se usaron las primeras {MAX_FILAS:,} filas de {len(df):,}")
    if len(df.columns) > MAX_COLUMNAS:
        raise DatosInsuficientes(
            f"demasiadas columnas ({len(df.columns)}); el máximo es {MAX_COLUMNAS}")

    y = df[objetivo]
    clases = y.dropna().nunique()
    if clases < 2:
        raise DatosInsuficientes(
            f"la columna {objetivo!r} tiene un solo valor: no hay nada que "
            "predecir")
    if clases > 2:
        raise DatosInsuficientes(
            f"la columna {objetivo!r} tiene {clases} valores distintos. Por "
            "ahora se predicen columnas de dos valores (sí/no, paga/no paga)")

    reparto = y.value_counts(normalize=True)
    minoria = float(reparto.min())
    if minoria < 0.05:
        avisos.append(
            f"la clase menos frecuente es apenas el {minoria * 100:.1f}% de los "
            "datos: el modelo puede acertar mucho sin aprender nada útil")
    return avisos


def _descartar_identificadores(X: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Saca columnas que son identificadores, no señal.

    "Muchos valores distintos" NO alcanza como criterio, y creer que sí es un
    error caro: un monto de deuda es un decimal continuo, tiene un valor
    distinto por fila igual que un número de contrato, y es la columna más
    predictiva de una cartera. Descartarla dejaría al modelo sin su mejor
    variable, en silencio y sin que el cliente entienda por qué predice mal.

    Por eso el criterio depende del tipo:

      * **decimales** — nunca se descartan. Son mediciones (monto, tasa,
        contactabilidad); que no se repitan es lo normal.
      * **enteros** — solo si son únicos en TODAS las filas. Un entero sin un
        solo repetido en miles de filas es un número de contrato, no una edad.
      * **texto** — si casi no se repiten. Un nombre o un código de operación.
    """
    fuera = []
    n = len(X)
    for col in X.columns:
        s = X[col]
        distintos = s.nunique(dropna=True)
        if pd.api.types.is_float_dtype(s):
            continue
        if pd.api.types.is_integer_dtype(s):
            if distintos == n and n > 1:
                fuera.append(col)
        elif distintos >= max(2, int(n * UMBRAL_IDENTIFICADOR)):
            fuera.append(col)
    return X.drop(columns=fuera), fuera


def _cortar(df: pd.DataFrame, columna_fecha: str | None):
    """Los tres cortes: entrenamiento / selección / holdout.

    Con `columna_fecha`, se corta por tiempo. Sin ella, al azar con semilla
    fija. El corte temporal no es un detalle: entrenar con el futuro para
    predecir el pasado infla la métrica y no se puede repetir en producción.
    """
    if columna_fecha and columna_fecha in df.columns:
        orden = pd.to_datetime(df[columna_fecha], errors="coerce")
        df = df.assign(_orden=orden).sort_values("_orden").drop(columns="_orden")
        temporal = True
    else:
        df = df.sample(frac=1.0, random_state=SEMILLA)
        temporal = False
    n = len(df)
    a, b = int(n * 0.6), int(n * 0.8)
    return df.iloc[:a], df.iloc[a:b], df.iloc[b:], temporal


def _medir(modelo, X, y) -> dict:
    p = modelo.predict_proba(X)[:, 1]
    return {
        "auc": round(float(roc_auc_score(y, p)), 4),
        "precision_media": round(float(average_precision_score(y, p)), 4),
        "brier": round(float(brier_score_loss(y, p)), 4),
    }


def entrenar(df: pd.DataFrame, objetivo: str,
             columna_fecha: str | None = None) -> dict:
    """Entrena, elige y mide. Devuelve el informe completo.

    El AUC que se reporta sale del holdout, que no se usó para elegir nada.
    """
    avisos = _revisar(df, objetivo)
    df = df.head(MAX_FILAS).dropna(subset=[objetivo])

    # El objetivo puede venir como texto ("sí"/"no"): se mapea a 0/1 dejando
    # como 1 el valor menos frecuente, que es el evento de interés en cobranzas
    # (lo raro es lo que se quiere anticipar).
    valores = df[objetivo].value_counts()
    positivo = valores.index[-1]
    y_todo = (df[objetivo] == positivo).astype(int)

    X_todo = df.drop(columns=[objetivo])
    if columna_fecha and columna_fecha in X_todo.columns:
        X_todo = X_todo.drop(columns=[columna_fecha])
    X_todo, descartadas = _descartar_identificadores(X_todo)
    if descartadas:
        avisos.append(
            "se descartaron por parecer identificadores (un valor distinto por "
            f"fila, sin señal): {', '.join(descartadas)}")
    if X_todo.empty or not len(X_todo.columns):
        raise DatosInsuficientes(
            "no quedó ninguna columna utilizable para predecir")

    juntos = X_todo.assign(**{objetivo: y_todo})
    if columna_fecha and columna_fecha in df.columns:
        juntos = juntos.assign(**{columna_fecha: df[columna_fecha]})
    tr, sel, hold, temporal = _cortar(juntos, columna_fecha)

    def partir(parte):
        yy = parte[objetivo]
        xx = parte.drop(columns=[c for c in (objetivo, columna_fecha)
                                 if c and c in parte.columns])
        return xx, yy

    X_tr, y_tr = partir(tr)
    X_sel, y_sel = partir(sel)
    X_hold, y_hold = partir(hold)

    for nombre, parte in (("selección", y_sel), ("holdout", y_hold)):
        if parte.nunique() < 2:
            raise DatosInsuficientes(
                f"el tramo de {nombre} quedó con una sola clase. Hacen falta "
                "más datos, o más equilibrio entre las dos clases")

    # --- entrenar y elegir, mirando SOLO selección -------------------------
    candidatos = []
    for nombre, estimador in _modelos().items():
        pipe = Pipeline([("preparar", _preparador(X_tr)), ("modelo", estimador)])
        try:
            pipe.fit(X_tr, y_tr)
            candidatos.append({"modelo": nombre, "pipeline": pipe,
                               "seleccion": _medir(pipe, X_sel, y_sel)})
        except Exception as e:                          # noqa: BLE001
            # Un algoritmo que no converge con estos datos no puede tumbar la
            # corrida entera: se reporta y se sigue con los demás.
            avisos.append(f"{nombre} no se pudo entrenar: {e}")

    if not candidatos:
        raise DatosInsuficientes(
            "ningún algoritmo pudo entrenar con estos datos")

    ganador = max(candidatos, key=lambda c: c["seleccion"]["auc"])

    # --- medir el ganador en el holdout intacto ----------------------------
    en_holdout = _medir(ganador["pipeline"], X_hold, y_hold)
    brecha = round(ganador["seleccion"]["auc"] - en_holdout["auc"], 4)

    if en_holdout["auc"] >= UMBRAL_SOSPECHA:
        avisos.append(
            f"un AUC de {en_holdout['auc']} es sospechosamente alto. Suele "
            "significar que alguna columna es una consecuencia del resultado y "
            "no una causa (por ejemplo, la fecha de pago para predecir si "
            "paga). Revisá las columnas antes de confiar en este número")

    return {
        "modelo_elegido": ganador["modelo"],
        # Este es el número honesto: sale de datos que no se usaron para
        # entrenar NI para elegir.
        "holdout": en_holdout,
        "en_seleccion": ganador["seleccion"],
        # Cuánto se hubiera exagerado reportando el tramo donde se eligió.
        "brecha_seleccion_holdout": brecha,
        "candidatos": [{"modelo": c["modelo"], "seleccion": c["seleccion"]}
                       for c in candidatos],
        "corte_temporal": temporal,
        "filas": {"entrenamiento": len(tr), "seleccion": len(sel),
                  "holdout": len(hold)},
        "columnas_usadas": list(X_tr.columns),
        "columnas_descartadas": descartadas,
        "clase_positiva": str(positivo),
        "avisos": avisos,
        "pipeline": ganador["pipeline"],
    }


def informe(resultado: dict) -> dict:
    """El resultado sin el objeto del modelo — lo que viaja al frontend."""
    return {k: v for k, v in resultado.items() if k != "pipeline"}


def importancias(resultado: dict, tope: int = 15) -> list[dict]:
    """Qué columnas pesaron. Un modelo que nadie puede explicar no se usa para
    decidir sobre personas, y en cobranzas hay que poder justificar la
    decisión."""
    pipe = resultado.get("pipeline")
    if pipe is None:
        return []
    modelo = pipe.named_steps.get("modelo")
    try:
        nombres = list(pipe.named_steps["preparar"].get_feature_names_out())
    except Exception:                                   # noqa: BLE001
        return []

    if hasattr(modelo, "feature_importances_"):
        pesos = np.asarray(modelo.feature_importances_, dtype=float)
    elif hasattr(modelo, "coef_"):
        pesos = np.abs(np.asarray(modelo.coef_, dtype=float)).ravel()
    else:
        return []
    if len(pesos) != len(nombres):
        return []

    total = pesos.sum() or 1.0
    pares = sorted(zip(nombres, pesos), key=lambda p: p[1], reverse=True)
    return [{"columna": n, "peso": round(float(p / total), 4)}
            for n, p in pares[:tope] if p > 0]
