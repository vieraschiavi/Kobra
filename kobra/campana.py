# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Campaña de contacto automática (canal + horario + prioridad)
===========================================================================
Orquesta el contacto saliente de la cartera de forma automática:

  1. **Prioridad**: usa `valor_esperado_recupero` / `prioridad` ya calculados
     por el Agente Negociador (`kobra/negociador.py`) sobre la cartera
     scoreada (`outputs/kobra_scored.csv`), y sube la prioridad de quienes
     tienen una promesa/arreglo vencido (`kobra/seguimiento.py`).
  2. **Canal preferido**: a diferencia de `canal_recomendado` (una regla de
     negocio fija sobre el dataset sintético), esto se calcula de verdad a
     partir del **historial real de gestiones de los últimos meses**: el
     canal donde más se contactó (o más cerró, si hay éxitos) a CADA deudor.
  3. **Horario preferido**: la hora del día donde más se lo contactó/cerró
     en el historial — combinado con la política de cumplimiento vigente
     (horario legal, feriados, topes de frecuencia, No Contactar), que
     siempre tiene la última palabra.
  4. **Ejecución**: llamada real (Twilio, ya integrado), WhatsApp saliente
     (Twilio WhatsApp API con plantilla aprobada) o **email** (SMTP
     corporativo del cliente, con plantilla customizable por tramo de mora).

