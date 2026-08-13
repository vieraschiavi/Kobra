# © 2026 Martín Viera. Todos los derechos reservados.
"""
MV Kobra AI · Integración con ERP / base de datos (sábana de gestiones)
====================================================================
Cierra el círculo: cada gestión —la haya hecho el **Gestor IA** o un **humano**—
queda tipificada con su resultado y sus datos (fechas, montos, notas) y puede
**exportarse o sincronizarse a cualquier base de datos o ERP**:

  - Archivos: JSON / CSV / Excel (para importar en cualquier sistema).
  - **API REST**: hace POST de la sábana al webhook/endpoint del ERP del cliente.
  - **Base de datos**: escribe en cualquier motor SQL vía SQLAlchemy
    (PostgreSQL, MySQL/MariaDB, SQL Server, Oracle, SQLite…) con una URL de conexión.
  - **Mapeo de campos** opcional: renombra las columnas de MV Kobra AI a las del ERP.

Tipificaciones estándar de cobranza soportadas (el campo `resultado`):
  Pago · Arreglo de pago · Promesa de pago · Informado · No contactado ·
  Fallecido · Negativa · Número erróneo · Sin acuerdo
"""
from __future__ import annotations

import io
import json

import pandas as pd

TIPIFICACIONES = [
    "Pago", "Arreglo de pago", "Promesa de pago", "Informado",
    "No contactado", "Fallecido", "Negativa", "Número erróneo", "Sin acuerdo",
]

# Columnas de la sábana de datos exportable (orden estable para el ERP)
SABANA_COLS = [
    "id_gestion", "fecha_gestion", "id_deudor", "documento",
    "gestor_id", "gestor", "tipo_gestor", "canal", "resultado",
    "fecha_compromiso", "fecha_pago", "monto_gestionado", "monto_acordado",
    "cuotas", "descuento", "recupero",
    "calidad_gestion", "sentimiento_cliente", "emocion_dominante",
    "tecnicas_usadas", "segmento", "producto", "departamento", "tramo_mora",
    "notas",
]


def _tipo_gestor(gestor_id: str) -> str:
    return "IA" if str(gestor_id).upper().startswith("IA") else "Humano"


