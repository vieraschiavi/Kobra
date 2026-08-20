# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Gestión de proyectos
==================================
Módulo de la suite, se vende aparte (`plan.exigir("proyectos")`). Portado del
motor de MV Project Management (`mvpm/health.py` + `mvpm/prioritizer.py`).

Dos cosas, las dos con motor de reglas determinístico y **sin depender de IA**:

  1. **Salud del portafolio** en seis dimensiones — alcance, cronograma,
     presupuesto, riesgo, dependencias y equipo.
  2. **Backlog priorizado por valor esperado** — impacto × urgencia × riesgo,
     en vez de por orden de llegada o por quién insiste más.

Por qué sin IA
---------------
Un índice de salud tiene que dar lo mismo hoy que mañana con los mismos datos,
y tiene que poder explicarse frente a un directorio: "este proyecto está en
rojo porque el 40% de sus tareas está vencida" se discute; "el modelo dice 42"
no. La IA sirve para redactar la recomendación, no para calcular el número.

Cambio respecto del original
-----------------------------
El motor de origen tenía la fecha de hoy **fija en el código**
(`_TODAY = datetime(2026, 7, 12)`). Para su demo alcanzaba, pero portado tal
cual el cronograma quedaría congelado: al día siguiente ninguna tarea vencería
y el índice de salud dejaría de moverse. Acá la fecha se toma del reloj, y se
puede inyectar en los tests — que es lo que un test necesita, sin obligar al
producto a vivir en una fecha inventada.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

DIMENSIONES = ("alcance", "cronograma", "presupuesto", "riesgo",
               "dependencias", "equipo")

# Umbrales del semáforo. Un proyecto en "observación" todavía se endereza; en
# "riesgo" ya necesita una decisión, no más seguimiento.
UMBRAL_RIESGO = 55
UMBRAL_OBSERVACION = 75

# Pesos del valor esperado. Un proyecto crítico pesa más que uno que no lo es,
# y una tarea de prioridad alta más que una baja — pero ninguno de los dos
# alcanza para tapar la urgencia de algo ya vencido.
PESO_CRITICIDAD = {"Alta": 1.4, "Media": 1.0, "Baja": 0.6}
PESO_PRIORIDAD = {"Alta": 1.3, "Media": 1.0, "Baja": 0.7}

COLUMNAS_PROYECTOS = ("proyecto_id", "nombre")
COLUMNAS_TAREAS = ("tarea_id", "proyecto_id", "estado")

ESTADOS_PENDIENTES = ("todo", "in_progress", "blocked")


class DatosIncompletos(ValueError):
    """Falta una columna necesaria. El mensaje nombra cuál y en qué tabla."""


def _exigir(df: pd.DataFrame, columnas, tabla: str) -> None:
    faltan = [c for c in columnas if c not in df.columns]
    if faltan:
        raise DatosIncompletos(
            f"A la tabla de {tabla} le faltan columnas: {', '.join(faltan)}. "
            f"Se necesitan: {', '.join(columnas)}.")


def _ahora(hoy: datetime | None = None) -> datetime:
    return hoy if hoy is not None else datetime.now()


# ---------------------------------------------------------------------------
# Las seis dimensiones de salud
# ---------------------------------------------------------------------------
# Cada una devuelve 0-100. Los multiplicadores (140, 200, 260…) están calibrados
# para que una proporción chica de problemas ya mueva la aguja: si el 20% de las
# tareas está vencida, el cronograma no puede dar 80 — dar 80 sería un tablero
# que tranquiliza mientras el proyecto se cae, que es peor que no tener tablero.
def _puntaje_cronograma(tareas: pd.DataFrame, hoy: datetime) -> float:
    if tareas.empty or "vencimiento" not in tareas.columns:
        return 100.0
    vence = pd.to_datetime(tareas["vencimiento"], errors="coerce")
    vencidas = ((vence < hoy) & (tareas["estado"] != "done")).sum()
    return max(0.0, 100.0 - (vencidas / len(tareas)) * 140)


def _puntaje_presupuesto(proyecto: pd.Series) -> float:
    """Se empieza a descontar al 85% de ejecución, no al 100%.

    Cuando un proyecto llega al 100% del presupuesto ya es tarde para
    reaccionar: la alerta tiene que sonar mientras todavía queda margen.
    """
    presupuesto = proyecto.get("presupuesto") or 0
    if not presupuesto:
        return 100.0
    pct = (proyecto.get("ejecutado") or 0) / presupuesto
    if pct <= 1.0:
        return 100.0 - max(0.0, pct - 0.85) * 200
    return max(0.0, 100.0 - (pct - 1.0) * 250)


