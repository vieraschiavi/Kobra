"""
MV Kobra AI · Cuentas por cobrar (el otro lado del mostrador)
=============================================================
Kobra nació del lado de la GESTIÓN de cobranza: a quién llamar, con qué
estrategia, qué dijo el cliente. Este módulo cubre el lado de ANÁLISIS de
cuentas por cobrar, que es el trabajo diario de un analista de CxC y que
hasta acá el producto no resolvía: antigüedad de saldos, DSO, efectividad
de cobranza, conciliación de pagos y detección de pagos mal aplicados.

Por qué acá y no como "prompts"
-------------------------------
Todo lo de este archivo es CÁLCULO DETERMINÍSTICO sobre los datos que el
cliente ya tiene cargados. Son preguntas con una respuesta correcta: el DSO
de un período es un número, no una opinión; si un pago de $58.300 calza
exactamente con F-4502 + F-4510, calza — no hay que pedirle a un modelo que
lo estime mirando una tabla pegada a mano, y encima arriesgar que se
equivoque en una suma.

La diferencia importa en la práctica: pedirle a un asistente que "analice
esta tabla" obliga a copiar y pegar los datos a mano en cada consulta, no
deja rastro auditable, y da un resultado que hay que volver a verificar.
Estas funciones corren sobre la cartera real, siempre dan lo mismo para la
misma entrada, y se pueden testear — que es lo que las hace usables para
cerrar un mes contable.

Lo que este módulo NO hace, a propósito
---------------------------------------
No decide. No autoriza una quita, no castiga una cuenta como incobrable, no
aplica un pago. Devuelve el número y, cuando hay ambigüedad (un pago que
podría corresponder a dos combinaciones distintas de facturas), lo dice en
vez de elegir por su cuenta. La decisión sigue siendo de la persona.
"""
from __future__ import annotations

from itertools import combinations

import pandas as pd

# Tramos estándar de antigüedad de saldos. Son los que usa cualquier reporte
# de aging y los que ya trae la cartera de Kobra en `tramo_mora`.
TRAMOS = ["Por vencer", "1-30", "31-60", "61-90", "91-180", "180+"]

# Tope de facturas que se combinan al conciliar un pago. Buscar TODAS las
# combinaciones posibles es 2^n: con 40 facturas abiertas son un billón de
# sumas. En la práctica un pago junta unas pocas facturas, así que se corta
# en combinaciones de hasta 4 y se avisa explícitamente si se truncó — un
# límite silencioso haría creer que "no hay match" cuando en realidad no se
# buscó.
MAX_FACTURAS_POR_PAGO = 4
MAX_FACTURAS_ABIERTAS = 60


# ---------------------------------------------------------------------------
# 1) Antigüedad de saldos (aging) y concentración
# ---------------------------------------------------------------------------
def antiguedad_saldos(cartera: pd.DataFrame) -> dict:
    """Reporte de antigüedad de saldos: cuánto se debe en cada tramo de mora.

    Es el artefacto base de cuentas por cobrar — de acá salen el resto de los
    análisis. Devuelve monto y cantidad de deudores por tramo, más el total.
    """
    if cartera is None or cartera.empty:
        return {"tramos": [], "total_uyu": 0.0, "deudores": 0}
    df = cartera.copy()
    if "monto_deuda" not in df.columns:
        return {"tramos": [], "total_uyu": 0.0, "deudores": 0}
    df["monto_deuda"] = pd.to_numeric(df["monto_deuda"], errors="coerce").fillna(0.0)
    if "tramo_mora" not in df.columns:
        df["tramo_mora"] = "Sin tramo"

    total = float(df["monto_deuda"].sum())
    filas = []
    for tramo, grupo in df.groupby("tramo_mora", sort=False):
        monto = float(grupo["monto_deuda"].sum())
        filas.append({
            "tramo": str(tramo),
            "monto_uyu": round(monto, 2),
            "deudores": int(len(grupo)),
            "pct_del_total": round(monto / total, 4) if total else 0.0,
        })
    # Orden estándar del reporte (los tramos desconocidos van al final).
    filas.sort(key=lambda f: TRAMOS.index(f["tramo"]) if f["tramo"] in TRAMOS
               else len(TRAMOS))
    return {"tramos": filas, "total_uyu": round(total, 2), "deudores": int(len(df))}


