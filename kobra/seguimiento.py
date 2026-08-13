# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Agenda y seguimiento de promesas de pago
=======================================================
Cierra el círculo después de una negociación con resultado "Promesa de
pago" o "Arreglo de pago": detecta cuándo la fecha comprometida venció sin
que se haya registrado el pago correspondiente, y arma la **agenda del
día** —a quién re-contactar y por qué— respetando la política de
cumplimiento (horario, feriados, topes de frecuencia, lista de No
Contactar).

No es un canal de contacto nuevo: la agenda solo dice A QUIÉN y POR QUÉ
recontactar. El contacto real sigue pasando por el Gestor IA (llamada/
WhatsApp) o por un humano, igual que cualquier otra gestión — y vuelve a
quedar registrado con `kobra.registro.registrar_gestion` como siempre.
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd

RESULTADOS_CON_COMPROMISO = ("Promesa", "Arreglo de pago")


def _a_fecha(v) -> date | None:
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return None
    try:
        return pd.to_datetime(v).date()
    except Exception:
        return None


def promesas_incumplidas(gestiones: pd.DataFrame, hoy: date | None = None) -> pd.DataFrame:
    """
    Una fila por deudor con la promesa/arreglo de pago MÁS RECIENTE cuya
    `fecha_compromiso` ya venció sin un "Pago" registrado después (ni en la
    misma fila vía `fecha_pago`, ni en una gestión posterior).

    Columnas devueltas: id_deudor, fecha_gestion, fecha_compromiso,
    dias_vencida, monto_acordado, cuotas, canal, gestor, resultado, notas.
    """
    hoy = hoy or date.today()
    cols_out = ["id_deudor", "fecha_gestion", "fecha_compromiso", "dias_vencida",
               "monto_acordado", "cuotas", "canal", "gestor", "resultado", "notas"]
    if gestiones is None or gestiones.empty:
        return pd.DataFrame(columns=cols_out)

    g = gestiones.copy()
    g["_fecha_gestion"] = pd.to_datetime(g["fecha_gestion"], errors="coerce")
    # Vectorizado a proposito: .map(_a_fecha) llamaba pd.to_datetime() por
    # celda y tardaba ~14 s con la cartera de demo (la Agenda parecia colgada).
    # .dt.date deja date en las filas validas y NaT en las invalidas — las
    # de compromiso se filtran con .notna() y las de pago se chequean con
    # pd.notna() abajo, misma semantica que _a_fecha.
    g["_fecha_compromiso"] = pd.to_datetime(g["fecha_compromiso"], errors="coerce").dt.date
    g["_fecha_pago"] = pd.to_datetime(g["fecha_pago"], errors="coerce").dt.date

    # Vectorizado a proposito: el loop original por deudor (5.000+ grupos con
    # filtros booleanos y sort por grupo) tardaba ~13 s con la cartera de demo
    # y la Agenda parecia colgada. Misma semantica, en ~0.1 s.

    # Ultimo compromiso (Promesa/Arreglo con fecha valida) por deudor — sort
    # estable por _fecha_gestion + tail(1) == sort_values(...).iloc[-1] del loop.
    comp = g[g["resultado"].isin(RESULTADOS_CON_COMPROMISO)
             & g["_fecha_compromiso"].notna()]
    comp = comp.sort_values("_fecha_gestion").groupby("id_deudor").tail(1)

    # Fecha del ultimo "Pago" registrado por deudor (cualquier gestion).
    pagos = (g[g["resultado"] == "Pago"]
             .groupby("id_deudor")["_fecha_gestion"].max().rename("_ultimo_pago"))
    comp = comp.merge(pagos, left_on="id_deudor", right_index=True, how="left")

    vencida = comp["_fecha_compromiso"] < hoy
    pago_directo = comp["_fecha_pago"].notna()
    # NaT >= NaT / NaT >= fecha dan False, igual que el chequeo del loop.
    pago_posterior = comp["_ultimo_pago"].notna() & \
        (comp["_ultimo_pago"] >= comp["_fecha_gestion"])
    pend = comp[vencida & ~pago_directo & ~pago_posterior]

    out = pd.DataFrame({
        "id_deudor": pend["id_deudor"],
        "fecha_gestion": pend["fecha_gestion"],
        "fecha_compromiso": pend["_fecha_compromiso"],
        "dias_vencida": (pd.Timestamp(hoy) -
                         pd.to_datetime(pend["_fecha_compromiso"])).dt.days,
        "monto_acordado": pend.get("monto_acordado"),
        "cuotas": pend.get("cuotas"),
        "canal": pend.get("canal"),
        "gestor": pend.get("gestor"),
        "resultado": pend.get("resultado"),
        "notas": pend.get("notas"),
    }).reset_index(drop=True) if not pend.empty else pd.DataFrame(columns=cols_out)
    if not out.empty:
        out = out.sort_values("dias_vencida", ascending=False).reset_index(drop=True)
    return out


def agenda_hoy(gestiones: pd.DataFrame, hoy: date | None = None,
              canal: str = "Llamada", politica=None,
              contactos_previos_por_deudor: dict | None = None,
              archivo_dnc: str | None = None) -> pd.DataFrame:
    """
    `promesas_incumplidas` filtrada por la política de cumplimiento vigente
    (horario/feriados/topes/no-contactar) — agrega `contactable` (bool) y
    `motivo_bloqueo` para que la agenda muestre solo (o marque) lo que HOY
    se puede contactar de verdad.

    `archivo_dnc` (default `None`) se resuelve a `kcump.NO_CONTACTAR_CSV`
    **leído en el momento de la llamada** (no como default del parámetro):
    así un test puede monkeypatchear `cumplimiento.NO_CONTACTAR_CSV` y que
    se respete, en vez de quedar atado al valor de cuando se importó el
    módulo (mismo criterio que ya se documentó para `auditoria.registrar`).
    """
    from kobra import cumplimiento as kcump

    hoy = hoy or date.today()
    df = promesas_incumplidas(gestiones, hoy)
    if df.empty:
        return df.assign(contactable=pd.Series(dtype=bool), motivo_bloqueo=pd.Series(dtype=object))

    ahora = datetime.combine(hoy, datetime.min.time()).replace(hour=10)
    contactos_previos_por_deudor = contactos_previos_por_deudor or {}
    dnc = archivo_dnc if archivo_dnc is not None else kcump.NO_CONTACTAR_CSV

    decisiones = [
        kcump.puede_contactar(d, canal=canal, ahora=ahora,
                             contactos_previos=contactos_previos_por_deudor.get(d, []),
                             politica=politica, archivo_dnc=dnc)
        for d in df["id_deudor"]
    ]
    df = df.copy()
    df["contactable"] = [bool(d) for d in decisiones]
    df["motivo_bloqueo"] = [None if d else d.motivo for d in decisiones]
    return df
