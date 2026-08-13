# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Exportar ProbPago para scorear en el navegador
=============================================================
Convierte el modelo entrenado (`outputs/probpago_model.joblib`) en un JSON que
el demo público puede usar para scorear un CSV **sin backend**: el archivo del
visitante nunca sale de su navegador.

Por qué se puede hacer sin perder exactitud
-------------------------------------------
El modelo que gana la selección es una `LogisticRegression` calibrada
(`CalibratedClassifierCV` con 3 pliegues e isotónica). Todo eso es aritmética
que se reimplementa exacto:

    z     = intercept + Σ coef·x         (con x escalado y one-hot)
    p_cal = interpolación lineal en los nodos de la isotónica, SOBRE z
    p     = promedio de los 3 pliegues

OJO con el segundo paso: la isotónica de `CalibratedClassifierCV` se ajusta
sobre la salida de `decision_function` —o sea `z` crudo, que acá va de -9,88 a
6,99— y NO sobre la sigmoide. Aplicar `1/(1+e^-z)` antes de interpolar da
números plausibles y equivocados: al probarlo así, la diferencia máxima contra
scikit-learn era 0,525. Con `z` directo baja al error de punto flotante.

No es una aproximación ni un modelo "parecido para la demo": es el mismo
cálculo. `tests/test_scoring_web.py` compara la implementación JS contra
`predict_proba` de scikit-learn sobre la cartera real y exige que la diferencia
máxima sea despreciable. Si algún día `kobra.train` elige un modelo de árboles,
este exportador se planta en vez de exportar algo que no es el modelo.

Uso:
    python -m kobra.exportar_modelo_web
    python -m kobra.exportar_modelo_web --salida dashboard_estatico/modelo_web.json