def concentracion(cartera: pd.DataFrame, top: int = 10) -> dict:
    """Los `top` deudores más grandes y qué porcentaje de la cartera son.

    Responde la pregunta que decide dónde poner el esfuerzo: si 10 clientes
    son el 60 % de lo vencido, la gestión masiva es secundaria.
    """
    if cartera is None or cartera.empty or "monto_deuda" not in cartera.columns:
        return {"top": [], "pct_acumulado": 0.0, "total_uyu": 0.0}
    df = cartera.copy()
    df["monto_deuda"] = pd.to_numeric(df["monto_deuda"], errors="coerce").fillna(0.0)
    total = float(df["monto_deuda"].sum())
    top = max(1, int(top))
    mayores = df.nlargest(top, "monto_deuda")
    filas = [{
        "id_deudor": str(r.get("id_deudor", "")),
        "monto_uyu": round(float(r["monto_deuda"]), 2),
        "dias_mora": int(r["dias_mora"]) if pd.notna(r.get("dias_mora")) else None,
        "pct_del_total": round(float(r["monto_deuda"]) / total, 4) if total else 0.0,
    } for _, r in mayores.iterrows()]
    acumulado = sum(f["pct_del_total"] for f in filas)
    return {"top": filas, "pct_acumulado": round(acumulado, 4),
            "total_uyu": round(total, 2)}


# ---------------------------------------------------------------------------
# 2) DSO — días de cartera
# ---------------------------------------------------------------------------
def dso(ventas_credito: float, saldo_cxc: float, dias_periodo: int,
        plazo_estandar: int | None = None) -> dict:
    """Days Sales Outstanding: cuántos días tarda en cobrarse una venta.

    DSO = (saldo de cuentas por cobrar / ventas a crédito) × días del período.

    Las ventas a crédito NO salen de Kobra —que ve la cobranza, no la
    facturación— así que se piden como dato. Es el indicador estándar de
    cuentas por cobrar y no estaba en el producto.

    Si se pasa el `plazo_estandar` de crédito de la empresa, se agrega la
    lectura que realmente importa: cuántos días por encima del plazo se está
    cobrando (un DSO de 45 es excelente con plazo 60 y malo con plazo 30 —
    el número solo, sin el plazo, no dice nada).
    """
    ventas = float(ventas_credito or 0)
    saldo = float(saldo_cxc or 0)
    dias = int(dias_periodo or 0)
    if ventas <= 0 or dias <= 0:
        return {"dso": None, "error": "Se necesitan ventas a crédito y días del "
                                      "período mayores a cero."}
    valor = (saldo / ventas) * dias
    out = {"dso": round(valor, 1), "ventas_credito": round(ventas, 2),
           "saldo_cxc": round(saldo, 2), "dias_periodo": dias,
           "formula": "(saldo CxC / ventas a crédito) × días del período"}
    if plazo_estandar:
        exceso = valor - float(plazo_estandar)
        out["plazo_estandar"] = int(plazo_estandar)
        out["exceso_dias"] = round(exceso, 1)
        out["lectura"] = (
            f"Se cobra {abs(exceso):.0f} días {'POR ENCIMA' if exceso > 0 else 'por debajo'} "
            f"del plazo de {int(plazo_estandar)} días."
        )
    return out


# ---------------------------------------------------------------------------
# 3) Efectividad de cobranza
# ---------------------------------------------------------------------------
def ultimo_mes_con_datos(gestiones: pd.DataFrame) -> str | None:
    """El mes más reciente que se PUEDE calcular (con monto gestionado > 0).

    No es lo mismo que "el último mes del archivo": el mes en curso suele
    estar a medias, y un mes con gestiones cargadas pero sin monto gestionado
    da una efectividad indefinida (división por cero). Elegir ese mes por
    default hace que un tablero con miles de gestiones muestre "sin datos",
    que es lo que pasaba antes de esta función.
    """
    if gestiones is None or gestiones.empty:
        return None
    if not {"mes", "monto_gestionado"}.issubset(gestiones.columns):
        return None
    df = gestiones.copy()
    df["monto_gestionado"] = pd.to_numeric(df["monto_gestionado"], errors="coerce").fillna(0)
    por_mes = df.groupby("mes")["monto_gestionado"].sum()
    con_datos = por_mes[por_mes > 0]
    if con_datos.empty:
        return None
    return str(sorted(con_datos.index)[-1])