def sabana(gestiones: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza el historial de gestiones a la **sábana de datos** exportable,
    con todas las columnas de `SABANA_COLS`. Deriva `tipo_gestor` (IA/Humano) y
    `fecha_gestion`; completa con vacío las columnas que aún no se registran.
    """
    df = gestiones.copy()
    if "tipo_gestor" not in df.columns and "gestor_id" in df.columns:
        df["tipo_gestor"] = df["gestor_id"].map(_tipo_gestor)
    if "fecha_gestion" not in df.columns:
        # si no hay fecha explícita, usar el mes (YYYY-MM) como referencia
        df["fecha_gestion"] = df.get("mes", "")
    for col in SABANA_COLS:
        if col not in df.columns:
            df[col] = ""
    return df[SABANA_COLS].copy()


def aplicar_mapeo(df: pd.DataFrame, mapeo: dict | None) -> pd.DataFrame:
    """Renombra columnas de MV Kobra AI → nombres del ERP del cliente (opcional)."""
    if not mapeo:
        return df
    return df.rename(columns={k: v for k, v in mapeo.items() if k in df.columns})


# ---------------------------------------------------------------------------
# Exportes a archivo
# ---------------------------------------------------------------------------
def a_json(df: pd.DataFrame) -> str:
    return df.to_json(orient="records", force_ascii=False, date_format="iso")


def a_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8")


def a_excel(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xl:
        df.to_excel(xl, sheet_name="Gestiones", index=False)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Envío por API REST al ERP del cliente
# ---------------------------------------------------------------------------
def enviar_api(df: pd.DataFrame, url: str, api_key: str | None = None,
               headers: dict | None = None, lote: int = 500,
               timeout: int = 30) -> dict:
    """
    Hace POST de la sábana al endpoint/webhook del ERP. Envía en lotes:
    `{"gestiones": [ {...}, ... ]}`. Autenticación opcional por Bearer token.

    Devuelve {ok, enviados, lotes, status, detalle}.
    """
    import requests
    if not url:
        return {"ok": False, "enviados": 0, "detalle": "Falta la URL del ERP."}
    hdrs = {"Content-Type": "application/json"}
    if api_key:
        hdrs["Authorization"] = f"Bearer {api_key}"
    if headers:
        hdrs.update(headers)
    from kobra import auditoria as kauditoria
    registros = json.loads(a_json(df))
    enviados, ultimo_status = 0, None
    for i in range(0, len(registros), max(lote, 1)):
        chunk = registros[i:i + lote]
        try:
            r = requests.post(url, data=json.dumps({"gestiones": chunk}),
                              headers=hdrs, timeout=timeout)
            ultimo_status = r.status_code
            if r.status_code not in (200, 201, 202):
                kauditoria.registrar("erp_envio_api", {"ok": False, "url": url,
                                                       "status": r.status_code, "enviados": enviados})
                return {"ok": False, "enviados": enviados, "status": r.status_code,
                        "detalle": r.text[:400]}
            enviados += len(chunk)
        except Exception as e:
            kauditoria.registrar("erp_envio_api", {"ok": False, "url": url, "error": str(e)[:200]})
            return {"ok": False, "enviados": enviados, "detalle": str(e)[:400]}
    kauditoria.registrar("erp_envio_api", {"ok": True, "url": url, "enviados": enviados})
    return {"ok": True, "enviados": enviados,
            "lotes": (len(registros) + lote - 1) // max(lote, 1),
            "status": ultimo_status, "detalle": "Sábana enviada al ERP."}


# ---------------------------------------------------------------------------
# Sincronización a cualquier base de datos SQL (SQLAlchemy)
# ---------------------------------------------------------------------------
def sincronizar_db(df: pd.DataFrame, conn_url: str, tabla: str = "kobra_gestiones",
                   if_exists: str = "append") -> dict:
    """
    Escribe la sábana en cualquier motor SQL a partir de una **URL de conexión**
    de SQLAlchemy, por ejemplo:
      - postgresql+psycopg2://user:pass@host:5432/basedatos
      - mysql+pymysql://user:pass@host/basedatos
      - mssql+pyodbc://user:pass@host/basedatos?driver=ODBC+Driver+17+for+SQL+Server
      - sqlite:///ruta/al/archivo.db

    `if_exists`: "append" (agrega) | "replace" (reemplaza la tabla).
    """
    from kobra import auditoria as kauditoria
    # nunca loguear la URL cruda: puede traer usuario:contraseña embebidos
    _destino = conn_url.split("@")[-1] if conn_url else ""

    if not conn_url:
        return {"ok": False, "filas": 0, "detalle": "Falta la URL de conexión."}
    try:
        from sqlalchemy import create_engine
    except ImportError:
        return {"ok": False, "filas": 0,
                "detalle": "Instalá SQLAlchemy (y el driver del motor) para sincronizar a base de datos."}
    try:
        eng = create_engine(conn_url)
        df.to_sql(tabla, eng, if_exists=if_exists, index=False)
        eng.dispose()
        kauditoria.registrar("erp_sync_db", {"ok": True, "destino": _destino,
                                             "tabla": tabla, "filas": int(len(df))})
        return {"ok": True, "filas": int(len(df)), "tabla": tabla,
                "detalle": f"{len(df)} gestiones escritas en «{tabla}»."}
    except Exception as e:
        kauditoria.registrar("erp_sync_db", {"ok": False, "destino": _destino,
                                             "tabla": tabla, "error": str(e)[:200]})
        return {"ok": False, "filas": 0, "detalle": str(e)[:400]}
