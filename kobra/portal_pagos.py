"""
MV Kobra AI · Portal de cobros centralizado
===========================================
El deudor paga solo, sin hablar con nadie: entra por un LINK de pago, un QR
o con usuario y código, ve su listado de facturas pendientes y paga el total
o una parte por transferencia bancaria o MercadoPago (si la empresa lo
habilitó). Cada pago queda IMPUTADO en un registro conciliable y se empuja
al ERP/CRM de la empresa por webhook, además de poder consultarse por API
(pull) con una API key.

Diseño:
- **Acceso sin cuenta previa**: el link/QR lleva un token HMAC firmado con el
  secreto del servidor (no hay nada que "registrar"); el acceso por
  usuario+código usa el id de deudor y un código derivado por HMAC — ambos
  se pueden regenerar desde la app y compartir por WhatsApp/mail.
- **Facturas**: si la cartera del cliente no trae el desglose, se deriva un
  desglose determinístico de la deuda (cuotas vencidas) — mismo id, mismas
  facturas siempre. Con datos reales, el mismo esquema acepta el desglose
  importado.
- **Imputación**: cada pago aprobado/informado queda en
  `pagos_portal.csv` (estado auditable) y en `imputaciones_erp.jsonl`
  (cola para el ERP). Si hay webhook configurado se hace POST al confirmar,
  con reintento simple; el pull por API (`/api/erp/imputaciones`) es la vía
  robusta para cualquier ERP/CRM sin desarrollo del lado del cliente.
- **Demo comercial**: MercadoPago en demo no cobra de verdad — arma el link
  preconfigurado de la empresa (o uno simulado) y aprueba el pago al volver.
  Con credenciales reales, el mismo flujo queda listo para producción.

Sin dependencias nuevas: hmac/hashlib/csv/json de la stdlib.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Configuración del portal (por tenant)
# ---------------------------------------------------------------------------
CONFIG_DEFAULT = {
    "transferencia": {
        "habilitado": True,
        "banco": "",
        "titular": "",
        "cuenta": "",
        "nota": "",
    },
    "mercadopago": {
        "habilitado": False,
        # Link base preconfigurado por la empresa (link de pago / suscripción
        # de MercadoPago). En demo, si está vacío se usa uno simulado.
        "link_base": "",
    },
    "erp": {
        # Webhook saliente: POST JSON de cada imputación al ERP/CRM.
        "webhook_url": "",
        # API key para el pull entrante GET /api/erp/imputaciones.
        "api_key": "",
    },
}


def _ruta_config(dir_datos_tenant: str) -> str:
    return os.path.join(dir_datos_tenant, "portal_config.json")


def cargar_config(dir_datos_tenant: str) -> dict:
    """Config del portal con defaults completos (merge superficial por
    sección: una config guardada con menos claves no rompe nada)."""
    cfg = {k: dict(v) for k, v in CONFIG_DEFAULT.items()}
    ruta = _ruta_config(dir_datos_tenant)
    if os.path.exists(ruta):
        try:
            with open(ruta, encoding="utf-8") as f:
                guardada = json.load(f)
            for seccion, valores in guardada.items():
                if seccion in cfg and isinstance(valores, dict):
                    cfg[seccion].update(valores)
        except (OSError, ValueError):
            pass
    return cfg


def guardar_config(dir_datos_tenant: str, nueva: dict) -> dict:
    """Persiste solo las secciones/claves conocidas (no es un JSON libre)."""
    cfg = cargar_config(dir_datos_tenant)
    for seccion, valores in (nueva or {}).items():
        if seccion in cfg and isinstance(valores, dict):
            for k, v in valores.items():
                if k in cfg[seccion]:
                    cfg[seccion][k] = v
    os.makedirs(dir_datos_tenant, exist_ok=True)
    with open(_ruta_config(dir_datos_tenant), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return cfg


def api_key_erp(dir_datos_tenant: str, secreto: str) -> str:
    """API key del pull ERP: si la empresa no configuró una, se deriva una
    estable del secreto del servidor (así el endpoint nunca queda abierto)."""
    cfg = cargar_config(dir_datos_tenant)
    propia = (cfg["erp"].get("api_key") or "").strip()
    if propia:
        return propia
    return hmac.new(secreto.encode(), b"erp-api-key",
                    hashlib.sha256).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Acceso del deudor: token firmado (link/QR) y usuario+código
# ---------------------------------------------------------------------------
def _firma(secreto: str, mensaje: str, largo: int = 20) -> str:
    return hmac.new(secreto.encode(), mensaje.encode(),
                    hashlib.sha256).hexdigest()[:largo]


def token_portal(secreto: str, empresa: str, id_deudor: str) -> str:
    """Token del link/QR: `empresa.id.firma` — verificable sin estado."""
    cuerpo = f"{empresa}.{id_deudor}"
    return f"{cuerpo}.{_firma(secreto, 'portal|' + cuerpo)}"


def validar_token(secreto: str, token: str):
    """Devuelve (empresa, id_deudor) o None si la firma no cierra."""
    partes = (token or "").split(".")
    if len(partes) != 3:
        return None
    cuerpo = f"{partes[0]}.{partes[1]}"
    esperada = _firma(secreto, "portal|" + cuerpo)
    if not hmac.compare_digest(esperada, partes[2]):
        return None
    return partes[0], partes[1]


def codigo_acceso(secreto: str, empresa: str, id_deudor: str) -> str:
    """Código de 6 dígitos del acceso usuario+código (usuario = id deudor).
    Derivado por HMAC: estable, sin tabla de contraseñas que administrar."""
    d = hmac.new(secreto.encode(), f"codigo|{empresa}|{id_deudor}".encode(),
                 hashlib.sha256).digest()
    return f"{int.from_bytes(d[:4], 'big') % 1_000_000:06d}"


# ---------------------------------------------------------------------------
# Facturas del deudor
# ---------------------------------------------------------------------------
def facturas_de(fila: dict) -> list:
    """Desglose de la deuda en facturas/cuotas vencidas.

    Determinístico (mismo deudor → mismas facturas): la cantidad sale de
    `plan_cuotas`/`cuotas_atrasadas` si existe (mínimo 1, máximo 6) y los
    montos se reparten con pesos derivados del id — sin números al azar que
    cambien entre visitas. La suma SIEMPRE es exactamente `monto_deuda`."""
    total = round(float(fila.get("monto_deuda") or 0), 2)
    if total <= 0:
        return []
    n = fila.get("cuotas_atrasadas") or fila.get("plan_cuotas") or 1
    try:
        n = max(1, min(6, int(n)))
    except (TypeError, ValueError):
        n = 1
    id_deudor = str(fila.get("id_deudor", ""))
    semilla = hashlib.sha256(id_deudor.encode()).digest()
    pesos = [semilla[i] + 64 for i in range(n)]          # 64..319: sin cuota ínfima
    suma_pesos = sum(pesos)
    dias_mora = int(fila.get("dias_mora") or 30)
    base = date.today() - timedelta(days=dias_mora)
    facturas, acumulado = [], 0.0
    for i in range(n):
        if i == n - 1:
            monto = round(total - acumulado, 2)          # el resto exacto
        else:
            monto = round(total * pesos[i] / suma_pesos, 2)
            acumulado = round(acumulado + monto, 2)
        vence = base + timedelta(days=30 * i)
        facturas.append({
            "numero": f"{id_deudor}-F{i + 1:02d}",
            "concepto": f"Cuota {i + 1} de {n}" if n > 1 else "Saldo adeudado",
            "vencimiento": vence.isoformat(),
            "monto": monto,
        })
    return facturas


# ---------------------------------------------------------------------------
# Pagos e imputación
# ---------------------------------------------------------------------------
_CAMPOS_PAGO = ["referencia", "empresa", "id_deudor", "monto", "metodo",
                "tipo", "estado", "creado", "actualizado"]
# Estados: pendiente (transferencia creada, sin informar) → informado
# (el deudor declaró la transferencia; pendiente de conciliar) /
# aprobado (MercadoPago). Imputan al ERP: informado y aprobado.
_ESTADOS_IMPUTABLES = ("informado", "aprobado")

_LOCK = threading.Lock()


def _ruta_pagos(dir_datos_tenant: str) -> str:
    return os.path.join(dir_datos_tenant, "pagos_portal.csv")


def _ruta_imputaciones(dir_datos_tenant: str) -> str:
    return os.path.join(dir_datos_tenant, "imputaciones_erp.jsonl")


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def listar_pagos(dir_datos_tenant: str, id_deudor: str | None = None) -> list:
    ruta = _ruta_pagos(dir_datos_tenant)
    if not os.path.exists(ruta):
        return []
    with open(ruta, encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))
    if id_deudor is not None:
        filas = [p for p in filas if p["id_deudor"] == id_deudor]
    for p in filas:
        p["monto"] = float(p["monto"])
    return filas


def _escribir_pagos(dir_datos_tenant: str, pagos: list) -> None:
    os.makedirs(dir_datos_tenant, exist_ok=True)
    with open(_ruta_pagos(dir_datos_tenant), "w", encoding="utf-8",
              newline="") as f:
        w = csv.DictWriter(f, fieldnames=_CAMPOS_PAGO)
        w.writeheader()
        w.writerows(pagos)


def crear_pago(dir_datos_tenant: str, empresa: str, id_deudor: str,
               monto: float, metodo: str, total_deuda: float) -> dict:
    """Crea el intento de pago (total o parcial) y devuelve el registro.
    `metodo`: 'transferencia' | 'mercadopago'."""
    monto = round(float(monto), 2)
    if monto <= 0:
        raise ValueError("El monto a pagar tiene que ser mayor a cero.")
    saldo = saldo_pendiente(dir_datos_tenant, id_deudor, total_deuda)
    if monto > saldo + 0.01:
        raise ValueError(
            f"El monto supera el saldo pendiente ({saldo:.2f}).")
    if metodo not in ("transferencia", "mercadopago"):
        raise ValueError("Método de pago desconocido.")
    with _LOCK:
        pagos = listar_pagos(dir_datos_tenant)
        referencia = f"KP-{int(time.time() * 1000) % 10**9:09d}-{len(pagos) + 1:03d}"
        registro = {
            "referencia": referencia, "empresa": empresa,
            "id_deudor": id_deudor, "monto": monto, "metodo": metodo,
            "tipo": "total" if abs(monto - saldo) < 0.01 else "parcial",
            "estado": "pendiente", "creado": _ahora(), "actualizado": _ahora(),
        }
        pagos.append(registro)
        _escribir_pagos(dir_datos_tenant, pagos)
    return dict(registro)


def saldo_pendiente(dir_datos_tenant: str, id_deudor: str,
                    total_deuda: float) -> float:
    """Deuda menos lo ya pagado/informado por el portal."""
    pagado = sum(p["monto"] for p in listar_pagos(dir_datos_tenant, id_deudor)
                 if p["estado"] in _ESTADOS_IMPUTABLES)
    return round(max(0.0, float(total_deuda) - pagado), 2)


def confirmar_pago(dir_datos_tenant: str, referencia: str, estado: str,
                   webhook_url: str = "") -> dict:
    """Pasa un pago a `informado` (transferencia declarada) o `aprobado`
    (MercadoPago) e imputa: cola ERP + webhook si está configurado."""
    if estado not in _ESTADOS_IMPUTABLES:
        raise ValueError(f"Estado no imputable: {estado}")
    with _LOCK:
        pagos = listar_pagos(dir_datos_tenant)
        registro = next((p for p in pagos if p["referencia"] == referencia), None)
        if registro is None:
            raise KeyError(f"No existe el pago {referencia}.")
        if registro["estado"] in _ESTADOS_IMPUTABLES:
            return dict(registro)          # idempotente: ya imputado
        registro["estado"] = estado
        registro["actualizado"] = _ahora()
        _escribir_pagos(dir_datos_tenant, pagos)
        imputacion = _imputar(dir_datos_tenant, registro)
    if webhook_url:
        _webhook_async(webhook_url, imputacion)
    return dict(registro)


def _imputar(dir_datos_tenant: str, pago: dict) -> dict:
    """Asiento para el ERP/CRM: una línea JSON por pago imputado."""
    imputacion = {
        "tipo": "pago_portal",
        "referencia": pago["referencia"],
        "id_deudor": pago["id_deudor"],
        "empresa": pago["empresa"],
        "monto": pago["monto"],
        "metodo": pago["metodo"],
        "pago_total": pago["tipo"] == "total",
        "estado": pago["estado"],
        "imputado_en": _ahora(),
    }
    with open(_ruta_imputaciones(dir_datos_tenant), "a", encoding="utf-8") as f:
        f.write(json.dumps(imputacion, ensure_ascii=False) + "\n")
    return imputacion


def listar_imputaciones(dir_datos_tenant: str, desde: str = "") -> list:
    """Pull para el ERP/CRM: todas las imputaciones (opcionalmente desde un
    timestamp ISO exclusivo, para sincronización incremental)."""
    ruta = _ruta_imputaciones(dir_datos_tenant)
    if not os.path.exists(ruta):
        return []
    out = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.strip()
            if not linea:
                continue
            try:
                imp = json.loads(linea)
            except ValueError:
                continue
            if desde and imp.get("imputado_en", "") <= desde:
                continue
            out.append(imp)
    return out


def _webhook_async(url: str, imputacion: dict, intentos: int = 3) -> None:
    """POST de la imputación al ERP en un hilo aparte (no bloquea el pago del
    deudor). Best-effort con reintento corto: la fuente de verdad sigue
    siendo la cola local + el pull por API."""
    def _enviar():
        import requests
        for i in range(intentos):
            try:
                r = requests.post(url, json=imputacion, timeout=6)
                if r.ok:
                    return
            except Exception:
                pass
            time.sleep(2 * (i + 1))
    threading.Thread(target=_enviar, daemon=True).start()


# ---------------------------------------------------------------------------
# MercadoPago (preconfigurado por la empresa; simulado en demo)
# ---------------------------------------------------------------------------
def link_mercadopago(cfg: dict, referencia: str, monto: float) -> str:
    """Link de pago de MercadoPago. Si la empresa preconfiguró su link base
    (link de pago de su cuenta MP) se usa ese con la referencia; si no, en
    demo se arma un link simulado que deja claro que no cobra de verdad."""
    base = (cfg.get("mercadopago", {}).get("link_base") or "").strip()
    if base:
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}external_reference={referencia}"
    return (f"https://demo.mvkobranzaia.com/mercadopago-simulado"
            f"?ref={referencia}&monto={monto:.2f}")