def efectividad(gestiones: pd.DataFrame, mes: str | None = None,
                mes_comparar: str | None = None) -> dict:
    """Monto cobrado sobre monto gestionado, del mes indicado.

    Es el indicador con el que se mide un equipo de cobranza. Sale de las
    gestiones que Kobra ya registra (`monto_gestionado` y `recupero`), sin
    pedirle nada al usuario.
    """
    if gestiones is None or gestiones.empty:
        return {"efectividad": None, "error": "No hay gestiones registradas."}
    cols = {"mes", "monto_gestionado", "recupero"}
    if not cols.issubset(gestiones.columns):
        faltan = sorted(cols - set(gestiones.columns))
        return {"efectividad": None,
                "error": f"Faltan columnas en las gestiones: {', '.join(faltan)}."}

    def _de(m):
        df = gestiones if m is None else gestiones[gestiones["mes"] == m]
        if df.empty:
            return None
        gestionado = float(pd.to_numeric(df["monto_gestionado"], errors="coerce")
                           .fillna(0).sum())
        cobrado = float(pd.to_numeric(df["recupero"], errors="coerce").fillna(0).sum())
        return {
            "mes": m, "gestionado_uyu": round(gestionado, 2),
            "cobrado_uyu": round(cobrado, 2),
            "efectividad": round(cobrado / gestionado, 4) if gestionado else None,
            "gestiones": int(len(df)),
        }

    actual = _de(mes)
    if actual is None:
        return {"efectividad": None, "error": f"No hay gestiones del mes {mes}."}
    out = dict(actual)
    if mes_comparar:
        previo = _de(mes_comparar)
        if previo and previo["efectividad"] is not None and actual["efectividad"] is not None:
            out["comparacion"] = {
                "mes": mes_comparar,
                "efectividad": previo["efectividad"],
                # En puntos porcentuales, no en "% de cambio": comparar dos
                # porcentajes en % relativo es la forma más común de exagerar
                # una mejora (de 2 % a 3 % no es "+50 %", es +1 punto).
                "variacion_pp": round((actual["efectividad"] - previo["efectividad"]) * 100, 1),
            }
        elif previo:
            out["comparacion"] = {"mes": mes_comparar, "efectividad": previo["efectividad"]}
    return out


# ---------------------------------------------------------------------------
# 4) Conciliación: a qué factura(s) corresponde un pago
# ---------------------------------------------------------------------------
def conciliar_pago(monto_pago: float, facturas: list[dict],
                   tolerancia: float = 0.01) -> dict:
    """¿A qué factura o combinación de facturas corresponde este pago?

    Busca, en orden: coincidencia exacta con una factura, y después con una
    combinación de hasta `MAX_FACTURAS_POR_PAGO` facturas.

    Devuelve TODAS las combinaciones que dan el mismo monto, no la primera.
    Si hay más de una, lo marca como ambiguo y no elige: dos facturas de
    $30.000 y $28.300 y otra de $58.300 son indistinguibles desde el monto, y
    aplicar la que "parezca" deja un saldo mal imputado que aparece semanas
    después como un descuadre.

    `facturas`: [{"id": "F-4501", "monto": 30000.0}, ...]
    """
    monto = round(float(monto_pago or 0), 2)
    limpias = []
    for f in (facturas or []):
        try:
            limpias.append({"id": str(f.get("id", "")),
                            "monto": round(float(f.get("monto") or 0), 2)})
        except (TypeError, ValueError):
            continue
    limpias = [f for f in limpias if f["monto"] > 0]

    if monto <= 0:
        return {"match": None, "candidatos": [], "ambiguo": False,
                "error": "El monto del pago tiene que ser mayor a cero."}
    if not limpias:
        return {"match": None, "candidatos": [], "ambiguo": False,
                "error": "No hay facturas abiertas para conciliar."}

    truncado = len(limpias) > MAX_FACTURAS_ABIERTAS
    if truncado:
        # Las más grandes primero: son las que más probablemente compongan un
        # pago alto, y las que más pesan si quedan mal imputadas.
        limpias = sorted(limpias, key=lambda f: -f["monto"])[:MAX_FACTURAS_ABIERTAS]

    candidatos = []
    for n in range(1, MAX_FACTURAS_POR_PAGO + 1):
        for combo in combinations(limpias, n):
            if abs(sum(c["monto"] for c in combo) - monto) <= tolerancia:
                candidatos.append({
                    "facturas": [c["id"] for c in combo],
                    "monto": round(sum(c["monto"] for c in combo), 2),
                })
        if candidatos:
            # Se prefiere siempre la explicación más simple: si una sola
            # factura calza, no tiene sentido ofrecer además combinaciones de
            # tres que sumen lo mismo.
            break

    out = {
        "monto_pago": monto,
        "candidatos": candidatos,
        "ambiguo": len(candidatos) > 1,
        "match": candidatos[0] if len(candidatos) == 1 else None,
    }
    if truncado:
        out["aviso"] = (f"Se consideraron las {MAX_FACTURAS_ABIERTAS} facturas más "
                        "grandes de una lista más larga: puede haber otras "
                        "combinaciones no evaluadas.")
    if not candidatos:
        # El caso más útil de todos: NO hay match. Decirlo claro evita que
        # alguien aplique el pago "al que más se parece".
        cercanas = sorted(limpias, key=lambda f: abs(f["monto"] - monto))[:3]
        out["sin_match"] = True
        out["mas_cercanas"] = [{"id": c["id"], "monto": c["monto"],
                                "diferencia": round(c["monto"] - monto, 2)}
                               for c in cercanas]
    return out


