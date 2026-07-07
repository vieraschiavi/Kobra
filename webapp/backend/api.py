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
import os
import sys
import time

import pandas as pd
from fastapi import Depends, FastAPI, Header, HTTPException, Response
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
from kobra import registro as kregistro            # noqa: E402
from kobra import seguimiento as kseg              # noqa: E402

kconfig.aplicar()

TOKEN_TTL_SEG = 12 * 3600
EMPRESA_DEFAULT = "principal"


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
    return os.path.join(ROOT, "data", "tenants", empresa)


def _datos_de(empresa: str) -> dict:
    """Rutas de datos del tenant. 'principal' = los datos del repo."""
    if empresa == EMPRESA_DEFAULT:
        return {"scored": os.path.join(ROOT, "outputs", "kobra_scored.csv"),
                "gestiones": os.path.join(ROOT, "data", "kobra_gestiones.csv")}
    d = _dir_tenant(empresa)
    return {"scored": os.path.join(d, "kobra_scored.csv"),
            "gestiones": os.path.join(d, "kobra_gestiones.csv")}


def _scored(empresa: str) -> pd.DataFrame:
    ruta = _datos_de(empresa)["scored"]
    if not os.path.exists(ruta):
        raise HTTPException(404, f"La empresa '{empresa}' no tiene cartera scoreada cargada.")
    return pd.read_csv(ruta)


def _gestiones(empresa: str) -> pd.DataFrame | None:
    ruta = _datos_de(empresa)["gestiones"]
    return pd.read_csv(ruta) if os.path.exists(ruta) else None


def _aplicar_filtros(df: pd.DataFrame, segmento: str | None, tramo: str | None,
                     propension: str | None, busqueda: str | None) -> pd.DataFrame:
    if segmento:
        df = df[df["segmento"] == segmento]
    if tramo:
        df = df[df["tramo_mora"] == tramo]
    if propension:
        df = df[df["segmento_propension"] == propension]
    if busqueda:
        df = df[df["id_deudor"].str.contains(busqueda, case=False, na=False)]
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


@app.post("/api/auth/login")
def auth_login(datos: LoginIn):
    if not kauth.configurado():
        raise HTTPException(409, "Todavía no hay contraseña de administrador creada — "
                                 "abrí el dashboard una vez para el primer arranque.")
    rol = None
    for candidato in ("admin", "gestor"):
        if kauth.tiene_password(candidato) and kauth.verificar_password(candidato, datos.password):
            rol = candidato
            break
    if not rol:
        raise HTTPException(401, "Contraseña incorrecta.")
    return {"token": _emitir_token(rol, datos.empresa), "rol": rol,
            "empresa": datos.empresa}


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


@app.get("/api/cartera")
def cartera(u: Usuario = Depends(usuario_actual), pagina: int = 1, tamano: int = 25,
            segmento: str | None = None, tramo: str | None = None,
            propension: str | None = None, busqueda: str | None = None):
    tamano = max(1, min(tamano, 200))
    f = _aplicar_filtros(_scored(u.empresa), segmento, tramo, propension, busqueda)
    f = f.sort_values("prioridad")
    total = len(f)
    ini = (max(1, pagina) - 1) * tamano
    filas = f.iloc[ini:ini + tamano][[c for c in _COLS_CARTERA if c in f.columns]]
    return {"total": total, "pagina": pagina, "tamano": tamano,
            "filas": filas.to_dict("records")}


@app.get("/api/cartera/export.csv")
def cartera_export(u: Usuario = Depends(usuario_actual), segmento: str | None = None,
                   tramo: str | None = None, propension: str | None = None,
                   busqueda: str | None = None):
    f = _aplicar_filtros(_scored(u.empresa), segmento, tramo, propension, busqueda)
    f = f.sort_values("prioridad")
    buf = io.StringIO()
    f.to_csv(buf, index=False)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=cartera_priorizada.csv"})


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
def agenda(u: Usuario = Depends(usuario_actual)):
    g = _gestiones(u.empresa)
    if g is None or g.empty:
        return {"vencidas": [], "total": 0}
    venc = kseg.promesas_incumplidas(g)
    return {"total": int(len(venc)), "vencidas": venc.to_dict("records")}


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


class PreguntaIn(BaseModel):
    pregunta: str


@app.post("/api/ayuda")
def ayuda(datos: PreguntaIn, u: Usuario = Depends(usuario_actual)):
    return kayuda.responder(datos.pregunta)


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
    destino_dir = (os.path.join(ROOT, "data") if u.empresa == EMPRESA_DEFAULT
                   else _dir_tenant(u.empresa))
    os.makedirs(destino_dir, exist_ok=True)
    destino = os.path.join(destino_dir, "cartera_entrante.csv")
    pd.DataFrame(contactos).to_csv(destino, index=False)
    return {"recibidos": len(datos.contactos), "validos": len(contactos),
            "archivo": os.path.relpath(destino, ROOT)}


# --- Frontend compilado (webapp/frontend/dist), si existe -------------------
_DIST = os.path.join(ROOT, "webapp", "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