Nada de esto reemplaza la política de cumplimiento: `plan_contacto_hoy`
descarta todo lo que `cumplimiento.puede_contactar` no autorice, sin
excepción.
"""
from __future__ import annotations

import os
from collections import Counter
from datetime import date, datetime, timedelta

import pandas as pd

from kobra import registro as kregistro
from kobra import seguimiento as kseg

VENTANA_HISTORIAL_DIAS = 90
RESULTADOS_EXITOSOS = ("Pago", "Promesa", "Arreglo de pago")

# ---------------------------------------------------------------------------
# Plantillas de email por tramo de mora (customizables por la empresa)
# ---------------------------------------------------------------------------
PLANTILLA_EMAIL_DEFAULT = {
    "1-30": {
        "asunto": "{empresa} · Recordatorio de saldo pendiente",
        "cuerpo": ("Hola,\n\nLe recordamos que tiene un saldo pendiente de $U {monto:,.0f} "
                  "con {dias_mora} días de atraso. Si ya realizó el pago, puede ignorar "
                  "este mensaje.\n\nPara coordinar el pago o consultar opciones, "
                  "contáctenos.\n\nSaludos,\n{empresa}"),
    },
    "31-60": {
        "asunto": "{empresa} · Su saldo pendiente sigue sin regularizar",
        "cuerpo": ("Hola,\n\nSu saldo de $U {monto:,.0f} lleva {dias_mora} días de atraso. "
                  "Ofrecemos planes de pago en cuotas — respondiendo este correo o "
                  "contactándonos podemos coordinar la opción que mejor le sirva.\n\n"
                  "Saludos,\n{empresa}"),
    },
    "61-90": {
        "asunto": "{empresa} · Regularice su saldo pendiente",
        "cuerpo": ("Hola,\n\nSu saldo de $U {monto:,.0f} tiene {dias_mora} días de atraso. "
                  "Le pedimos que se comunique a la brevedad para acordar una forma de "
                  "pago y evitar que la situación avance a instancias posteriores.\n\n"
                  "Saludos,\n{empresa}"),
    },
    "91-180": {
        "asunto": "{empresa} · Atención requerida: saldo con atraso significativo",
        "cuerpo": ("Hola,\n\nSu saldo de $U {monto:,.0f} tiene {dias_mora} días de atraso. "
                  "Es importante que se comunique con nosotros para acordar una solución "
                  "antes de que el caso avance a gestión más formal.\n\nSaludos,\n{empresa}"),
    },
    "180+": {
        "asunto": "{empresa} · Última instancia para regularizar su saldo",
        "cuerpo": ("Hola,\n\nSu saldo de $U {monto:,.0f} tiene {dias_mora} días de atraso, "
                  "en instancia avanzada de gestión. Contáctenos a la brevedad para "
                  "acordar una solución.\n\nSaludos,\n{empresa}"),
    },
}
_CLAVE_PLANTILLAS = "PLANTILLAS_EMAIL_TRAMO"


def obtener_plantillas_email() -> dict:
    """Plantillas activas por tramo de mora: las que la empresa haya
    customizado (guardadas en kconfig) o, si no, las de referencia."""
    from kobra import config as kconfig
    guardadas = kconfig.leer_extra(_CLAVE_PLANTILLAS)
    if guardadas:
        return {**PLANTILLA_EMAIL_DEFAULT, **guardadas}
    return dict(PLANTILLA_EMAIL_DEFAULT)


def guardar_plantilla_email(tramo_mora: str, asunto: str, cuerpo: str) -> None:
    """Customiza la plantilla de un tramo — persiste junto a la config del cliente."""
    from kobra import config as kconfig
    actuales = kconfig.leer_extra(_CLAVE_PLANTILLAS) or {}
    actuales[tramo_mora] = {"asunto": asunto, "cuerpo": cuerpo}
    kconfig.guardar_extra(_CLAVE_PLANTILLAS, actuales)


def renderizar_plantilla(plantilla: dict, contexto: dict) -> tuple[str, str]:
    """(asunto, cuerpo) con los placeholders reemplazados. Placeholders
    faltantes en el contexto no rompen el envío — quedan en blanco."""
    ctx = {"empresa": "MV Kobra AI", "monto": 0.0, "dias_mora": 0, **contexto}
    try:
        asunto = plantilla["asunto"].format(**ctx)
        cuerpo = plantilla["cuerpo"].format(**ctx)
    except (KeyError, IndexError):
        asunto, cuerpo = plantilla["asunto"], plantilla["cuerpo"]
    return asunto, cuerpo


# ---------------------------------------------------------------------------
# 1) Preferencia de canal y horario por historial real (últimos N días)
# ---------------------------------------------------------------------------
def preferencias_contacto(gestiones: pd.DataFrame, hoy: date | None = None,
                          ventana_dias: int = VENTANA_HISTORIAL_DIAS) -> pd.DataFrame:
    """
    Por deudor: canal_preferido y hora_preferida según el historial real de
    los últimos `ventana_dias` días. Prioriza gestiones con resultado
    exitoso; si no hay ninguna, usa todas las gestiones del deudor en la
    ventana. Devuelve columnas: id_deudor, canal_preferido, hora_preferida,
    n_gestiones_consideradas.
    """
    hoy = hoy or date.today()
    desde = hoy - timedelta(days=ventana_dias)
    cols = ["id_deudor", "canal_preferido", "hora_preferida", "n_gestiones_consideradas"]
    if gestiones is None or gestiones.empty:
        return pd.DataFrame(columns=cols)

    g = gestiones.copy()
    g["_fecha"] = pd.to_datetime(g["fecha_gestion"], errors="coerce")
    g = g[g["_fecha"].notna() & (g["_fecha"].dt.date >= desde)]
    if g.empty:
        return pd.DataFrame(columns=cols)

    filas = []
    for id_deudor, grupo in g.groupby("id_deudor"):
        exitosas = grupo[grupo["resultado"].isin(RESULTADOS_EXITOSOS)]
        base = exitosas if not exitosas.empty else grupo
        canal = Counter(base["canal"].dropna()).most_common(1)
        hora = Counter(base["_fecha"].dt.hour.dropna()).most_common(1)
        filas.append({
            "id_deudor": id_deudor,
            "canal_preferido": canal[0][0] if canal else None,
            "hora_preferida": int(hora[0][0]) if hora else None,
            "n_gestiones_consideradas": len(base),
        })
    return pd.DataFrame(filas, columns=cols)


# ---------------------------------------------------------------------------
# 2) Plan de contacto de hoy: prioridad + canal + horario + cumplimiento
# ---------------------------------------------------------------------------
def _contactos_previos_por_deudor(gestiones: pd.DataFrame) -> dict:
    if gestiones is None or gestiones.empty:
        return {}
    g = gestiones.copy()
    g["_fecha"] = pd.to_datetime(g["fecha_gestion"], errors="coerce")
    out: dict[str, list] = {}
    for id_deudor, grupo in g.groupby("id_deudor"):
        out[id_deudor] = [d.to_pydatetime() for d in grupo["_fecha"].dropna()]
    return out


def plan_contacto_hoy(gestiones: pd.DataFrame, hoy: date | None = None,
                      ahora: datetime | None = None, politica=None,
                      max_contactos: int | None = None,
                      excluir: set | None = None) -> pd.DataFrame:
    """
    Arma el plan de contacto de hoy, ordenado por prioridad:

      1. Promesas/arreglos vencidos (kobra.seguimiento) primero — ya
         perdieron una fecha comprometida.
      2. El resto de la cartera scoreada (outputs/kobra_scored.csv),
         ordenada por `valor_esperado_recupero` descendente.

    Cada fila trae canal/hora preferidos (según historial real) y se
    descarta si `cumplimiento.puede_contactar` no lo autoriza AHORA. Solo
    quedan filas listas para ejecutar. Columnas: id_deudor, monto,
    dias_mora, tramo_mora, canal, motivo, prioridad_rank, contactable,
    motivo_bloqueo.
    """
    from kobra import cumplimiento as kcump

    hoy = hoy or date.today()
    ahora = ahora or datetime.now()
    prefs = preferencias_contacto(gestiones, hoy).set_index("id_deudor")
    previos = _contactos_previos_por_deudor(gestiones)
    scored = kregistro._scored()
    scored_idx = scored.set_index("id_deudor") if scored is not None else None

    filas = []
    ya_vistos = set()

    vencidas = kseg.promesas_incumplidas(gestiones, hoy)
    for _, r in vencidas.iterrows():
        d = r["id_deudor"]
        ya_vistos.add(d)
        canal = prefs["canal_preferido"].get(d) or r.get("canal") or "Llamada"
        info = scored_idx.loc[d] if scored_idx is not None and d in scored_idx.index else {}
        filas.append({"id_deudor": d, "monto": r.get("monto_acordado"),
                      "dias_mora": info.get("dias_mora") if hasattr(info, "get") else None,
                      "tramo_mora": info.get("tramo_mora") if hasattr(info, "get") else None,
                      "canal": canal, "motivo": f"Promesa/arreglo vencido hace {r['dias_vencida']} días",
                      "_orden": (0, -r["dias_vencida"])})

    if scored is not None:
        resto = scored[~scored["id_deudor"].isin(ya_vistos)].sort_values(
            "valor_esperado_recupero", ascending=False)
        for _, r in resto.iterrows():
            d = r["id_deudor"]
            canal = prefs["canal_preferido"].get(d) or r.get("canal_recomendado") or "Llamada"
            filas.append({"id_deudor": d, "monto": r.get("monto_deuda"),
                          "dias_mora": r.get("dias_mora"), "tramo_mora": r.get("tramo_mora"),
                          "canal": canal, "motivo": "Prioridad por valor esperado de recupero",
                          "_orden": (1, -float(r.get("valor_esperado_recupero", 0) or 0))})

    plan = pd.DataFrame(filas)
    if excluir and not plan.empty:
        plan = plan[~plan["id_deudor"].isin(excluir)]
    if plan.empty:
        return plan.assign(prioridad_rank=pd.Series(dtype=int),
                           contactable=pd.Series(dtype=bool), motivo_bloqueo=pd.Series(dtype=object))

    plan = plan.sort_values("_orden").drop(columns="_orden").reset_index(drop=True)
    plan["prioridad_rank"] = plan.index + 1

    decisiones = [
        kcump.puede_contactar(d, canal=c, ahora=ahora,
                             contactos_previos=previos.get(d, []), politica=politica)
        for d, c in zip(plan["id_deudor"], plan["canal"])
    ]
    plan["contactable"] = [bool(dec) for dec in decisiones]
    plan["motivo_bloqueo"] = [None if dec else dec.motivo for dec in decisiones]

    plan = plan[plan["contactable"]].reset_index(drop=True)
    if max_contactos is not None:
        plan = plan.head(max_contactos)
    return plan


# ---------------------------------------------------------------------------
# 3) Ejecución: llamada real (Twilio) o WhatsApp saliente (plantilla)
# ---------------------------------------------------------------------------
def iniciar_llamada(to: str, id_deudor: str, monto, base_url: str,
                    sid: str | None = None, token: str | None = None,
                    from_: str | None = None, timeout: int = 30) -> dict:
    """Dispara una llamada real vía la API de Twilio (misma lógica que
    `POST /voz/llamar` en `realtime/server.py`, factorizada para poder
    llamarla también desde el scheduler, sin pasar por HTTP)."""
    from urllib.parse import quote

    import requests

    sid = sid or os.getenv("TWILIO_ACCOUNT_SID")
    token = token or os.getenv("TWILIO_AUTH_TOKEN")
    from_ = from_ or os.getenv("TWILIO_FROM")
    if not (sid and token and from_ and to):
        return {"ok": False, "detalle": "Faltan credenciales de Twilio o el número de destino."}

    url = (f"{base_url.rstrip('/')}/voz/entrante?id_deudor={quote(id_deudor or '')}"
           f"&monto={quote(str(monto or ''))}&gestor=IA01")
    try:
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Calls.json",
            data={"To": to, "From": from_, "Url": url}, auth=(sid, token), timeout=timeout)
        ok = resp.status_code in (200, 201)
        cuerpo = resp.json() if ok else {}
        return {"ok": ok, "status": resp.status_code, "sid": cuerpo.get("sid"),
                "detalle": None if ok else resp.text[:400]}
    except Exception as e:
        return {"ok": False, "detalle": str(e)[:300]}


def enviar_whatsapp(to: str, content_variables: dict, sid: str | None = None,
                    token: str | None = None, from_whatsapp: str | None = None,
                    content_sid: str | None = None, timeout: int = 30) -> dict:
    """
    Envía un WhatsApp saliente de **inicio de conversación** (fuera de la
    ventana de 24hs) vía Twilio, usando una **plantilla ya aprobada** por
    Meta/WhatsApp (`content_sid` — Twilio Content API). Esto NO es opcional:
    WhatsApp Business Platform exige una plantilla aprobada para que una
    empresa inicie una conversación; sin `content_sid` configurado, esta
    función no envía nada y devuelve el motivo — no hay forma de saltear
    ese requisito de Meta desde acá.

    Requiere que el cliente ya tenga su propia cuenta de WhatsApp Business
    (vía Twilio) con al menos una plantilla de mensaje aprobada.
    """
    import json

    import requests

    sid = sid or os.getenv("TWILIO_ACCOUNT_SID")
    token = token or os.getenv("TWILIO_AUTH_TOKEN")
    from_whatsapp = from_whatsapp or os.getenv("TWILIO_WHATSAPP_FROM")
    content_sid = content_sid or os.getenv("TWILIO_WHATSAPP_CONTENT_SID")

    if not (sid and token and from_whatsapp and to):
        return {"ok": False, "detalle": "Faltan credenciales de Twilio WhatsApp o el número de destino."}
    if not content_sid:
        return {"ok": False, "detalle": "Falta TWILIO_WHATSAPP_CONTENT_SID (plantilla aprobada por "
                                        "Meta) — sin esto, WhatsApp no permite iniciar la conversación."}

    to_wa = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
    from_wa = from_whatsapp if from_whatsapp.startswith("whatsapp:") else f"whatsapp:{from_whatsapp}"
    try:
        resp = requests.post(
            f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
            data={"To": to_wa, "From": from_wa, "ContentSid": content_sid,
                  "ContentVariables": json.dumps(content_variables or {})},
            auth=(sid, token), timeout=timeout)
        ok = resp.status_code in (200, 201)
        cuerpo = resp.json() if ok else {}
        return {"ok": ok, "status": resp.status_code, "sid": cuerpo.get("sid"),
                "detalle": None if ok else resp.text[:400]}
    except Exception as e:
        return {"ok": False, "detalle": str(e)[:300]}


def enviar_email(to: str, tramo_mora: str, contexto: dict,
                 smtp_host: str | None = None, smtp_port: int | None = None,
                 smtp_user: str | None = None, smtp_password: str | None = None,
                 from_email: str | None = None, timeout: int = 20) -> dict:
    """
    Envía el email de gestión correspondiente al tramo de mora del deudor,
    vía el **SMTP corporativo que defina el cliente** (nunca un servidor
    nuestro) — `smtp_host`/`smtp_user`/etc. se leen de la configuración
    guardada si no se pasan explícitos. La plantilla (asunto + cuerpo) es
    la que la empresa haya customizado para ese tramo (`obtener_plantillas_email`),
    o la de referencia si no la tocó.
    """
    import smtplib
    from email.mime.text import MIMEText

    smtp_host = smtp_host or os.getenv("SMTP_HOST")
    smtp_port = int(smtp_port or os.getenv("SMTP_PORT") or 587)
    smtp_user = smtp_user or os.getenv("SMTP_USER")
    smtp_password = smtp_password or os.getenv("SMTP_PASSWORD")
    from_email = from_email or os.getenv("SMTP_FROM") or smtp_user

    if not (smtp_host and smtp_user and smtp_password and from_email and to):
        return {"ok": False, "detalle": "Falta configurar el SMTP corporativo "
                                        "(SMTP_HOST/SMTP_USER/SMTP_PASSWORD/SMTP_FROM) o falta el email de destino."}

    plantillas = obtener_plantillas_email()
    plantilla = plantillas.get(tramo_mora) or plantillas.get("1-30")
    asunto, cuerpo = renderizar_plantilla(plantilla, contexto)

    try:
        msg = MIMEText(cuerpo, "plain", "utf-8")
        msg["Subject"] = asunto
        msg["From"] = from_email
        msg["To"] = to
        with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(from_email, [to], msg.as_string())
        return {"ok": True, "detalle": None}
    except Exception as e:
        return {"ok": False, "detalle": str(e)[:300]}


def ejecutar_plan(plan: pd.DataFrame, base_url: str, telefonos: dict | None = None,
                  emails: dict | None = None) -> list[dict]:
    """
    Ejecuta cada fila del plan (llamada, WhatsApp o email) y registra el
    resultado en el log de auditoría. `telefonos`/`emails` (opcionales):
    {id_deudor: telefono/email} — sin esto, no hay a dónde llamar/escribir
    (el dataset sintético no trae contactos reales a propósito, ver README
    "Honestidad de los números"); en producción vienen de la cartera real
    que carga el cliente.
    """
    from kobra import auditoria as kauditoria

    telefonos = telefonos or {}
    emails = emails or {}
    resultados = []
    for _, fila in plan.iterrows():
        d = fila["id_deudor"]
        canal = fila["canal"]
        if canal == "Llamada":
            tel = telefonos.get(d)
            r = ({"ok": False, "detalle": "Sin teléfono cargado para este deudor."} if not tel
                else iniciar_llamada(tel, d, fila.get("monto"), base_url))
        elif canal == "WhatsApp":
            tel = telefonos.get(d)
            r = ({"ok": False, "detalle": "Sin teléfono cargado para este deudor."} if not tel
                else enviar_whatsapp(tel, {"1": str(d), "2": str(fila.get("monto") or "")}))
        elif canal == "Email":
            mail = emails.get(d)
            if not mail:
                r = {"ok": False, "detalle": "Sin email cargado para este deudor."}
            else:
                ctx = {"monto": float(fila.get("monto") or 0), "dias_mora": fila.get("dias_mora", 0)}
                r = enviar_email(mail, fila.get("tramo_mora", "1-30"), ctx)
        else:
            r = {"ok": False, "detalle": f"Canal no soportado para envío automático: {canal}"}

        kauditoria.registrar("campana_contacto", {
            "id_deudor": d, "canal": canal, "motivo": fila["motivo"], "ok": r["ok"],
            "detalle": r.get("detalle")})
        resultados.append({"id_deudor": d, "canal": canal, **r})
    return resultados


# ---------------------------------------------------------------------------
# 4) Dedup para el scheduler: no recontactar dos veces el mismo día
# ---------------------------------------------------------------------------
def contactados_hoy_por_campana(hoy: date | None = None) -> set:
    """
    IDs de deudor ya despachados HOY por la campaña automática, leído del
    log de auditoría — necesario porque un envío de WhatsApp/email no
    genera una gestión "cerrada" al instante (a diferencia de una llamada,
    que sí se registra al colgar); sin este chequeo, cada corrida del
    scheduler podría volver a incluir al mismo deudor antes de que exista
    una gestión que lo refleje.
    """
    from kobra import auditoria as kauditoria

    hoy = hoy or date.today()
    hoy_str = hoy.isoformat()
    vistos = set()
    for e in kauditoria.leer():
        if e.get("accion") != "campana_contacto":
            continue
        if str(e.get("ts", "")).startswith(hoy_str):
            d = (e.get("detalle") or {}).get("id_deudor")
            if d:
                vistos.add(d)
    return vistos


def cargar_contactos(csv_path: str) -> tuple[dict, dict]:
    """
    Lee un CSV con columnas `id_deudor,telefono,email` (el que mantiene el
    cliente con los datos reales de su cartera) y devuelve (telefonos, emails)
    como {id_deudor: valor}. Si el archivo no existe, devuelve ({}, {}) —
    sin romper: el dataset sintético de la demo no trae contactos reales
    a propósito (ver README "Honestidad de los números").
    """
    if not csv_path or not os.path.exists(csv_path):
        return {}, {}
    df = pd.read_csv(csv_path, dtype=str)
    telefonos = {r["id_deudor"]: r["telefono"] for _, r in df.iterrows()
                if pd.notna(r.get("telefono")) and str(r["telefono"]).strip()}
    emails = {r["id_deudor"]: r["email"] for _, r in df.iterrows()
             if "email" in df.columns and pd.notna(r.get("email")) and str(r["email"]).strip()}
    return telefonos, emails