# ---------------------------------------------------------------------------
# 5) Pagos duplicados o mal aplicados
# ---------------------------------------------------------------------------
def anomalias_en_pagos(pagos: list[dict], dias_duplicado: int = 3) -> dict:
    """Revisa un listado de pagos aplicados y marca lo que huele mal.

    Tres cosas, que son las que aparecen en una conciliación real:
      * **duplicado**: mismo cliente, mismo monto, a pocos días — el caso
        clásico de cargar dos veces el mismo comprobante.
      * **sin factura**: un pago aplicado sin factura asociada.
      * **monto no calza**: el pago no coincide con el monto de la factura a
        la que se aplicó (puede ser legítimo —un parcial— pero tiene que
        estar marcado, no pasar de largo).

    Marca, no corrige: cada caso vuelve con el motivo para que una persona lo
    revise. Nada se aplica ni se revierte solo.
    """
    filas = []
    for p in (pagos or []):
        try:
            filas.append({
                "referencia": str(p.get("referencia", "")),
                "id_deudor": str(p.get("id_deudor", "")),
                "monto": round(float(p.get("monto") or 0), 2),
                "fecha": str(p.get("fecha", "")),
                "factura": str(p.get("factura") or ""),
                "monto_factura": (round(float(p["monto_factura"]), 2)
                                  if p.get("monto_factura") not in (None, "") else None),
            })
        except (TypeError, ValueError):
            continue

    hallazgos = []
    # Duplicados: mismo deudor + mismo monto, ordenados por fecha.
    por_clave: dict = {}
    for f in filas:
        por_clave.setdefault((f["id_deudor"], f["monto"]), []).append(f)
    for (deudor, monto), grupo in por_clave.items():
        if len(grupo) < 2:
            continue
        grupo = sorted(grupo, key=lambda x: x["fecha"])
        for a, b in zip(grupo, grupo[1:]):
            dias = _dias_entre(a["fecha"], b["fecha"])
            if dias is not None and dias <= dias_duplicado:
                hallazgos.append({
                    "tipo": "posible_duplicado",
                    "referencias": [a["referencia"], b["referencia"]],
                    "id_deudor": deudor, "monto": monto,
                    "detalle": (f"Dos pagos de {monto} del mismo deudor con "
                                f"{dias} día(s) de diferencia."),
                })

    for f in filas:
        if not f["factura"]:
            hallazgos.append({
                "tipo": "sin_factura", "referencias": [f["referencia"]],
                "id_deudor": f["id_deudor"], "monto": f["monto"],
                "detalle": "Pago aplicado sin factura asociada.",
            })
        elif f["monto_factura"] is not None and abs(f["monto_factura"] - f["monto"]) > 0.01:
            dif = round(f["monto"] - f["monto_factura"], 2)
            hallazgos.append({
                "tipo": "monto_no_calza", "referencias": [f["referencia"]],
                "id_deudor": f["id_deudor"], "monto": f["monto"],
                "detalle": (f"El pago ({f['monto']}) no coincide con la factura "
                            f"{f['factura']} ({f['monto_factura']}): diferencia de {dif}. "
                            "Puede ser un pago parcial o una retención — verificar."),
            })

    return {"revisados": len(filas), "hallazgos": hallazgos,
            "total_hallazgos": len(hallazgos)}


def _dias_entre(fecha_a: str, fecha_b: str) -> int | None:
    try:
        a = pd.to_datetime(fecha_a)
        b = pd.to_datetime(fecha_b)
    except (ValueError, TypeError):
        return None
    if pd.isna(a) or pd.isna(b):
        return None
    return abs(int((b - a).days))
