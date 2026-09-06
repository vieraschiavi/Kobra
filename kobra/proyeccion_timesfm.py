# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Adaptador opcional de TimesFM (modelo fundacional de series)
==========================================================================
TimesFM es el modelo fundacional de series temporales de Google: viene
preentrenado sobre cientos de miles de millones de puntos y predice una serie
que nunca vio, sin entrenarlo. Acá compite como un modelo más dentro del
backtest de `kobra/proyeccion.py` — y si no le gana al ingenuo estacional en
el holdout, no se usa.

Por qué vive aparte y es opcional
---------------------------------
* **Pesa 925 MB** y necesita PyTorch (otros ~200 MB). El instalador entero de
  MV Kobra AI pesa 270 MB: meterlo adentro lo cuadruplicaría para una función
  que en muchas carteras no va a mejorar nada.
* **El programa instalado no tiene internet** —es una de las respuestas al
  área de seguridad del cliente (ver `docs/MODOS_INSTALACION.md`)— así que
  bajar pesos en el primer arranque no es una opción. Acá NUNCA se descarga
  nada salvo que se pida explícitamente.
* Si el paquete no está, `disponible()` devuelve False y el resto del
  programa funciona igual, con los baselines.

La licencia importa, y no es un detalle
---------------------------------------
El código de TimesFM es Apache-2.0, pero **los pesos de la versión 3.0 se
publican bajo una licencia no comercial** que prohíbe explícitamente el uso en
producción. MV Kobra AI se vende: usar esos pesos sería incumplirla.

Los pesos de la **2.5 siguen siendo Apache-2.0**, así que es la única versión
que este adaptador carga, y está fijada en `REPO_25`. No es una preferencia
técnica: es la diferencia entre poder vender el producto y no poder.
"""
from __future__ import annotations

import os

import numpy as np

# Pesos Apache-2.0. NO cambiar a 3.0 sin resolver antes la licencia: los pesos
# de 3.0 son `timesfm-non-commercial-license-v1.0`, prohibidos en producción.
REPO_25 = "google/timesfm-2.5-200m-pytorch"
LICENCIA_PESOS = "Apache-2.0"

# Contexto que se le pasa al modelo. 512 días son casi dos años de historia
# diaria: más contexto no aporta en una cartera y multiplica el tiempo por
# ventana del backtest.
CONTEXTO = 512
HORIZONTE_MAX = 64

_MODELO = None


def _ruta_local() -> str | None:
    """Carpeta con los pesos ya bajados, si la hay.

    `KOBRA_TIMESFM_DIR` es la vía soportada para una instalación sin internet:
    se bajan los pesos una vez en una máquina con red y se copia la carpeta.
    """
    ruta = os.environ.get("KOBRA_TIMESFM_DIR")
    return ruta if ruta and os.path.isdir(ruta) else None


def disponible(permitir_descarga: bool = False) -> bool:
    """¿Se puede usar TimesFM en esta máquina, ahora, sin sorpresas?

    Sin `permitir_descarga` hace falta que los pesos ya estén en disco: pedir
    925 MB por la red mientras alguien mira una pantalla no es un detalle de
    implementación, es un cuelgue de dos minutos.
    """
    try:
        import timesfm  # noqa: F401
    except Exception:
        return False
    return bool(_ruta_local()) or permitir_descarga


def cargar(permitir_descarga: bool = False, horizonte: int = HORIZONTE_MAX):
    """Carga el modelo una sola vez por proceso (tarda ~10 s)."""
    global _MODELO
    if _MODELO is not None:
        return _MODELO
    if not disponible(permitir_descarga):
        return None
    import timesfm
    origen = _ruta_local() or REPO_25
    modelo = timesfm.TimesFM_2p5_200M_torch.from_pretrained(origen)
    modelo.compile(timesfm.ForecastConfig(
        max_context=CONTEXTO, max_horizon=horizonte,
        normalize_inputs=True, use_continuous_quantile_head=True))
    _MODELO = modelo
    return _MODELO


def predictor(permitir_descarga: bool = False, horizonte: int = HORIZONTE_MAX):
    """Devuelve un modelo con la firma que espera `proyeccion.comparar()`.

    `None` si TimesFM no está: el llamador sigue con los baselines en vez de
    romperse, que es la única forma de que una dependencia opcional sea de
    verdad opcional.
    """
    modelo = cargar(permitir_descarga, horizonte)
    if modelo is None:
        return None

    def _predecir(historia: np.ndarray, n: int) -> np.ndarray:
        contexto = np.asarray(historia[-CONTEXTO:], dtype="float32")
        punto, _ = modelo.forecast(horizon=n, inputs=[contexto.tolist()])
        return np.asarray(punto[0][:n], dtype="float64")

    return _predecir