def _puntaje_riesgo(tareas: pd.DataFrame) -> float:
    if tareas.empty:
        return 100.0
    bloqueadas = (tareas["estado"] == "blocked").sum()
    return max(0.0, 100.0 - (bloqueadas / len(tareas)) * 260)


def _puntaje_dependencias(tareas: pd.DataFrame, ids_validos: set) -> float:
    """Penaliza las dependencias que apuntan a una tarea que no existe.

    Es el síntoma de un plan que quedó viejo: alguien borró o renombró una
    tarea y las que dependían de ella quedaron colgando. El cronograma sigue
    calculando como si la cadena estuviera entera.
    """
    if "depende_de" not in tareas.columns:
        return 100.0
    deps = tareas["depende_de"].dropna()
    if deps.empty:
        return 100.0
    huerfanas = sum(1 for d in deps if d not in ids_validos)
    return max(0.0, 100.0 - (huerfanas / len(deps)) * 100)


def _puntaje_alcance(tareas: pd.DataFrame) -> float:
    """Tareas sin responsable: nadie las va a hacer, y nadie va a avisar."""
    if tareas.empty or "responsable" not in tareas.columns:
        return 100.0
    sin_dueno = tareas["responsable"].isna().sum()
    return max(0.0, 100.0 - (sin_dueno / len(tareas)) * 130)


def _puntaje_equipo(dueno, equipo: pd.DataFrame) -> float:
    """Sobrecarga del responsable del proyecto.

    Un proyecto sin dueño arranca en 55 —ni bien ni mal, sin información— en
    vez de 100: dar 100 diría que está sano justo por no tener a nadie a cargo.
    """
    if dueno is None or (isinstance(dueno, float) and pd.isna(dueno)):
        return 55.0
    if equipo is None or equipo.empty or "nombre" not in equipo.columns:
        return 80.0
    fila = equipo[equipo["nombre"] == dueno]
    if fila.empty:
        return 80.0
    r = fila.iloc[0]
    capacidad = r.get("capacidad_semanal_hs") or 0
    if not capacidad:
        return 80.0
    sobrecarga = max(0.0, (r.get("carga_actual_hs", 0) - capacidad) / capacidad)
    return max(0.0, 100.0 - sobrecarga * 180)


def salud(proyectos: pd.DataFrame, tareas: pd.DataFrame,
          equipo: pd.DataFrame | None = None,
          hoy: datetime | None = None) -> pd.DataFrame:
    """Índice de salud por proyecto, con el detalle de cada dimensión.

    Devuelve el desglose y no solo el índice a propósito: un número solo se
    discute, un desglose se acciona — dice qué arreglar.
    """
    _exigir(proyectos, COLUMNAS_PROYECTOS, "proyectos")
    _exigir(tareas, COLUMNAS_TAREAS, "tareas")
    hoy = _ahora(hoy)
    equipo = equipo if equipo is not None else pd.DataFrame()
    ids_validos = set(tareas["tarea_id"])

    filas = []
    for _, p in proyectos.iterrows():
        suyas = tareas[tareas["proyecto_id"] == p["proyecto_id"]]
        puntajes = {
            "alcance": _puntaje_alcance(suyas),
            "cronograma": _puntaje_cronograma(suyas, hoy),
            "presupuesto": _puntaje_presupuesto(p),
            "riesgo": _puntaje_riesgo(suyas),
            "dependencias": _puntaje_dependencias(suyas, ids_validos),
            "equipo": _puntaje_equipo(p.get("dueno"), equipo),
        }
        indice = round(sum(puntajes.values()) / len(puntajes), 1)
        estado = ("riesgo" if indice < UMBRAL_RIESGO
                  else "observacion" if indice < UMBRAL_OBSERVACION
                  else "saludable")
        filas.append({"proyecto_id": p["proyecto_id"], "nombre": p["nombre"],
                      "indice": indice, "estado": estado,
                      **{f"dim_{k}": round(v, 1) for k, v in puntajes.items()}})
    columnas = ["proyecto_id", "nombre", "indice", "estado",
                *[f"dim_{d}" for d in DIMENSIONES]]
    return pd.DataFrame(filas, columns=columnas)


