# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Qué incluye realmente el plan que pagó el cliente
==============================================================
La licencia (`backend_venta/licencias.py`) viaja firmada con tres cosas:
`plan`, `cupo_mensual` y `features`. Hasta acá **la app instalada leía una
sola**: la fecha de vencimiento. O sea que un cliente de Básico (US$99, 300
gestiones/mes en la landing) recibía exactamente el mismo producto que uno de
Pro (US$349, 1.000 gestiones/mes) — lo único distinto entre los dos era cuándo
se les vencía. La diferencia estaba emitida en el token y firmada, pero no la
aplicaba nadie: el único que miraba `cupo_mensual` era `backend_venta/app.py`,
el gateway, que no va dentro del programa que se instala el cliente.

Este módulo es el que la aplica, y es el ÚNICO lugar donde se decide qué
habilita un plan.

Qué cuenta como "gestión"
-------------------------
Lo que la landing vende por mes: **cada acción de cobranza asistida por IA**.
Concretamente, las tres que consumen el motor:

  * una gestión generada por el Agente IA Negociador,
  * el análisis de una llamada (copiloto de voz),
  * la evaluación automática de un audio de gestión.

NO cuenta —y esto es deliberado— nada de lo que el cliente hace con **sus
propios datos**: mirar el dashboard, filtrar la cartera, exportar, imprimir un
informe. Un cupo que se agota no puede dejar a una empresa sin acceso a su
propia cartera; eso no sería un límite comercial sino un secuestro de datos.

Qué pasa al llegar al tope
--------------------------
  * `cupo_mensual = None`  → sin tope (Enterprise, copia del dueño, o cuando
    no hay licencia: correr desde el repo o el modo hosted no se limitan).
  * 80 % del cupo          → aviso en la app, nada se bloquea.
  * 100 % con "excedente"  → se deja pasar y se registra el excedente (Pro y
    Enterprise lo tienen: pagan por lo que se pasen, no se les corta).
  * 100 % sin "excedente"  → se rechaza esa acción con un mensaje que dice
    cuánto es el cupo y dónde se mejora el plan (Trial, Básico, Starter).

