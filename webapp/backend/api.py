"""
MV Kobra AI · Backend del SaaS web (FastAPI)
=============================================
API REST que expone los mismos motores que usa el dashboard Streamlit
(`app/app.py`) para el frontend React profesional (`webapp/frontend`).
No reemplaza a Streamlit — conviven: mismos CSV/modelos, otra interfaz.

Diseño:

- **Auth con JWT** (PyJWT, HS256): el login reutiliza las contraseñas de
  `kobra.autenticacion` (roles admin/gestor). El token lleva `rol` y
  `empresa`.
- **Multi-tenant desde el día uno**: toda lectura de datos pasa por
  `_datos_de(empresa)`. La empresa "principal" usa los datos existentes
  del repo (`outputs/`, `data/`); cualquier otra empresa resuelve a
  `data/tenants/<empresa>/` — el aislamiento es por directorio, listo para
  un despliegue hosteado. (Honestidad: el aprovisionamiento de tenants es
  manual — crear el directorio y colocar sus CSV; no hay UI de alta aún.)
- **API entrante para integradores**: POST /api/integracion/cartera acepta
  la cartera como JSON y la deja normalizada en el directorio del tenant —
  el mismo camino que el CSV manual, pero automatizable desde el core del
  cliente (API-first).

Correr:  python -m uvicorn webapp.backend.api:app --port 8800
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from datetime import datetime, timezone

import pandas as pd
from fastapi import Depends, FastAPI, File, Header, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from kobra import analitica as kanalitica          # noqa: E402
from kobra import autenticacion as kauth           # noqa: E402
from kobra import ayuda as kayuda                  # noqa: E402
from kobra import cartera_manual as kcartera       # noqa: E402
from kobra import config as kconfig                # noqa: E402
from kobra import informe_ejecutivo as kinforme    # noqa: E402
from kobra import llm as kllm                      # noqa: E402
from kobra import paises as kpaises                # noqa: E402
from kobra import registro as kregistro            # noqa: E402
from kobra import rutas as krutas                  # noqa: E402
from kobra import seguimiento as kseg              # noqa: E402
from backend_venta import licencias as klicencias  # noqa: E402

# Escribible siempre (ver kobra/rutas.py): en dev/tests es el repo (ROOT),
# igual que antes; instalado, es una carpeta propia del usuario, nunca
# Program Files. ROOT sigue usándose para leer recursos bundleados (el
# build de React, sys.path) — nunca para escribir datos de negocio.
DIR_DATOS = krutas.DIR_DATOS

kconfig.aplicar()

TOKEN_TTL_SEG = 12 * 3600
EMPRESA_DEFAULT = "principal"

# Modo standalone (instalador de Windows, kobra_launcher.py lo activa): en vez
# de contraseña de admin, la puerta de entrada es la licencia emitida al
# comprar (o el trial de 3 días). En modo hosted (Vercel, multi-tenant) esto
# queda desactivado y el login sigue siendo por contraseña, sin cambios.
MODO_STANDALONE = os.getenv("KOBRA_MODO_STANDALONE", "").lower() in ("1", "true", "si", "sí")
# Modo owner (carpeta owner/ del repo): la copia del dueño del producto —
# sin licencia, sin trial, sin vencimiento, entra directo como admin. Solo
# tiene efecto combinado con MODO_STANDALONE (el server local del launcher,
# que escucha únicamente en 127.0.0.1); en el despliegue hosted esta variable
# no se setea nunca y no cambia nada.
MODO_OWNER = os.getenv("KOBRA_OWNER", "").lower() in ("1", "true", "si", "sí")
_CLAVE_LICENCIA = "LICENCIA_TOKEN"


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def _secreto() -> str:
    """Secreto HS256 persistente: env > kconfig extra > generado y guardado."""
    s = os.getenv("KOBRA_API_SECRET") or kconfig.leer_extra("KOBRA_API_SECRET")
    if not s:
        import secrets
        s = secrets.token_urlsafe(48)
        kconfig.guardar_extra("KOBRA_API_SECRET", s)
    return s


def _emitir_token(rol: str, empresa: str) -> str:
    import jwt
    return jwt.encode({"rol": rol, "empresa": empresa,
                       "exp": int(time.time()) + TOKEN_TTL_SEG},
                      _secreto(), algorithm="HS256")


class Usuario(BaseModel):
    rol: str
    empresa: str


def usuario_actual(authorization: str = Header(default="")) -> Usuario:
    import jwt
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Falta el token (Authorization: Bearer …).")
    try:
        datos = jwt.decode(authorization[7:], _secreto(), algorithms=["HS256"])
    except Exception:
        raise HTTPException(401, "Token inválido o vencido — iniciá sesión de nuevo.")
    return Usuario(rol=datos.get("rol", "gestor"),
                   empresa=datos.get("empresa", EMPRESA_DEFAULT))


def solo_admin(u: Usuario = Depends(usuario_actual)) -> Usuario:
    if u.rol != "admin":
        raise HTTPException(403, "Esta acción es solo para el rol Administrador.")
    return u


# ---------------------------------------------------------------------------
# Datos por empresa (multi-tenant por directorio)
# ---------------------------------------------------------------------------
def _dir_tenant(empresa: str) -> str:
    return os.path.join(DIR_DATOS, "data", "tenants", empresa)


def _datos_de(empresa: str) -> dict:
    """Rutas de datos del tenant. 'principal' = los datos del repo."""
    if empresa == EMPRESA_DEFAULT:
        return {"scored": os.path.join(DIR_DATOS, "outputs", "kobra_scored.csv"),
                "gestiones": os.path.join(DIR_DATOS, "data", "kobra_gestiones.csv")}
    d = _dir_tenant(empresa)
    return {"scored": os.path.join(d, "kobra_scored.csv"),
            "gestiones": os.path.join(d, "kobra_gestiones.csv")}


def _archivo_real(empresa: str) -> str:
    """Cartera real subida por el cliente — se guarda APARTE de la demo
    (nunca la pisa), así el botón demo ON/OFF puede volver a los datos de
    demostración cuando se quiera."""
    return os.path.join(os.path.dirname(_datos_de(empresa)["scored"]), "kobra_cartera_real.csv")


def _archivo_origen(empresa: str) -> str:
    return os.path.join(os.path.dirname(_datos_de(empresa)["scored"]), "origen_cartera.json")


def _origen_meta(empresa: str) -> dict:
    ruta = _archivo_origen(empresa)
    if os.path.exists(ruta):
        try:
            with open(ruta, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            pass
    return {}


def _modo_cartera(empresa: str) -> str:
    """'demo' (default) o 'real' — qué cartera ve TODO el dashboard. Nunca
    devuelve 'real' si el archivo real no está (defensa ante marcas viejas)."""
    meta = _origen_meta(empresa)
    modo = meta.get("modo") or meta.get("tipo") or "demo"
    if modo == "real" and os.path.exists(_archivo_real(empresa)):
        return "real"
    return "demo"


def _scored(empresa: str) -> pd.DataFrame:
    # El botón demo decide la fuente: real (la subida) o demo (la sintética).
    if _modo_cartera(empresa) == "real":
        return pd.read_csv(_archivo_real(empresa))
    ruta = _datos_de(empresa)["scored"]
    if not os.path.exists(ruta):
        raise HTTPException(404, f"La empresa '{empresa}' no tiene cartera scoreada cargada.")
    return pd.read_csv(ruta)


def _gestiones(empresa: str) -> pd.DataFrame | None:
    ruta = _datos_de(empresa)["gestiones"]
    return pd.read_csv(ruta) if os.path.exists(ruta) else None


def _archivo_pais(empresa: str) -> str:
    base = os.path.join(DIR_DATOS, "data") if empresa == EMPRESA_DEFAULT else _dir_tenant(empresa)
    return os.path.join(base, "pais.json")


def _pais_de(empresa: str) -> str:
    """Código de país del tenant (Fase 1 LATAM). Uruguay si no se configuró."""
    ruta = _archivo_pais(empresa)
    if not os.path.exists(ruta):
        return kpaises.PAIS_DEFAULT
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f).get("codigo", kpaises.PAIS_DEFAULT)
    except (OSError, ValueError):
        return kpaises.PAIS_DEFAULT


def _guardar_pais_de(empresa: str, codigo: str) -> None:
    ruta = _archivo_pais(empresa)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({"codigo": codigo}, f)


_COL_FECHA_CANDIDATAS = ["fecha", "fecha_alta", "fecha_originacion", "fecha_ingreso",
                         "fecha_solicitud", "fecha_mora", "fecha_vencimiento", "mes"]


def _col_fecha(df: pd.DataFrame):
    """Devuelve (nombre, serie_datetime) de la primera columna de fecha
    reconocible del dataset — o (None, None) si la cartera no trae fechas
    (caso típico: es una foto de deudores, sin dimensión temporal)."""
    if df is None:
        return None, None
    for c in _COL_FECHA_CANDIDATAS:
        if c in df.columns:
            s = pd.to_datetime(df[c], errors="coerce")
            if s.notna().any():
                return c, s
    return None, None


def _aplicar_filtros(df: pd.DataFrame, segmento=None, tramo=None, propension=None,
                     busqueda=None, producto=None, departamento=None,
                     monto_min=None, monto_max=None, dias_min=None, dias_max=None,
                     anio=None, mes=None) -> pd.DataFrame:
    """Aplica filtros del dashboard de forma DEFENSIVA: cada filtro se ignora si
    la columna no está en el dataset activo (real o demo), así una cartera con
    otro esquema nunca rompe la vista."""
    def _cat(col, val):
        nonlocal df
        if val and col in df.columns:
            df = df[df[col].astype(str) == str(val)]

    _cat("segmento", segmento)
    _cat("tramo_mora", tramo)
    _cat("segmento_propension", propension)
    _cat("producto", producto)
    _cat("departamento", departamento)
    if busqueda and "id_deudor" in df.columns:
        df = df[df["id_deudor"].astype(str).str.contains(busqueda, case=False, na=False)]
    for col, lo, hi in [("monto_deuda", monto_min, monto_max),
                        ("dias_mora", dias_min, dias_max)]:
        if col in df.columns and (lo is not None or hi is not None):
            serie = pd.to_numeric(df[col], errors="coerce")
            if lo is not None:
                df = df[serie >= float(lo)]
                serie = pd.to_numeric(df[col], errors="coerce")
            if hi is not None:
                df = df[serie <= float(hi)]
    if anio or mes:
        _, serie_fecha = _col_fecha(df)
        if serie_fecha is not None:
            serie_fecha = serie_fecha.reindex(df.index)
            if anio:
                df = df[serie_fecha.dt.year == int(anio)]
                serie_fecha = serie_fecha.reindex(df.index)
            if mes:
                df = df[serie_fecha.dt.month == int(mes)]
    return df


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="MV Kobra AI · API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                   allow_headers=["*"])


@app.get("/api/health")
def health():
    return {"ok": True, "servicio": "mv-kobra-api"}


class LoginIn(BaseModel):
    password: str
    empresa: str = EMPRESA_DEFAULT


def _sin_puerta_por_password():
    """En la copia instalada de un CLIENTE (standalone sin owner) la única
    puerta de entrada es la LICENCIA. Si además se pudiera crear/usar una
    contraseña de admin, cualquiera saltearía el vencimiento de la demo
    creando una clave y entrando para siempre — el límite de días dejaría de
    existir. En modo hosted (multi-tenant) y en la copia del owner, la
    contraseña sigue siendo la puerta normal."""
    if MODO_STANDALONE and not MODO_OWNER:
        raise HTTPException(404, "No encontrado.")


@app.get("/api/auth/estado")
def auth_estado():
    """Sin auth: el login lo consulta al arrancar para saber si mostrar el
    formulario de primer arranque (crear la contraseña de admin) o el de
    ingreso normal. En la copia de un cliente (standalone) no aplica: ahí se
    entra con licencia, así que informa que la puerta es esa."""
    if MODO_STANDALONE and not MODO_OWNER:
        return {"configurado": True, "gestor_configurado": False,
                "por_licencia": True}
    return {"configurado": kauth.configurado(),
            "gestor_configurado": kauth.tiene_password("gestor"),
            "por_licencia": False}


class SetupIn(BaseModel):
    password: str
    empresa: str = EMPRESA_DEFAULT


@app.post("/api/auth/setup")
def auth_setup(datos: SetupIn):
    """Primer arranque: crea la contraseña de administrador desde la propia
    webapp (antes había que abrir el dashboard Streamlit, imposible en hosting).
    Solo funciona si TODAVÍA no hay admin — si ya existe, devuelve 409 para no
    permitir reset sin autenticación. Deja la sesión iniciada.

    No existe en la copia instalada de un cliente: ahí se entra por licencia."""
    _sin_puerta_por_password()
    if kauth.configurado():
        raise HTTPException(409, "El administrador ya está configurado. Iniciá sesión.")
    pw = (datos.password or "").strip()
    if len(pw) < 6:
        raise HTTPException(422, "La contraseña debe tener al menos 6 caracteres.")
    kauth.establecer_password("admin", pw)
    return {"token": _emitir_token("admin", datos.empresa), "rol": "admin",
            "empresa": datos.empresa}


@app.post("/api/auth/login")
def auth_login(datos: LoginIn):
    _sin_puerta_por_password()
    if not kauth.configurado():
        raise HTTPException(409, "Todavía no hay contraseña de administrador creada — "
                                 "creála en esta pantalla para el primer arranque.")
    rol = None
    for candidato in ("admin", "gestor"):
        if kauth.tiene_password(candidato) and kauth.verificar_password(candidato, datos.password):
            rol = candidato
            break
    if not rol:
        raise HTTPException(401, "Contraseña incorrecta.")
    return {"token": _emitir_token(rol, datos.empresa), "rol": rol,
            "empresa": datos.empresa}


class LicenciaIn(BaseModel):
    token: str


def _estado_licencia(token: str | None) -> dict:
    if not token:
        return {"activa": False}
    r = klicencias.licencia_activa(token)
    if not r["ok"]:
        return {"activa": False, "error": r["error"]}
    claims = r["claims"]
    dias_restantes = max(0, int((claims["exp"] - time.time()) // 86400))
    return {"activa": True, "plan": claims["plan"],
            "trial": claims["plan"] == "trial", "dias_restantes": dias_restantes}


@app.get("/api/licencia/estado")
def licencia_estado():
    """Sin auth: es lo primero que consulta el frontend al arrancar, antes de
    saber si hay sesión. En modo hosted no hace nada (standalone=False)."""
    if not MODO_STANDALONE:
        return {"standalone": False}
    if MODO_OWNER:
        return {"standalone": True, "activa": True, "owner": True,
                "plan": "owner", "trial": False, "dias_restantes": None}
    return {"standalone": True, **_estado_licencia(kconfig.leer_extra(_CLAVE_LICENCIA))}


@app.post("/api/licencia/owner-login")
def licencia_owner_login():
    """Entrada directa de la copia del owner: emite el token de admin sin
    licencia ni contraseña. Solo existe cuando el launcher local corre con
    KOBRA_OWNER=1 (server en 127.0.0.1); en hosted o en la copia de un
    cliente devuelve 404 como si el endpoint no existiera."""
    if not (MODO_STANDALONE and MODO_OWNER):
        raise HTTPException(404, "No encontrado.")
    return {"token": _emitir_token("admin", EMPRESA_DEFAULT), "rol": "admin",
            "empresa": EMPRESA_DEFAULT}


@app.post("/api/licencia/activar")
def licencia_activar(datos: LicenciaIn):
    if not MODO_STANDALONE:
        raise HTTPException(404, "Este endpoint es solo para la versión standalone.")
    r = klicencias.licencia_activa(datos.token)
    if not r["ok"]:
        mensaje = ("Tu licencia venció — comprá un plan en mvkobranzaia.com para seguir usando MV Kobra AI."
                  if r["error"] == "licencia_expirada" else
                  "Licencia inválida — revisá que la copiaste completa.")
        raise HTTPException(400, mensaje)
    kconfig.guardar_extra(_CLAVE_LICENCIA, datos.token)
    estado = _estado_licencia(datos.token)
    return {"token": _emitir_token("admin", EMPRESA_DEFAULT), "rol": "admin",
            "empresa": EMPRESA_DEFAULT, **estado}


@app.get("/api/kpis")
def kpis(u: Usuario = Depends(usuario_actual)):
    f = _scored(u.empresa)
    cartera = float(f["monto_deuda"].sum())
    recupero = float(f["valor_esperado_recupero"].sum())
    riesgo = float(f.loc[f["segmento_propension"] == "Baja", "monto_deuda"].sum())
    return {"deudores": int(len(f)), "cartera_uyu": cartera,
            "recupero_esperado_uyu": recupero,
            "recupero_pct": recupero / cartera if cartera else 0,
            "probpago_promedio": float(f["probpago"].mean()),
            "mora_promedio_dias": float(f["dias_mora"].mean()),
            "cartera_riesgo_uyu": riesgo,
            "riesgo_pct": riesgo / cartera if cartera else 0}


@app.get("/api/graficos/resumen")
def graficos_resumen(u: Usuario = Depends(usuario_actual)):
    f = _scored(u.empresa)
    por_tramo = (f.groupby("tramo_mora")
                   .agg(cartera=("monto_deuda", "sum"),
                        recupero=("valor_esperado_recupero", "sum"))
                   .reindex(["1-30", "31-60", "61-90", "91-180", "180+"]).dropna()
                   .reset_index())
    propension = (f.groupby("segmento_propension")["id_deudor"].count()
                    .reset_index().rename(columns={"id_deudor": "cantidad"}))
    por_segmento = (f.groupby("segmento")["valor_esperado_recupero"].sum()
                      .sort_values(ascending=False).reset_index())
    top_deptos = (f.groupby("departamento")["monto_deuda"].sum()
                    .sort_values(ascending=False).head(10).reset_index())
    return {"por_tramo": por_tramo.to_dict("records"),
            "propension": propension.to_dict("records"),
            "por_segmento": por_segmento.to_dict("records"),
            "top_departamentos": top_deptos.to_dict("records")}


_COLS_CARTERA = ["prioridad", "id_deudor", "segmento", "producto", "departamento",
                 "tramo_mora", "monto_deuda", "probpago", "segmento_propension",
                 "estrategia", "descuento_recomendado", "canal_recomendado",
                 "valor_esperado_recupero"]


def _ordenar_cartera(f: pd.DataFrame) -> pd.DataFrame:
    """Ordena por prioridad si existe; si no (esquema real distinto), por valor
    esperado de recupero descendente; y si tampoco, deja el orden natural. Nunca
    rompe la vista."""
    if "prioridad" in f.columns:
        return f.sort_values("prioridad")
    if "valor_esperado_recupero" in f.columns:
        return f.sort_values("valor_esperado_recupero", ascending=False)
    if "monto_deuda" in f.columns:
        return f.sort_values("monto_deuda", ascending=False)
    return f


@app.get("/api/cartera/filtros")
def cartera_filtros(u: Usuario = Depends(usuario_actual)):
    """Opciones de filtrado REALES del dataset activo (real o demo): valores de
    cada dimensión categórica presente + rangos de monto y días de mora + años/
    meses si la cartera trae fecha. El front arma los filtros con esto, así se
    adapta a cualquier esquema — no hay valores hardcodeados."""
    g = _scored(u.empresa)
    def _u(col):
        return sorted(g[col].dropna().astype(str).unique().tolist()) if col in g.columns else []
    def _rango(col):
        if col not in g.columns:
            return None
        s = pd.to_numeric(g[col], errors="coerce").dropna()
        if s.empty:
            return None
        return {"min": int(s.min()), "max": int(s.max())}
    col_fecha, serie = _col_fecha(g)
    anios = sorted(serie.dt.year.dropna().astype(int).unique().tolist()) if serie is not None else []
    meses = sorted(serie.dt.month.dropna().astype(int).unique().tolist()) if serie is not None else []
    return {
        "modo": _modo_cartera(u.empresa),
        "segmentos": _u("segmento"), "productos": _u("producto"),
        "departamentos": _u("departamento"), "tramos": _u("tramo_mora"),
        "propensiones": _u("segmento_propension"),
        "monto": _rango("monto_deuda"), "dias_mora": _rango("dias_mora"),
        "tiene_fecha": col_fecha is not None, "anios": anios, "meses": meses,
    }


@app.get("/api/cartera")
def cartera(u: Usuario = Depends(usuario_actual), pagina: int = 1, tamano: int = 25,
            segmento: str | None = None, tramo: str | None = None,
            propension: str | None = None, busqueda: str | None = None,
            producto: str | None = None, departamento: str | None = None,
            monto_min: float | None = None, monto_max: float | None = None,
            dias_min: int | None = None, dias_max: int | None = None,
            anio: int | None = None, mes: int | None = None):
    tamano = max(1, min(tamano, 200))
    f = _aplicar_filtros(_scored(u.empresa), segmento, tramo, propension, busqueda,
                         producto, departamento, monto_min, monto_max,
                         dias_min, dias_max, anio, mes)
    f = _ordenar_cartera(f)
    total = len(f)
    ini = (max(1, pagina) - 1) * tamano
    filas = f.iloc[ini:ini + tamano][[c for c in _COLS_CARTERA if c in f.columns]]
    return {"total": total, "pagina": pagina, "tamano": tamano,
            "filas": filas.to_dict("records")}


@app.get("/api/cartera/export.csv")
def cartera_export(u: Usuario = Depends(usuario_actual), segmento: str | None = None,
                   tramo: str | None = None, propension: str | None = None,
                   busqueda: str | None = None, producto: str | None = None,
                   departamento: str | None = None, monto_min: float | None = None,
                   monto_max: float | None = None, dias_min: int | None = None,
                   dias_max: int | None = None, anio: int | None = None,
                   mes: int | None = None):
    f = _aplicar_filtros(_scored(u.empresa), segmento, tramo, propension, busqueda,
                         producto, departamento, monto_min, monto_max,
                         dias_min, dias_max, anio, mes)
    f = _ordenar_cartera(f)
    buf = io.StringIO()
    f.to_csv(buf, index=False)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=cartera_priorizada.csv"})


@app.get("/api/informe/ejecutivo.pdf")
def informe_ejecutivo(u: Usuario = Depends(usuario_actual)):
    """Informe ejecutivo de cartera en PDF, con un clic — lo que el gerente
    de cobranzas lleva a su directorio. Idioma y moneda según el país del
    tenant; la empresa "principal" (datos del repo) lleva el disclaimer de
    demo sintética."""
    pdf = kinforme.generar_pdf(
        _scored(u.empresa), _gestiones(u.empresa), empresa=u.empresa,
        codigo_pais=_pais_de(u.empresa),
        datos_demo=(u.empresa == EMPRESA_DEFAULT))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition":
                             "attachment; filename=informe_ejecutivo.pdf"})


# ---------------------------------------------------------------------------
# Informe semanal por email (el scheduler vive en realtime/server.py —
# requiere ese proceso corriendo 24/7, igual que la campaña automática)
# ---------------------------------------------------------------------------
@app.get("/api/informe/programacion")
def informe_programacion(u: Usuario = Depends(solo_admin)):
    return {"activo": bool(kconfig.leer_extra("INFORME_EMAIL_ACTIVO")),
            "destino": kconfig.leer_extra("INFORME_EMAIL_DESTINO", "") or "",
            "smtp_configurado": bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_USER"))}


class ProgramacionIn(BaseModel):
    activo: bool
    destino: str = ""


@app.post("/api/informe/programacion")
def informe_programacion_guardar(datos: ProgramacionIn, u: Usuario = Depends(solo_admin)):
    destino = datos.destino.strip()
    if datos.activo and ("@" not in destino or "." not in destino.split("@")[-1]):
        raise HTTPException(400, "Ingresá un email de destino válido para activar el envío.")
    kconfig.guardar_extra("INFORME_EMAIL_ACTIVO", datos.activo)
    kconfig.guardar_extra("INFORME_EMAIL_DESTINO", destino)
    return {"activo": datos.activo, "destino": destino}


@app.post("/api/informe/enviar-ahora")
def informe_enviar_ahora(u: Usuario = Depends(solo_admin)):
    """Envío inmediato de prueba (valida el SMTP sin esperar al lunes)."""
    destino = (kconfig.leer_extra("INFORME_EMAIL_DESTINO", "") or "").strip()
    if not destino:
        raise HTTPException(400, "Configurá primero el email de destino y guardá.")
    r = kinforme.enviar_por_email(
        destino, _scored(u.empresa), _gestiones(u.empresa), empresa=u.empresa,
        codigo_pais=_pais_de(u.empresa),
        datos_demo=(u.empresa == EMPRESA_DEFAULT))
    if not r["ok"]:
        raise HTTPException(502, r["detalle"])
    return {"enviado": True, "destino": destino}


# ---------------------------------------------------------------------------
# Alta autoservicio de empresa (tenant) con datos de demostración
# ---------------------------------------------------------------------------
class AltaTenantIn(BaseModel):
    empresa: str


@app.post("/api/tenant/alta")
def tenant_alta(datos: AltaTenantIn, u: Usuario = Depends(solo_admin)):
    """Crea una empresa nueva con una muestra sintética de la demo, lista
    para entrar (login con la misma contraseña + nombre de empresa). Cierra
    el aprovisionamiento manual que quedaba documentado como pendiente."""
    import re as _re
    slug = _re.sub(r"[^a-z0-9-]", "-", datos.empresa.strip().lower())[:40].strip("-")
    if len(slug) < 3:
        raise HTTPException(400, "El nombre de empresa debe tener al menos 3 caracteres (letras/números).")
    if slug == EMPRESA_DEFAULT:
        raise HTTPException(400, "Ese nombre está reservado.")
    destino = _dir_tenant(slug)
    if os.path.exists(destino):
        raise HTTPException(409, f"La empresa '{slug}' ya existe.")

    scored = _scored(EMPRESA_DEFAULT).sample(n=2000, random_state=42)
    os.makedirs(destino, exist_ok=True)
    scored.to_csv(os.path.join(destino, "kobra_scored.csv"), index=False)
    g = _gestiones(EMPRESA_DEFAULT)
    if g is not None and "id_deudor" in g.columns:
        g[g["id_deudor"].isin(set(scored["id_deudor"]))].to_csv(
            os.path.join(destino, "kobra_gestiones.csv"), index=False)
    return {"empresa": slug, "deudores": int(len(scored)),
            "mensaje": (f"Empresa '{slug}' creada con datos de demostración. "
                        "Cerrá sesión y entrá con ese nombre de empresa.")}


@app.get("/api/deudor/{id_deudor}")
def deudor(id_deudor: str, u: Usuario = Depends(usuario_actual)):
    f = _scored(u.empresa)
    fila = f[f["id_deudor"] == id_deudor]
    if fila.empty:
        raise HTTPException(404, f"No existe el deudor {id_deudor}.")
    out = {}
    for k, v in fila.iloc[0].items():
        if pd.isna(v):
            out[k] = None
        elif hasattr(v, "item"):          # numpy escalar -> nativo Python
            out[k] = v.item()
        else:
            out[k] = v
    return out


@app.get("/api/agenda")
def agenda(limite: int = 200, u: Usuario = Depends(usuario_actual)):
    """Promesas vencidas a retomar HOY. Se devuelven las `limite` mas urgentes
    (mayor monto acordado primero, desempate por dias vencida): con carteras
    grandes la demo trae miles y renderizarlas todas congela la pagina ~15 s —
    el gestor igual trabaja de a una, empezando por las que mas importan."""
    g = _gestiones(u.empresa)
    if g is None or g.empty:
        return {"vencidas": [], "total": 0, "mostrando": 0}
    venc = kseg.promesas_incumplidas(g)
    total = int(len(venc))
    if total and {"monto_acordado", "dias_vencida"} <= set(venc.columns):
        venc = venc.sort_values(["monto_acordado", "dias_vencida"],
                                ascending=[False, False])
    limite = max(1, min(int(limite), 1000))
    venc = venc.head(limite)
    return {"total": total, "mostrando": int(len(venc)),
            "vencidas": venc.to_dict("records")}


@app.get("/api/gestores/resumen")
def gestores_resumen(u: Usuario = Depends(usuario_actual)):
    g = _gestiones(u.empresa)
    if g is None or g.empty:
        return {"ranking": [], "impacto": None}
    ranking = kanalitica.ranking_gestores(g).head(15)
    impacto = kanalitica.impacto_kobra(g)
    return {"ranking": ranking.reset_index().to_dict("records"),
            "impacto": {k: (v.to_dict("records") if isinstance(v, pd.DataFrame)
                            else (None if isinstance(v, float) and pd.isna(v) else v))
                        for k, v in (impacto or {}).items()
                        if not isinstance(v, pd.DataFrame)} if impacto else None}


def _cols_unicas(g, col):
    if g is None or col not in getattr(g, "columns", []):
        return []
    return sorted(g[col].dropna().astype(str).unique().tolist())


@app.get("/api/calidad/comparativa")
def calidad_comparativa(canal: str | None = None, tipo: str | None = None,
                        gestor: str | None = None, mes: str | None = None,
                        u: Usuario = Depends(usuario_actual)):
    """Performance Gestor IA vs Gestor Humano (calidad, conversión, recupero)
    a partir del registro de gestiones, con tableros extra: perfil por criterio
    (ítem de negociación), evolución mensual y potencial de mejora de la
    cobranza. Filtros opcionales canal/tipo/gestor/mes."""
    from kobra import calidad_gestion as kcalidad
    g = _gestiones(u.empresa)
    canales = _cols_unicas(g, "canal")
    meses = _cols_unicas(g, "mes")
    gestores = _cols_unicas(g, "gestor")

    # Filtros mes/gestor se aplican a la base; canal/tipo los maneja comparativa.
    base = g
    if base is not None:
        if mes and "mes" in base.columns:
            base = base[base["mes"].astype(str) == mes]
        if gestor and "gestor" in base.columns:
            base = base[base["gestor"].astype(str) == gestor]

    comp = kcalidad.comparativa(base, canal=canal, tipo=tipo)
    comp["canales"] = canales
    comp["meses"] = meses
    comp["gestores"] = gestores
    # Tableros nuevos (el perfil/mejora usan la base filtrada por mes/gestor;
    # la evolución ignora el mes porque es justamente la serie en el tiempo).
    comp["perfil"] = kcalidad.perfil_criterios(base, canal=canal, mes=None)
    comp["evolucion"] = kcalidad.evolucion(g, canal=canal)
    comp["mejora"] = kcalidad.mejora_potencial(base, canal=canal)
    return comp


class EvaluarGestionIn(BaseModel):
    transcripcion: str
    canal: str = "Llamada"


@app.post("/api/calidad/evaluar")
def calidad_evaluar(datos: EvaluarGestionIn, u: Usuario = Depends(usuario_actual)):
    """Evalúa la calidad de una gestión (transcripción de llamada o chat de
    WhatsApp) contra la rúbrica de 14 criterios (100 pts). Núcleo offline; si
    hay proveedor de IA configurado, recalibra como un supervisor real."""
    from kobra import calidad_gestion as kcalidad
    texto = (datos.transcripcion or "").strip()
    if len(texto) < 15:
        raise HTTPException(422, "Pegá una transcripción más larga para evaluar.")
    return kcalidad.evaluar(texto, canal=datos.canal)


def _transcript_desde_turnos(turnos) -> str:
    """Arma una transcripción 'Gestor:/Cliente:' a partir de los turnos ya
    transcritos + con rol corregido por contenido (ver voz.asignar_roles_por_contenido)."""
    lineas = []
    for t in turnos or []:
        texto = (t.get("texto") or "").strip()
        if not texto:
            continue
        hablante = t.get("hablante") or ""
        etiqueta = "Gestor" if str(hablante).lower().startswith(("gestor", "agente", "asesor", "operador")) else "Cliente"
        lineas.append(f"{etiqueta}: {texto}")
    return "\n".join(lineas)


_AVISO_SIN_WHISPER = (
    "Para transcribir y evaluar la llamada automáticamente hace falta una "
    "OPENAI_API_KEY (Whisper), que todavía no está configurada. Podés cargarla "
    "en Configuración, o pegar la transcripción en la pestaña «Evaluar texto». "
    "Igual podés escuchar la grabación acá arriba.")


@app.post("/api/calidad/evaluar-audio")
async def calidad_evaluar_audio(archivo: UploadFile = File(...), canal: str = "Llamada",
                                gestor: str | None = None, fecha: str | None = None,
                                u: Usuario = Depends(usuario_actual)):
    """Sube una grabación (.wav/.mp3), la transcribe por hablante (Whisper) y la
    evalúa contra la rúbrica de 14 criterios. Si no hay Whisper configurado,
    responde al toque (no procesa el audio en vano). El rol Gestor/Cliente se
    corrige por contenido, no por tono (que suele invertirlo)."""
    nombre = (archivo.filename or "").lower()
    if not nombre.endswith((".wav", ".mp3")):
        raise HTTPException(400, "Subí un archivo .wav o .mp3.")

    from kobra import voz as kvoz
    # Sin Whisper la transcripción sería vacía y diarizar es caro: cortamos ya.
    if not kvoz.whisper_disponible():
        return {"archivo": archivo.filename, "modo_transcripcion": "sin_whisper",
                "turnos": [], "evaluacion": None, "aviso": _AVISO_SIN_WHISPER}

    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(400, "El archivo llegó vacío.")

    scratch = os.path.join(DIR_DATOS, ".uploads")
    os.makedirs(scratch, exist_ok=True)
    import uuid
    ext = ".wav" if nombre.endswith(".wav") else ".mp3"
    base = os.path.join(scratch, f"cal_{uuid.uuid4().hex}")
    destino, liviano = base + ext, base + "_16k.wav"
    with open(destino, "wb") as f:
        f.write(contenido)

    procesar = destino
    try:
        from kobra import calidad_gestion as kcalidad
        # Downmix a mono 16 kHz: diariza/transcribe mucho más rápido.
        try:
            procesar = kvoz.preparar_liviano(destino, liviano)
        except Exception:
            procesar = destino
        idioma = kpaises.obtener(_pais_de(u.empresa)).idioma
        turnos, modo = kvoz.transcribir_llamada(procesar, idioma=idioma)
        turnos = kvoz.asignar_roles_por_contenido(turnos)
        transcripcion = _transcript_desde_turnos(turnos)
        if len(transcripcion.strip()) < 15:
            return {"archivo": archivo.filename, "modo_transcripcion": modo,
                    "turnos": turnos, "evaluacion": None, "aviso": _AVISO_SIN_WHISPER}
        evaluacion = kcalidad.evaluar(transcripcion, canal=canal)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"No se pudo procesar el audio: {e}")
    finally:
        for p in (destino, liviano):
            try:
                os.remove(p)
            except OSError:
                pass

    guardado = None
    if gestor and evaluacion:
        guardado = _guardar_calidad(u.empresa, gestor, fecha, canal,
                                    archivo.filename, evaluacion)
    return {"archivo": archivo.filename, "modo_transcripcion": modo,
            "turnos": turnos, "transcripcion": transcripcion, "evaluacion": evaluacion,
            "guardado": guardado}


@app.get("/api/calidad/fuentes")
def calidad_fuentes(u: Usuario = Depends(usuario_actual)):
    """Estado de las fuentes de grabaciones para calidad: subida manual (siempre
    activa) y conexión a un PBX/grabador tipo Avaya (requiere credenciales del
    cliente). Honesto: informa qué falta configurar, no simula una conexión."""
    avaya_host = os.environ.get("KOBRA_AVAYA_HOST", "")
    avaya_user = os.environ.get("KOBRA_AVAYA_USER", "")
    avaya_ok = bool(avaya_host and avaya_user)
    whisper_ok = bool(os.environ.get("OPENAI_API_KEY"))
    return {
        "manual": {"activo": True, "formatos": ["wav", "mp3"],
                   "transcripcion": "whisper" if whisper_ok else "no_config"},
        "avaya": {
            "activo": avaya_ok,
            "host": avaya_host if avaya_ok else "",
            "estado": "conectado" if avaya_ok else "sin_configurar",
            "detalle": ("Conector a central Avaya listo: las grabaciones del PBX "
                        "se importan y evalúan automáticamente.") if avaya_ok else
                       ("Para conectar la central Avaya (o cualquier grabador por API) "
                        "configurá KOBRA_AVAYA_HOST, KOBRA_AVAYA_USER y KOBRA_AVAYA_PASS "
                        "con las credenciales del cliente. Mientras tanto, subí las "
                        "grabaciones manualmente (.wav/.mp3)."),
        },
    }


def _archivo_calidad(empresa: str) -> str:
    base = os.path.join(DIR_DATOS, "data") if empresa == EMPRESA_DEFAULT else _dir_tenant(empresa)
    return os.path.join(base, "calidad_evaluaciones.csv")


def _leer_calidad(empresa: str):
    ruta = _archivo_calidad(empresa)
    if not os.path.exists(ruta):
        return None
    try:
        return pd.read_csv(ruta)
    except Exception:
        return None


def _guardar_calidad(empresa: str, gestor: str, fecha: str | None, canal: str,
                     archivo: str, evaluacion: dict) -> dict:
    """Acumula una evaluación de audio en el registro de calidad del tenant, para
    armar fichas de gestor por mes y su evolución."""
    from kobra import calidad_gestion as kcalidad
    import uuid
    if not fecha:
        fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fila = kcalidad.fila_evaluacion(gestor, fecha, canal, archivo, evaluacion,
                                    uuid.uuid4().hex[:12])
    ruta = _archivo_calidad(empresa)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    df = _leer_calidad(empresa)
    nueva = pd.DataFrame([fila])
    df = nueva if df is None else pd.concat([df, nueva], ignore_index=True)
    df.to_csv(ruta, index=False)
    return {"id": fila["id"], "gestor": gestor, "fecha": fecha,
            "puntaje_total": fila["puntaje_total"], "acumuladas": int(len(df))}


class GuardarCalidadIn(BaseModel):
    gestor: str
    fecha: str | None = None
    canal: str = "Llamada"
    transcripcion: str
    archivo: str = "Transcripción pegada"


@app.post("/api/calidad/guardar")
def calidad_guardar(datos: GuardarCalidadIn, u: Usuario = Depends(usuario_actual)):
    """Evalúa una transcripción y la ACUMULA en la ficha del gestor (para los
    tableros de calidad por gestor/mes y su evolución)."""
    from kobra import calidad_gestion as kcalidad
    texto = (datos.transcripcion or "").strip()
    if len(texto) < 15:
        raise HTTPException(422, "Pegá una transcripción más larga para evaluar.")
    if not (datos.gestor or "").strip():
        raise HTTPException(422, "Indicá el gestor para acumular la evaluación.")
    evaluacion = kcalidad.evaluar(texto, canal=datos.canal)
    guardado = _guardar_calidad(u.empresa, datos.gestor.strip(), datos.fecha,
                                datos.canal, datos.archivo, evaluacion)
    return {"evaluacion": evaluacion, "guardado": guardado}


@app.get("/api/calidad/evaluaciones")
def calidad_evaluaciones(gestor: str | None = None, mes: str | None = None,
                         u: Usuario = Depends(usuario_actual)):
    """Tableros de las evaluaciones de audio acumuladas: ranking por gestor,
    evolución mensual de la nota, promedio por criterio y el detalle. Filtros
    opcionales por gestor y mes."""
    from kobra import calidad_gestion as kcalidad
    df = _leer_calidad(u.empresa)
    resumen = kcalidad.resumen_evaluaciones(df, gestor=gestor, mes=mes)
    resumen["gestores"] = (sorted(df["gestor"].dropna().astype(str).unique().tolist())
                           if df is not None and "gestor" in df.columns else [])
    resumen["meses"] = (sorted(df["mes"].dropna().astype(str).unique().tolist())
                        if df is not None and "mes" in df.columns else [])
    return resumen


class PreguntaIn(BaseModel):
    pregunta: str


@app.post("/api/ayuda")
def ayuda(datos: PreguntaIn, u: Usuario = Depends(usuario_actual)):
    idioma = kpaises.obtener(_pais_de(u.empresa)).idioma
    return kayuda.responder(datos.pregunta, idioma=idioma)


@app.get("/api/paises")
def paises_catalogo(u: Usuario = Depends(usuario_actual)):
    """Catálogo LATAM (Fase 1 hispanohablante + Fase 2 Brasil) — ver docs/KOBRA_2_0.md."""
    return {"paises": kpaises.listar()}


@app.get("/api/tenant/pais")
def tenant_pais(u: Usuario = Depends(usuario_actual)):
    p = kpaises.obtener(_pais_de(u.empresa))
    return dict(codigo=p.codigo, nombre=p.nombre, moneda=p.moneda,
                simbolo=p.simbolo, locale=p.locale, idioma=p.idioma,
                nota_cumplimiento=p.nota_cumplimiento)


class PaisIn(BaseModel):
    codigo: str


@app.post("/api/tenant/pais")
def tenant_pais_guardar(datos: PaisIn, u: Usuario = Depends(solo_admin)):
    codigo = datos.codigo.upper()
    if codigo not in kpaises.CATALOGO:
        raise HTTPException(400, f"País '{datos.codigo}' no está en el catálogo LATAM.")
    _guardar_pais_de(u.empresa, codigo)
    p = kpaises.obtener(codigo)
    return dict(codigo=p.codigo, nombre=p.nombre, moneda=p.moneda,
                simbolo=p.simbolo, locale=p.locale, idioma=p.idioma,
                nota_cumplimiento=p.nota_cumplimiento)


@app.get("/api/config/estado")
def config_estado(u: Usuario = Depends(solo_admin)):
    return kconfig.estado()


class ConfigIn(BaseModel):
    claves: dict


@app.post("/api/config")
def config_guardar(datos: ConfigIn, u: Usuario = Depends(solo_admin)):
    validas = {k: v for k, v in datos.claves.items()
               if k in kconfig.CLAVES and isinstance(v, str) and v.strip()}
    if not validas:
        raise HTTPException(400, "No llegó ninguna clave válida para guardar.")
    kconfig.guardar(validas)
    return {"guardadas": sorted(validas)}


@app.get("/api/config/proveedor_ia")
def proveedor_ia_estado(u: Usuario = Depends(solo_admin)):
    """Con qué proveedor de IA (traé tu propia cuenta corporativa) razona el
    Asistente, el Copiloto y el Gestor IA — Claude, Gemini o ChatGPT/OpenAI."""
    kconfig.aplicar()
    return {"proveedor": kllm.proveedor_activo(), "proveedores": list(kllm.PROVEEDORES),
            "claves_configuradas": {p: kllm.disponible(proveedor=p) for p in kllm.PROVEEDORES}}


class ProveedorIAIn(BaseModel):
    proveedor: str


@app.post("/api/config/proveedor_ia")
def proveedor_ia_guardar(datos: ProveedorIAIn, u: Usuario = Depends(solo_admin)):
    if datos.proveedor not in kllm.PROVEEDORES:
        raise HTTPException(400, f"Proveedor '{datos.proveedor}' no soportado "
                                 f"(válidos: {', '.join(kllm.PROVEEDORES)}).")
    kllm.establecer_proveedor(datos.proveedor)
    return {"proveedor": datos.proveedor}


# ---------------------------------------------------------------------------
# Originación (Kobra 2.0 · Bloque 3) — mismo contrato para cliente directo y,
# cuando se active ese canal, para partners API (Bloque 5, hoy diferido).
# ---------------------------------------------------------------------------
_MODELO_ORIGINACION = None


def _originacion():
    """Modelo de originación entrenado (lazy singleton). Sin datos reales del
    cliente entrena sobre el dataset sintético de demo — el response lo dice."""
    global _MODELO_ORIGINACION
    if _MODELO_ORIGINACION is None:
        from kobra import originacion as korig
        df = korig.generar_solicitudes_sinteticas()
        _MODELO_ORIGINACION = korig.OriginacionModel().fit(df)
    return _MODELO_ORIGINACION


class SolicitudIn(BaseModel):
    solicitud: dict


@app.post("/api/originacion/score")
def originacion_score(datos: SolicitudIn, u: Usuario = Depends(usuario_actual)):
    modelo = _originacion()
    resultado = modelo.evaluar(datos.solicitud or {})
    return {**resultado, "modelo_demo": True,
            "metricas_modelo": modelo.metrics}


@app.get("/api/originacion/metricas")
def originacion_metricas(u: Usuario = Depends(usuario_actual)):
    return {**_originacion().metrics, "modelo_demo": True,
            "es_real": _modo_cartera(u.empresa) == "real"}


@app.get("/api/originacion/cola")
def originacion_cola(n: int = 15, u: Usuario = Depends(usuario_actual)):
    """Cola de solicitudes pendientes de decisión. UNA sola fuente de datos: el
    MISMO dataset que ve todo el dashboard (el que se carga en Configuración,
    real o demo). En modo real, la originación se deriva de ese dataset
    (mapeando sus columnas a las features del modelo, con supuestos honestos
    para lo que no venga); en demo, solicitudes sintéticas. No hay una carga
    aparte para esta pestaña."""
    import json as _json
    from kobra import originacion as korig
    modelo = _originacion()
    tope = max(5, min(n, 50))
    real = _modo_cartera(u.empresa) == "real"
    if real:
        # Mismo dataset del cliente que las demás pestañas, visto como solicitudes.
        sols, _mapeo = korig.preparar_solicitudes(_scored(u.empresa).head(tope))
        if korig.TARGET in sols.columns:
            sols = sols.drop(columns=[korig.TARGET])
        es_real = True
    else:
        sols = korig.generar_solicitudes_sinteticas(
            n=tope, semilla=1234).drop(columns=[korig.TARGET])
        es_real = False
    out = modelo.evaluar_lote(sols)
    if "fecha_solicitud" in out.columns:
        out["fecha_solicitud"] = pd.to_datetime(
            out["fecha_solicitud"], errors="coerce").dt.strftime("%Y-%m-%d")
    return {"solicitudes": _json.loads(out.to_json(orient="records")),
            "modelo_demo": not es_real, "es_real": es_real,
            "metricas_modelo": modelo.metrics}


@app.get("/api/nba/{id_deudor}")
def next_best_action(id_deudor: str, u: Usuario = Depends(usuario_actual)):
    """Next-best-action de cobranza para un deudor: a quién ya lo decide la
    prioridad de la cartera; esto responde POR QUÉ canal, con QUÉ estrategia
    y con qué guion — la salida del Agente Negociador, como contrato API."""
    f = _scored(u.empresa)
    fila = f[f["id_deudor"] == id_deudor]
    if fila.empty:
        raise HTTPException(404, f"No existe el deudor {id_deudor}.")
    r = fila.iloc[0]
    return {"id_deudor": id_deudor,
            "prioridad": int(r["prioridad"]),
            "probpago": float(r["probpago"]),
            "canal": r["canal_recomendado"],
            "estrategia": r["estrategia"],
            "descuento_recomendado": float(r["descuento_recomendado"]),
            "plan_cuotas": int(r["plan_cuotas"]) if pd.notna(r.get("plan_cuotas")) else None,
            "guion_sugerido": r["guion"],
            "motivo": r["motivo_probpago"]}


class CarteraEntranteIn(BaseModel):
    contactos: list[dict]


@app.post("/api/integracion/cartera")
def integracion_cartera(datos: CarteraEntranteIn, u: Usuario = Depends(solo_admin)):
    """API entrante para integradores: el core/ERP del cliente empuja su
    cartera como JSON (mismas columnas que el CSV: nombre, telefono,
    deuda/monto_deuda, dias_mora, …). Se normaliza con el mismo camino que
    la carga manual y queda en el directorio del tenant."""
    if not datos.contactos:
        raise HTTPException(400, "La lista de contactos llegó vacía.")
    contactos = kcartera.desde_dataframe(pd.DataFrame(datos.contactos))
    if not contactos:
        raise HTTPException(422, "Ningún contacto tenía un monto de deuda válido.")
    destino_dir = (os.path.join(DIR_DATOS, "data") if u.empresa == EMPRESA_DEFAULT
                   else _dir_tenant(u.empresa))
    os.makedirs(destino_dir, exist_ok=True)
    destino = os.path.join(destino_dir, "cartera_entrante.csv")
    pd.DataFrame(contactos).to_csv(destino, index=False)
    return {"recibidos": len(datos.contactos), "validos": len(contactos),
            "archivo": os.path.relpath(destino, DIR_DATOS)}


@app.get("/api/cartera/origen")
def cartera_origen(u: Usuario = Depends(usuario_actual)):
    """Honestidad de los números: de dónde salen los datos que se están
    mostrando — demo sintética (default) o la cartera real que el cliente
    subió. `hay_real` habilita el botón demo ON/OFF en el frontend."""
    meta = _origen_meta(u.empresa)
    modo = _modo_cartera(u.empresa)
    return {"tipo": modo, "modo": modo,
            "hay_real": os.path.exists(_archivo_real(u.empresa)),
            "archivo": meta.get("archivo"), "deudores": meta.get("deudores"),
            "cargado_en": meta.get("cargado_en")}


class ModoCarteraIn(BaseModel):
    modo: str


@app.post("/api/cartera/modo")
def cartera_modo(datos: ModoCarteraIn, u: Usuario = Depends(solo_admin)):
    """Botón demo ON/OFF: alterna qué cartera ve TODO el dashboard —
    'demo' (datos sintéticos) o 'real' (la que subió el cliente). Sin
    pérdida: la demo y la cartera real conviven; esto solo cambia cuál se
    sirve. 'real' solo se puede activar si ya hay una cartera subida."""
    modo = (datos.modo or "").strip().lower()
    if modo not in ("demo", "real"):
        raise HTTPException(400, "El modo debe ser 'demo' o 'real'.")
    if modo == "real" and not os.path.exists(_archivo_real(u.empresa)):
        raise HTTPException(400, "Todavía no subiste una cartera real para activar. "
                                 "Subí un CSV/Excel primero.")
    meta = _origen_meta(u.empresa)
    meta["modo"] = modo
    meta["tipo"] = modo   # compat con marcas viejas
    os.makedirs(os.path.dirname(_archivo_origen(u.empresa)), exist_ok=True)
    with open(_archivo_origen(u.empresa), "w", encoding="utf-8") as f:
        json.dump(meta, f)
    return {"tipo": modo, "modo": modo, "hay_real": os.path.exists(_archivo_real(u.empresa))}


_COLS_EXPORT_CARTERA = ["id_deudor", "segmento", "producto", "departamento", "tramo_mora",
                        "dias_mora", "monto_deuda", "score_buro", "contactabilidad",
                        "probpago", "decil", "segmento_propension", "estrategia",
                        "descuento_recomendado", "plan_cuotas", "canal_recomendado",
                        "valor_esperado_recupero", "prioridad", "pago", "guion",
                        "motivo_probpago"]


def _guardar_cartera_real(empresa: str, full: pd.DataFrame, etiqueta: str) -> pd.DataFrame:
    """Guarda la cartera real scoreada APARTE de la demo (no la pisa) y activa
    el modo 'real'. Devuelve el DataFrame exportado. Camino común del CSV/Excel
    y del import por SQL — así ambos se comportan igual."""
    export = full[[c for c in _COLS_EXPORT_CARTERA if c in full.columns]]
    destino = _archivo_real(empresa)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    export.round(4).to_csv(destino, index=False)
    with open(_archivo_origen(empresa), "w", encoding="utf-8") as f:
        json.dump({"modo": "real", "tipo": "real", "archivo": etiqueta,
                   "cargado_en": datetime.now(timezone.utc).isoformat(),
                   "deudores": int(len(export))}, f)
    return export


@app.post("/api/cartera/importar")
async def cartera_importar(archivo: UploadFile = File(...), u: Usuario = Depends(solo_admin)):
    """Sube un CSV/Excel con la cartera real (nombre, telefono, deuda[,
    dias_mora, ...]) y REEMPLAZA los datos de demo: se scorea con ProbPago,
    se aplica la estrategia del Agente Negociador, y el dashboard entero
    (KPIs, Cartera, Agenda) pasa a reflejar esta cartera. Sin límite de
    tamaño. Las features que no vienen en el archivo se completan con
    supuestos (ver kobra/cartera_manual.py::DEFAULTS) — no se inventa
    historial de pagos."""
    nombre = (archivo.filename or "").lower()
    if not nombre.endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(400, "Subí un archivo .csv o .xlsx.")
    contenido = await archivo.read()
    try:
        df_bruto = (pd.read_csv(io.BytesIO(contenido), dtype=str) if nombre.endswith(".csv")
                    else pd.read_excel(io.BytesIO(contenido), dtype=str))
    except Exception as e:
        raise HTTPException(400, f"No pude leer el archivo: {e}")

    # Se adapta solo a nombres de columna parecidos (MontoDeuda, Saldo Vencido,
    # Dívida, Total Debt…); mostramos que reconoció para que el cliente confíe.
    mapeo = kcartera.mapear_columnas(df_bruto.columns)
    try:
        full = kcartera.importar_y_scorear(df_bruto.fillna(""))
    except ValueError as e:
        raise HTTPException(422, str(e))

    export = _guardar_cartera_real(u.empresa, full, archivo.filename)
    detectadas = "; ".join(f"«{orig}» → {campo}" for orig, campo in mapeo.items())
    return {"deudores": int(len(export)),
            "cartera_total_uyu": float(export["monto_deuda"].sum()),
            "columnas_detectadas": mapeo,
            "mensaje": f"Cartera real cargada y activada: {len(export)} deudor(es). "
                      + (f"Reconocí tus columnas ({detectadas}). " if detectadas else "")
                      + "El dashboard ya refleja estos datos (podés volver a la demo "
                      "con el botón)."}


class ImportarSQLIn(BaseModel):
    conn_url: str
    consulta: str


@app.post("/api/cartera/importar-sql")
def cartera_importar_sql(datos: ImportarSQLIn, u: Usuario = Depends(solo_admin)):
    """Importa la cartera real directamente desde la base de datos del cliente
    (Postgres, MySQL, SQL Server, SQLite, Oracle… cualquiera que soporte
    SQLAlchemy), SIN límite de tamaño — trae toda la cartera que devuelva la
    consulta. Solo lectura: se rechaza cualquier consulta que no sea
    SELECT/WITH. Igual que el CSV, se scorea con ProbPago, se aplica la
    estrategia y se activa el modo 'real'. La URL de conexión no se loguea."""
    try:
        contactos = kcartera.desde_base_de_datos(datos.conn_url, datos.consulta)  # limite=None
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(400, f"No pude conectar o consultar la base: {e}")
    if not contactos:
        raise HTTPException(422, "La consulta no devolvió ninguna fila con un monto de "
                                 "deuda válido (columna 'deuda', 'monto' o 'monto_deuda').")
    try:
        full = kcartera.importar_y_scorear(pd.DataFrame(contactos))
    except ValueError as e:
        raise HTTPException(422, str(e))

    export = _guardar_cartera_real(u.empresa, full, "Base de datos (SQL)")
    return {"deudores": int(len(export)),
            "cartera_total_uyu": float(export["monto_deuda"].sum()),
            "mensaje": f"Cartera real importada desde la base y activada: {len(export)} "
                      "deudor(es). El dashboard ya refleja estos datos."}


@app.post("/api/voz/analizar")
async def voz_analizar(archivo: UploadFile = File(...), id_deudor: str | None = None,
                       u: Usuario = Depends(usuario_actual)):
    """Analiza una grabación de llamada real (.wav/.mp3) subida desde el
    dashboard: diarización (quién habla), emoción acústica (tono, energía,
    ritmo) y — si hay OPENAI_API_KEY para transcribir (Whisper) — el
    copiloto completo (calidad, técnicas, sugerencias en vivo). Si se pasa
    `id_deudor` de la cartera priorizada, usa su probpago/estrategia reales
    para contextualizar las sugerencias, igual que en Streamlit."""
    nombre = (archivo.filename or "").lower()
    if not nombre.endswith((".wav", ".mp3")):
        raise HTTPException(400, "Subí un archivo .wav o .mp3.")
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(400, "El archivo llegó vacío.")

    scratch = os.path.join(DIR_DATOS, ".uploads")
    os.makedirs(scratch, exist_ok=True)
    import uuid
    ext = ".wav" if nombre.endswith(".wav") else ".mp3"
    destino = os.path.join(scratch, f"voz_{uuid.uuid4().hex}{ext}")
    with open(destino, "wb") as f:
        f.write(contenido)

    probpago = estrategia = None
    if id_deudor:
        cartera = _scored(u.empresa)
        fila = cartera[cartera["id_deudor"] == id_deudor] if cartera is not None else pd.DataFrame()
        if not fila.empty:
            probpago = float(fila.iloc[0]["probpago"])
            estrategia = fila.iloc[0]["estrategia"]

    try:
        from kobra import voz as kvoz
        idioma = kpaises.obtener(_pais_de(u.empresa)).idioma
        res = kvoz.copiloto_desde_audio(destino, probpago=probpago,
                                        estrategia=estrategia, idioma=idioma)
    except Exception as e:
        raise HTTPException(400, f"No se pudo analizar el audio: {e}")
    finally:
        try:
            os.remove(destino)
        except OSError:
            pass

    return {"archivo": archivo.filename, "voz": res["voz"],
            "modo_transcripcion": res["modo_transcripcion"], "turnos": res["turnos"],
            "copiloto": res["copiloto"], "calidad": res["calidad"], "tecnicas": res["tecnicas"]}


# Deudor sintético por default de la demo del Gestor IA — el caso "Martín Viera"
# que se le muestra a un prospecto: 3 cuotas adeudadas, sueldo declarado, etc.
_DEUDOR_DEMO_GESTOR = {
    "id_deudor": "DEMO-001", "nombre": "Martín Viera", "telefono": "098576279",
    "monto_deuda": 120000, "dias_mora": 90, "cuotas_atrasadas": 3,
    "ingreso_estimado": 120000, "antiguedad_cliente_meses": 36, "score_buro": 640,
    "segmento": "Retail", "producto": "Préstamo personal", "departamento": "Montevideo",
}
# Guiones del "cliente" para la demo (voz y WhatsApp toman caminos distintos:
# objeción por cuotas vs. pedido de descuento) — muestran cómo el Gestor IA
# escala la oferta y cierra. El admin puede editar/mandar sus propios mensajes.
_GUION_DEMO = {
    "Llamada": ["Sí, con él. Pero estoy muy complicado este mes, no me alcanza.",
                "¿No hay forma de pagarlo en cuotas? De una sola vez no puedo.",
                "Bueno, esa sí la puedo. Dale, coordinemos."],
    "WhatsApp": ["Hola sí soy yo",
                 "Uh, es un montón ahora. ¿Me hacen algún descuento si pago junto?",
                 "Perfecto, con ese descuento lo pago hoy. Acepto."],
}


class GestorDemoIn(BaseModel):
    canal: str = "Llamada"                 # "Llamada" (voz) | "WhatsApp" (chatbot)
    mensajes: list[str] | None = None      # guion del cliente; None = el de demo
    deudor: dict | None = None             # deudor a scorear; None = Martín Viera demo


@app.post("/api/gestor-ia/demo")
def gestor_ia_demo(datos: GestorDemoIn, u: Usuario = Depends(usuario_actual)):
    """Corre una negociación COMPLETA del Gestor IA (mismo motor que producción)
    y devuelve todos los turnos + las conclusiones que van al ERP. Para
    mostrarle a un prospecto, en vivo, cómo el agente negocia por voz o
    WhatsApp — sin necesidad de Twilio ni un teléfono real (Twilio solo
    transporta la voz/mensaje; la lógica de negociación es esta)."""
    from kobra.gestor_ia import SesionGestorIA, interpretar
    canal = "WhatsApp" if str(datos.canal).lower().startswith("w") else "Llamada"
    bruto = pd.DataFrame([datos.deudor or _DEUDOR_DEMO_GESTOR])
    try:
        full = kcartera.importar_y_scorear(bruto.astype(str))
    except ValueError as e:
        raise HTTPException(422, str(e))
    brief = kcartera.brief_desde_fila(full.iloc[0])

    ses = SesionGestorIA(id_deudor=brief["id_deudor"], canal=canal,
                         gestor_id="IA01" if canal == "Llamada" else "IA02",
                         usar_claude=False, brief=dict(brief))
    guion = datos.mensajes if datos.mensajes is not None else _GUION_DEMO[canal]
    turnos = [{"quien": "gestor", "texto": ses.responder(None)["texto"]}]
    for msg in guion:
        i = interpretar(msg)
        turnos.append({"quien": "cliente", "texto": msg,
                       "senales": [k for k in ("acepta", "pide_cuotas", "pide_menos",
                                   "dificultad", "enojo", "negativa_dura", "pide_humano")
                                   if i.get(k)],
                       "sentimiento": round(i["sentimiento"], 2),
                       "emociones": i["emociones"]})
        r = ses.responder(msg)
        turnos.append({"quien": "gestor", "texto": r["texto"]})
        if r["fin"]:
            break
    e = ses.campos_erp
    return {
        "canal": canal,
        "brief": {k: brief[k] for k in ("nombre", "telefono", "monto_deuda", "probpago",
                  "estrategia", "descuento_recomendado", "plan_cuotas", "segmento_propension")},
        "motivo_probpago": full.iloc[0].get("motivo_probpago", ""),
        "turnos": turnos,
        "conclusion": {
            "resultado": e.get("resultado"),
            "monto_acordado": e.get("monto_acordado"),
            "oferta": e.get("oferta_aceptada"),
            "fecha_promesa": e.get("fecha_promesa"),
            "calidad_gestion": e.get("calidad_gestion"),
            "clima_cliente": e.get("clima_cliente"),
            "emociones": e.get("emociones"),
            "tecnicas": e.get("tecnicas"),
            "turnos": e.get("turnos"),
        },
    }


# --- Frontend compilado, si existe ------------------------------------------
# Orden de búsqueda: (1) KOBRA_UI_DIST explícito (lo setea el lanzador owner
# apuntando a owner/ui_dist, un build ya compilado y versionado, para no
# depender de Node al correr desde código); (2) el build normal de Vite.
_DIST_CANDIDATOS = [
    os.environ.get("KOBRA_UI_DIST", ""),
    os.path.join(ROOT, "webapp", "frontend", "dist"),
]
for _d in _DIST_CANDIDATOS:
    if _d and os.path.isdir(_d):
        app.mount("/", StaticFiles(directory=_d, html=True), name="frontend")
        break