"""
from __future__ import annotations

import json
import os

from kobra import rutas as krutas

MODELO = os.path.join(krutas.DIR_DATOS, "outputs", "probpago_model.joblib")
SALIDA_DEFAULT = os.path.join(krutas.ROOT_REPO, "dashboard_estatico", "modelo_web.json")


class ModeloNoExportable(Exception):
    """El modelo entrenado no es lineal: no se puede reimplementar en JS."""


def _exportar_preprocesador(pre) -> dict:
    """Escalador y one-hot, en el MISMO orden de columnas que produce
    scikit-learn. El orden importa: los coeficientes están alineados a él."""
    num_cols, cat_cols = [], []
    escala = {"media": [], "desvio": []}
    categorias = {}
    for _nombre, trans, cols in pre.transformers_:
        cols = list(cols)
        tipo = type(trans).__name__
        if tipo == "StandardScaler":
            num_cols = cols
            escala["media"] = [float(x) for x in trans.mean_]
            escala["desvio"] = [float(x) for x in trans.scale_]
        elif tipo == "OneHotEncoder":
            cat_cols = cols
            for col, cats in zip(cols, trans.categories_):
                categorias[col] = [str(c) for c in cats]
        elif tipo not in ("drop", "passthrough"):
            raise ModeloNoExportable(f"transformador no soportado: {tipo}")
    return {"orden_transformers": [t[0] for t in pre.transformers_],
            "numericas": num_cols, "categoricas": cat_cols,
            "escala": escala, "categorias": categorias}


def exportar(ruta_modelo: str = MODELO, salida: str = SALIDA_DEFAULT) -> dict:
    import joblib

    cal = joblib.load(ruta_modelo)
    if type(cal).__name__ != "CalibratedClassifierCV":
        raise ModeloNoExportable(
            f"se esperaba CalibratedClassifierCV y vino {type(cal).__name__}")

    # CADA pliegue lleva su propio preprocesador. No es un detalle: con cv=3,
    # `CalibratedClassifierCV` reajusta el pipeline entero —escalador incluido—
    # sobre el subconjunto de entrenamiento de cada pliegue, así que las medias
    # y los desvíos difieren entre los tres. Guardar uno solo y reusarlo daría
    # números parecidos pero equivocados, que en una demo de scoring es peor
    # que no tener demo. Lo detectó el chequeo de abajo al primer intento.
    pliegues = []
    columnas_ref = None
    for c in cal.calibrated_classifiers_:
        pipe = c.estimator
        clf = pipe.named_steps["clf"]
        if type(clf).__name__ != "LogisticRegression":
            raise ModeloNoExportable(
                f"el clasificador es {type(clf).__name__}: solo se puede "
                "reimplementar en el navegador un modelo lineal. Reentrenar "
                "con kobra.train y volver a exportar, o servir el scoring "
                "desde el backend.")
        pre = _exportar_preprocesador(pipe.named_steps["pre"])
        columnas = (pre["orden_transformers"], pre["numericas"],
                    pre["categoricas"], pre["categorias"])
        if columnas_ref is None:
            columnas_ref = columnas
        elif columnas != columnas_ref:
            # Las COLUMNAS y las categorías sí tienen que coincidir: si un
            # pliegue no vio una categoría, su vector tendría otro largo.
            raise ModeloNoExportable(
                "los pliegues no comparten las mismas columnas o categorías")

        iso = c.calibrators[0]
        pliegues.append({
            "pre": pre,
            "coef": [float(x) for x in clf.coef_[0]],
            "intercept": float(clf.intercept_[0]),
            "calibrador": {
                "x": [float(v) for v in iso.X_thresholds_],
                "y": [float(v) for v in iso.y_thresholds_],
            },
        })

    bundle = {
        "modelo": "LogisticRegression + CalibratedClassifierCV(isotonic)",
        "pliegues": pliegues,
        # Copia de las columnas/categorías, iguales en los tres pliegues: es lo
        # que necesita el lector de CSV para saber qué columnas pedir.
        "pre": {k: pliegues[0]["pre"][k] for k in
                ("orden_transformers", "numericas", "categoricas", "categorias")},
        "aviso": ("Coeficientes de un modelo entrenado sobre datos 100% "
                  "SINTÉTICOS. Sirve para ver la mecánica del scoring; el "
                  "desempeño real se mide con la cartera del cliente."),
    }
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, separators=(",", ":"))

    # Y el MISMO bundle como .js, igual que `kobra_data.js`. No es redundancia:
    # el ZIP de la demo se abre con doble clic —o sea `file://`— y ahí el
    # navegador bloquea `fetch()` de un archivo local. Con `<script src>` anda
    # igual offline. El .json queda porque es el artefacto que sirve la web y lo
    # que compara el test contra el .joblib.
    with open(_ruta_js(salida), "w", encoding="utf-8") as f:
        f.write("window.KOBRA_MODELO = ")
        json.dump(bundle, f, ensure_ascii=False, separators=(",", ":"))
        f.write(";")
    return bundle


def _ruta_js(salida: str) -> str:
    base, _ = os.path.splitext(salida)
    return base + ".js"


def scorear(bundle: dict, filas: list) -> list:
    """La MISMA aritmética que hace `scoring.js`, en Python.

    Existe para poder testear el algoritmo contra scikit-learn sin levantar un
    navegador. `tests/test_scoring_web.py` verifica además que el JS coincida
    con esta, así la cadena queda cerrada: sklearn ↔ Python ↔ JavaScript.
    """
    def vector(fila, pre):
        num, cat = pre["numericas"], pre["categoricas"]
        media, desvio = pre["escala"]["media"], pre["escala"]["desvio"]
        cats = pre["categorias"]
        # scikit-learn concatena los bloques en el orden de `transformers_`.
        orden = pre["orden_transformers"]
        v_num = [((float(fila.get(c, 0) or 0) - media[i]) / (desvio[i] or 1.0))
                 for i, c in enumerate(num)]
        v_cat = []
        for c in cat:
            valor = str(fila.get(c, ""))
            v_cat += [1.0 if valor == opcion else 0.0 for opcion in cats[c]]
        bloques = {"num": v_num, "cat": v_cat}
        salida = []
        for nombre in orden:
            salida += bloques.get(nombre, [])
        return salida

    def interpolar(iso, p):
        x, y = iso["x"], iso["y"]
        if p <= x[0]:
            return y[0]
        if p >= x[-1]:
            return y[-1]
        lo, hi = 0, len(x) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if x[mid] <= p:
                lo = mid
            else:
                hi = mid
        if x[hi] == x[lo]:
            return y[lo]
        t = (p - x[lo]) / (x[hi] - x[lo])
        return y[lo] + t * (y[hi] - y[lo])

    salida = []
    for fila in filas:
        total = 0.0
        for pl in bundle["pliegues"]:
            v = vector(fila, pl["pre"])
            z = pl["intercept"] + sum(c * x for c, x in zip(pl["coef"], v))
            # `z` directo, sin sigmoide: ver la nota del encabezado.
            total += interpolar(pl["calibrador"], z)
        salida.append(total / len(bundle["pliegues"]))
    return salida


def main():
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("--modelo", default=MODELO)
    ap.add_argument("--salida", default=SALIDA_DEFAULT)
    args = ap.parse_args()
    b = exportar(args.modelo, args.salida)
    tam = os.path.getsize(args.salida)
    print(f"[OK] {args.salida}  ({tam // 1024} KB)")
    print(f"     {_ruta_js(args.salida)}  (mismo bundle, para abrir con file://)")
    print(f"     {b['modelo']} · {len(b['pliegues'])} pliegues · "
          f"{len(b['pre']['numericas'])} numéricas + "
          f"{len(b['pre']['categoricas'])} categóricas")


if __name__ == "__main__":
    main()