Honestidad sobre lo que esto es
-------------------------------
El conteo vive en la carpeta de datos del cliente, o sea que corre en su
máquina y es manipulable por alguien decidido a hacerlo. Es un límite
**comercial**, no una barrera de seguridad — igual que el odómetro de un
alquiler. Lo que sí es infalsificable es la licencia: el cupo y las features
vienen firmadas con HS256 y no se pueden editar sin el secreto.
"""
from __future__ import annotations

import json
import os
import threading
import time

import portalocker

ARCHIVO_USO = "uso_plan.json"

# Porcentaje a partir del cual la app avisa (sin bloquear nada).
UMBRAL_AVISO = 0.8

# Un `threading.Lock` NO alcanza acá: este paquete se abre por DOS vías —
# `app/app.py` (Streamlit) y `webapp/backend/api.py` (FastAPI) — que pueden
# correr como procesos SEPARADOS al mismo tiempo contra el mismo
# `uso_plan.json` (ver `tests/test_plan_diferenciado.py::
# test_el_dashboard_streamlit_tambien_aplica_el_cupo`). Dos gestiones
# disparadas casi juntas desde cada vía leerían el mismo `usado` antes de que
# cualquiera escribiera, y una de las dos se perdería (lost update). El lock
# de threading sigue sirviendo para serializar hilos del mismo proceso —
# barato, sin tocar disco — y encima se toma `portalocker.Lock` sobre un
# archivo `.lock` (mismo patrón que `kobra/registro.py`), que sí sincroniza
# entre procesos y es multiplataforma (Windows incluido, que es donde corre
# la copia instalada).
_LOCK = threading.Lock()

# Cachear los claims por un rato corto: `claims()`/`_es_owner()` terminan
# consultando el keyring del sistema operativo (ver `kobra/config.py`), un
# round-trip de IPC real. Sin caché, una sola request a un endpoint medido
# (que llama `exigir` + `verificar_cupo` + `registrar_gestion`, y cada una
# vuelve a resolver el plan) dispara esa consulta 15-20 veces — cientos de ms
# de latencia por clic que no compran nada, porque el plan no cambia entre
# una llamada y la siguiente a milisegundos de distancia. 2 segundos es corto
# frente a cualquier interacción humana y no introduce staleness relevante
# (activar/desactivar una licencia ya pasa por este mismo módulo y no depende
# de que el caché haya expirado para funcionar la vez siguiente).
_TTL_CACHE_SEG = 2.0
_cache_claims: dict = {"valor": None, "vence": 0.0}
_cache_owner: dict = {"valor": None, "vence": 0.0}


class LimitePlan(Exception):
    """Base de los dos rechazos que puede devolver este módulo."""

    def __init__(self, mensaje: str, estado: dict | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.estado = estado or {}


class FeatureNoIncluida(LimitePlan):
    """El plan contratado no incluye esa capacidad."""


class CupoAgotado(LimitePlan):
    """Se consumió el cupo mensual y el plan no admite excedente."""


# ---------------------------------------------------------------------------
# De dónde sale el plan
# ---------------------------------------------------------------------------
def invalidar_cache() -> None:
    """Se llama al activar/cambiar una licencia u owner: sin esto, el plan
    nuevo podría tardar hasta `_TTL_CACHE_SEG` en verse reflejado."""
    _cache_claims["vence"] = 0.0
    _cache_owner["vence"] = 0.0


def _es_owner() -> bool:
    ahora = time.monotonic()
    if ahora < _cache_owner["vence"]:
        return _cache_owner["valor"]
    from kobra import edicion as kedicion
    valor = kedicion.es_owner()
    _cache_owner["valor"] = valor
    _cache_owner["vence"] = ahora + _TTL_CACHE_SEG
    return valor


def claims() -> dict | None:
    """Los claims de la licencia activa, o None si no hay licencia vigente.

    None NO significa "bloqueado": significa que este programa no está
    gobernado por una licencia (copia del repo, modo hosted, dueño). Inventar
    un tope donde nadie configuró uno rompería el desarrollo y el multi-tenant.
    """
    ahora = time.monotonic()
    if ahora < _cache_claims["vence"]:
        return _cache_claims["valor"]
    valor = _claims_sin_cache()
    _cache_claims["valor"] = valor
    _cache_claims["vence"] = ahora + _TTL_CACHE_SEG
    return valor


def _claims_sin_cache() -> dict | None:
    try:
        from backend_venta import licencias as klicencias
        from kobra import config as kconfig
        from kobra.edicion import CLAVE_TOKEN
    except Exception:
        return None
    token = kconfig.leer_extra(CLAVE_TOKEN)
    if not token:
        return None
    r = klicencias.licencia_activa(token)
    return r["claims"] if r["ok"] else None


def _cliente_id(c: dict | None) -> str:
    return str((c or {}).get("sub") or "sin_licencia")


def features() -> list[str] | None:
    """Features habilitadas, o None cuando no hay plan que aplicar."""
    if _es_owner():
        return None
    c = claims()
    if c is None:
        return None
    feats = c.get("features")
    return list(feats) if isinstance(feats, list) else []


def permite(feature: str) -> bool:
    feats = features()
    return True if feats is None else feature in feats


def exigir(feature: str, nombre_visible: str | None = None) -> None:
    """Corta la acción si el plan no incluye `feature`."""
    if permite(feature):
        return
    que = nombre_visible or feature
    raise FeatureNoIncluida(
        f"Tu plan no incluye {que}. Mejorá tu plan en mvkobranzaia.com para habilitarlo.",
        estado(),
    )


def cupo() -> int | None:
    """Gestiones por mes del plan. None = sin tope."""
    if _es_owner():
        return None
    c = claims()
    if c is None:
        return None
    valor = c.get("cupo_mensual")
    if valor is None:
        return None
    try:
        return max(0, int(valor))
    except (TypeError, ValueError):
        return None


def admite_excedente() -> bool:
    return permite("excedente")


# ---------------------------------------------------------------------------
# Contador mensual
# ---------------------------------------------------------------------------
def _ruta_uso() -> str:
    from kobra import rutas as krutas
    return os.path.join(krutas.DIR_DATOS, ARCHIVO_USO)


def mes_actual() -> str:
    return time.strftime("%Y-%m", time.localtime())


def _leer_uso() -> dict:
    try:
        with open(_ruta_uso(), encoding="utf-8") as f:
            datos = json.load(f)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):
        return {}


def _escribir_uso(datos: dict) -> None:
    """Escritura atómica: un corte de luz a mitad no puede dejar el contador
    en un JSON roto (que se leería como cero y regalaría el cupo del mes)."""
    ruta = _ruta_uso()
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ruta)


def consumo(mes: str | None = None) -> int:
    """Gestiones consumidas por ESTE cliente en el mes indicado.

    El contador se guarda por cliente además de por mes: si una empresa
    activa una licencia nueva (renovó, o cambió de plan a mitad de mes) el
    cupo del plan nuevo arranca limpio en vez de heredar lo gastado con otro.
    """
    c = claims()
    uso = _leer_uso().get(_cliente_id(c), {})
    try:
        return max(0, int(uso.get(mes or mes_actual(), 0)))
    except (TypeError, ValueError):
        return 0


def _bloqueado(usado: int, tope: int) -> bool:
    """¿La próxima gestión se rechaza? Única definición de la regla — antes
    estaba reimplementada por separado en `estado()`, `verificar_cupo()` y
    `registrar_gestion()`, y las tres podían desincronizarse si se tocaba una
    sin acordarse de las otras dos."""
    return usado >= tope and not admite_excedente()


def estado() -> dict:
    """Foto del plan para la app y para la UI."""
    if _es_owner():
        return {"plan": "owner", "ilimitado": True, "cupo": None, "usado": 0,
                "restante": None, "excedente": 0, "avisar": False,
                "bloqueado": False, "features": None, "mes": mes_actual()}
    c = claims()
    tope = cupo()
    usado = consumo()
    feats = features()
    if tope is None:
        return {"plan": (c or {}).get("plan"), "ilimitado": True, "cupo": None,
                "usado": usado, "restante": None, "excedente": 0,
                "avisar": False, "bloqueado": False, "features": feats,
                "mes": mes_actual()}
    restante = max(0, tope - usado)
    excedente = max(0, usado - tope)
    return {
        "plan": (c or {}).get("plan"),
        "ilimitado": False,
        "cupo": tope,
        "usado": usado,
        "restante": restante,
        "excedente": excedente,
        "avisar": tope > 0 and usado >= tope * UMBRAL_AVISO,
        # `bloqueado` es "la próxima gestión se rechaza", no "la app se cerró":
        # el cliente sigue entrando a su cartera, sus informes y sus exports.
        "bloqueado": _bloqueado(usado, tope),
        "features": feats,
        "mes": mes_actual(),
    }


def _rechazo_por_cupo(tope: int, c: dict | None) -> CupoAgotado:
    return CupoAgotado(
        f"Llegaste a las {tope} gestiones de tu plan "
        f"{(c or {}).get('plan') or ''}".strip() +
        " este mes. Mejorá tu plan en mvkobranzaia.com para seguir "
        "gestionando — tu cartera, tus informes y tus exportaciones "
        "siguen disponibles.",
        estado(),
    )


def verificar_cupo() -> None:
    """¿Entra una gestión más? Corta si no, SIN consumir nada.

    Existe separada de `registrar_gestion` porque las acciones caras (analizar
    un audio, correr una negociación entera) se cobran cuando salieron bien:
    conviene rechazar antes de trabajar, y recién sumar cuando hay resultado.
    Un análisis que terminó en error no le puede comer el cupo al cliente.

    Es un chequeo OPTIMISTA, no una garantía dura bajo concurrencia: no toma
    lock ni bloquea a nadie más, así que dos llamadas casi simultáneas pueden
    pasar las dos y disparar el trabajo caro (Whisper, LLM) antes de que
    cualquiera llegue a `registrar_gestion` — que es quien aplica el corte
    real y consistente sobre el contador persistido. El costo de ese trabajo
    de más lo paga el propio cliente con su propia cuenta (OpenAI/Twilio), no
    un tercero: coherente con que esto es un límite comercial, no una barrera
    de seguridad (ver el docstring del módulo).
    """
    if _es_owner():
        return
    tope = cupo()
    if tope is None:
        return
    if _bloqueado(consumo(), tope):
        raise _rechazo_por_cupo(tope, claims())


def registrar_gestion() -> dict:
    """Suma una gestión al mes en curso y devuelve el estado resultante.

    Lanza `CupoAgotado` ANTES de sumar si el plan ya no da para más: cobrarle
    el consumo a alguien a quien se le está negando la acción sería el peor de
    los dos mundos.
    """
    if _es_owner():
        return estado()
    tope = cupo()
    if tope is None:
        return estado()
    ruta = _ruta_uso()
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    with _LOCK, portalocker.Lock(ruta + ".lock", timeout=10):
        c = claims()
        cid = _cliente_id(c)
        mes = mes_actual()
        datos = _leer_uso()
        por_cliente = datos.setdefault(cid, {})
        try:
            usado = max(0, int(por_cliente.get(mes, 0)))
        except (TypeError, ValueError):
            usado = 0
        if _bloqueado(usado, tope):
            raise _rechazo_por_cupo(tope, c)
        por_cliente[mes] = usado + 1
        # Se conservan solo los últimos 12 meses del cliente: el archivo no
        # tiene por qué crecer para siempre, y el historial largo no lo usa
        # nadie acá (facturación real la lleva el gateway).
        if len(por_cliente) > 12:
            for viejo in sorted(por_cliente)[:-12]:
                por_cliente.pop(viejo, None)
        try:
            _escribir_uso(datos)
        except OSError:
            # Carpeta de solo lectura: no se puede contar, pero tampoco se
            # puede dejar sin trabajar a quien pagó. Se deja pasar.
            pass
    return estado()