def indice_general(proyectos: pd.DataFrame, tareas: pd.DataFrame,
                   equipo: pd.DataFrame | None = None,
                   hoy: datetime | None = None) -> float:
    df = salud(proyectos, tareas, equipo, hoy)
    return round(float(df["indice"].mean()), 1) if not df.empty else 0.0


# ---------------------------------------------------------------------------
# Backlog priorizado
# ---------------------------------------------------------------------------
def _impacto_dependencias(tarea_id, tareas: pd.DataFrame) -> int:
    """Cuántas tareas se frenan si esta se atrasa, siguiendo la cadena entera.

    Se recorre transitivamente y no un solo salto: lo que decide la prioridad
    real es el tamaño de la cola que quedó esperando, no la primera de ellas.
    """
    if "depende_de" not in tareas.columns:
        return 0
    afectadas, frontera, vistos = set(), [tarea_id], {tarea_id}
    while frontera:
        actual = frontera.pop()
        directas = tareas[tareas["depende_de"] == actual]["tarea_id"].tolist()
        for t in directas:
            if t in vistos:      # un ciclo en el plan no puede colgar el cálculo
                continue
            vistos.add(t)
            afectadas.add(t)
            frontera.append(t)
    return len(afectadas)


def backlog(proyectos: pd.DataFrame, tareas: pd.DataFrame,
            hoy: datetime | None = None) -> pd.DataFrame:
    """Qué hacer primero, por valor esperado.

    Una tarea vencida sube a urgencia 1.6 —por encima del máximo de una que
    todavía tiene plazo— porque el costo del atraso ya se está pagando: no
    compite con las demás, va antes.
    """
    _exigir(proyectos, COLUMNAS_PROYECTOS, "proyectos")
    _exigir(tareas, COLUMNAS_TAREAS, "tareas")
    hoy = _ahora(hoy)

    pendientes = tareas[tareas["estado"].isin(ESTADOS_PENDIENTES)].copy()
    if pendientes.empty:
        return pendientes.assign(valor_esperado=pd.Series(dtype=float),
                                 tareas_impactadas=pd.Series(dtype=int),
                                 dias_restantes=pd.Series(dtype=int))
    por_id = proyectos.set_index("proyecto_id")

    def puntuar(fila):
        if "vencimiento" in fila and pd.notna(fila.get("vencimiento")):
            vence = pd.to_datetime(fila["vencimiento"], errors="coerce")
            dias = (vence - hoy).days if pd.notna(vence) else 999
        else:
            dias = 999
        urgencia = 1.6 if dias < 0 else max(0.3, 1.0 - dias / 90)

        pid = fila["proyecto_id"]
        criticidad = (por_id.loc[pid, "criticidad"]
                      if pid in por_id.index and "criticidad" in por_id.columns
                      else "Media")
        impacto = _impacto_dependencias(fila["tarea_id"], tareas)
        bloqueo = 1.25 if fila["estado"] == "blocked" else 1.0
        valor = (PESO_CRITICIDAD.get(criticidad, 1.0)
                 * PESO_PRIORIDAD.get(fila.get("prioridad"), 1.0)
                 * urgencia * bloqueo * (1 + impacto * 0.15))
        return round(valor, 2), impacto, dias

    puntuadas = pendientes.apply(puntuar, axis=1, result_type="expand")
    pendientes["valor_esperado"] = puntuadas[0]
    pendientes["tareas_impactadas"] = puntuadas[1]
    pendientes["dias_restantes"] = puntuadas[2]
    return (pendientes.sort_values("valor_esperado", ascending=False)
            .reset_index(drop=True))


def resumen(proyectos: pd.DataFrame, tareas: pd.DataFrame,
            equipo: pd.DataFrame | None = None,
            hoy: datetime | None = None, top: int = 10) -> dict:
    """Todo lo que muestra la pantalla, en una sola llamada."""
    s = salud(proyectos, tareas, equipo, hoy)
    b = backlog(proyectos, tareas, hoy)
    return {
        "indice_general": round(float(s["indice"].mean()), 1) if len(s) else 0.0,
        "proyectos": len(s),
        "en_riesgo": int((s["estado"] == "riesgo").sum()),
        "en_observacion": int((s["estado"] == "observacion").sum()),
        "saludables": int((s["estado"] == "saludable").sum()),
        "salud": s,
        "backlog": b.head(top),
        "tareas_pendientes": len(b),
    }
