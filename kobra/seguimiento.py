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
    g["_fecha_compromiso"] = g["fecha_compromiso"].map(_a_fecha)
    g["_fecha_pago"] = g["fecha_pago"].map(_a_fecha)

    pendientes = []
    for id_deudor, grupo in g.groupby("id_deudor"):
        pagos = grupo[grupo["resultado"] == "Pago"]
        fecha_ultimo_pago = pagos["_fecha_gestion"].max() if not pagos.empty else None

        compromisos = grupo[grupo["resultado"].isin(RESULTADOS_CON_COMPROMISO)
                            & grupo["_fecha_compromiso"].notna()]
        if compromisos.empty:
            continue
        ultimo = compromisos.sort_values("_fecha_gestion").iloc[-1]

        vencida = ultimo["_fecha_compromiso"] < hoy
        pago_directo = ultimo["_fecha_pago"] is not None
        pago_posterior = (fecha_ultimo_pago is not None
                         and pd.notna(fecha_ultimo_pago)
                         and fecha_ultimo_pago >= ultimo["_fecha_gestion"])
        if vencida and not pago_directo and not pago_posterior:
            pendientes.append({
                "id_deudor": id_deudor,
                "fecha_gestion": ultimo["fecha_gestion"],
                "fecha_compromiso": ultimo["_fecha_compromiso"],
                "dias_vencida": (hoy - ultimo["_fecha_compromiso"]).days,
                "monto_acordado": ultimo.get("monto_acordado"),
                "cuotas": ultimo.get("cuotas"),
                "canal": ultimo.get("canal"),
                "gestor": ultimo.get("gestor"),
                "resultado": ultimo.get("resultado"),
                "notas": ultimo.get("notas"),
            })

    out = pd.DataFrame(pendientes, columns=cols_out)
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
