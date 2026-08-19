# © 2026 Martín Viera. Todos los derechos reservados.

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

import hmac
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import pandas as pd
import portalocker
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from backend_venta import licencias as klicencias  # noqa: E402
from kobra import analitica as kanalitica  # noqa: E402
from kobra import autenticacion as kauth  # noqa: E402
from kobra import ayuda as kayuda  # noqa: E402
from kobra import cartera_manual as kcartera  # noqa: E402
from kobra import config as kconfig  # noqa: E402
from kobra import cuentas_por_cobrar as kcxc  # noqa: E402
from kobra import gobernanza as kgob  # noqa: E402
from kobra import informe_ejecutivo as kinforme  # noqa: E402
from kobra import limitador as klimite  # noqa: E402
from kobra import llm as kllm  # noqa: E402
from kobra import medidas as kmedidas  # noqa: E402
from kobra import owner as kowner  # noqa: E402
from kobra import paises as kpaises  # noqa: E402
from kobra import plan as kplan  # noqa: E402
from kobra import rutas as krutas  # noqa: E402
from kobra import seguimiento as kseg  # noqa: E402

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
# Marca persistida cuando el dueño desbloquea con su credencial (ver
# kobra/owner.py). Sin esto, el desbloqueo duraría solo hasta cerrar la app.
_CLAVE_OWNER = "KOBRA_OWNER_ACTIVADO"


def _es_owner() -> bool:
    """¿Corre como la copia del dueño?

    Dos vías, y las dos tienen que valer en caliente:
      * `KOBRA_OWNER=1` — lo exporta el launcher cuando el paquete es la
        edición Owner (decisión de build).
      * la credencial `mail|codigo` activada desde la propia app, que queda
        guardada en la config del usuario. Esta es la que permite tener una
        copia 100% operativa a partir del instalador PÚBLICO, sin un build
        aparte.

    Se consulta en cada llamada y no una vez al importar: si fuera una
    constante, desbloquear owner no surtiría efecto hasta reiniciar la app.
    """
    return MODO_OWNER or bool(kconfig.leer_extra(_CLAVE_OWNER))


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
    except Exception as e:
        # `from e` deja la causa real (firma rota, vencido, malformado) en el
        # log del servidor sin exponerla al cliente, que sigue viendo el mismo
        # mensaje. Sin esto, el traceback dice solo "During handling of the
        # above exception, another exception occurred" y se pierde cuál era.
        raise HTTPException(401, "Token inválido o vencido — iniciá sesión de nuevo.") from e
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


# ---------------------------------------------------------------------------
# Gobernanza de datos (módulo de la suite)
# ---------------------------------------------------------------------------
def _hay_gobernanza() -> bool:
    """¿El plan incluye el módulo?

    Se consulta con `permite` y no con `exigir` porque acá NO se quiere cortar:
    quien no compró gobernanza tiene que seguir viendo su cartera igual que
    siempre. El módulo agrega protección, no la condiciona.
    """
    return kplan.permite("gobernanza")


def _proteger(df: pd.DataFrame, rol: str) -> pd.DataFrame:
    """Enmascara según el rol, si el plan incluye gobernanza.

    Sin el módulo devuelve los datos tal cual, que es como Kobra se comportó
    siempre: activar la protección para quien no la compró le cambiaría el
    producto de golpe sin haber pedido nada.
    """
    if not _hay_gobernanza():
        return df
    return kgob.enmascarar(df, rol)


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
        # `str.contains` trata el argumento como REGEX por default. Es una
        # caja de búsqueda de texto libre, no un campo de regex — un usuario
        # que pega/tipea algo con paréntesis desbalanceados (p. ej. copiar un
        # id como "ID(005") provocaba un ValueError sin manejar → 500. Se
        # busca el texto literal, no un patrón.
        df = df[df["id_deudor"].astype(str).str.contains(
            re.escape(busqueda), case=False, na=False)]
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
# Exportación a Excel
# ---------------------------------------------------------------------------
_MARCA_NAVY = "#081527"


def _hoy_str() -> str:
    import datetime as _dt
    return _dt.date.today().isoformat()


# Columnas cuyo contenido es dinero, porcentaje o fecha. Se detectan por nombre
# porque los datasets del cliente traen nombres distintos a los de la demo, y
# un Excel donde los montos salen como "1234567.891" no lo usa nadie.
_PATRON_MONTO = ("monto", "saldo", "deuda", "recupero", "importe", "cuota",
                 "valor", "capital", "pago")
_PATRON_PCT = ("tasa", "porcentaje", "prob", "propension", "conversion", "pct")
_PATRON_FECHA = ("fecha", "vencim", "cargado", "alta")


def _excel_formateado(hojas: dict, titulo: str = "") -> bytes:
    """DataFrames a Excel con formato de informe, no un volcado crudo.

    Encabezado de marca, primera fila congelada, autofiltro, anchos calculados
    sobre el contenido real y formato por tipo de columna: miles y dos decimales
    para dinero, porcentaje para tasas, fecha corta para fechas. Es la
    diferencia entre un export que se manda a gerencia y uno que hay que
    reformatear a mano cada vez.
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xl:
        libro = xl.book
        f_titulo = libro.add_format({
            "bold": True, "font_size": 13, "font_color": "#FFFFFF",
            "bg_color": _MARCA_NAVY, "valign": "vcenter"})
        f_encab = libro.add_format({
            "bold": True, "font_color": "#FFFFFF", "bg_color": _MARCA_NAVY,
            "border": 1, "border_color": "#2a4160", "text_wrap": True,
            "valign": "vcenter"})
        f_monto = libro.add_format({"num_format": "#,##0.00"})
        f_pct = libro.add_format({"num_format": "0.0%"})
        f_fecha = libro.add_format({"num_format": "yyyy-mm-dd"})
        f_total = libro.add_format({"bold": True, "top": 2,
                                    "num_format": "#,##0.00"})
        f_total_txt = libro.add_format({"bold": True, "top": 2})

        for nombre, df in hojas.items():
            df = pd.DataFrame(df)
            # Excel corta los nombres de hoja a 31 caracteres y no acepta []:*?/\
            hoja = re.sub(r"[\[\]:*?/\\]", "-", str(nombre))[:31] or "Datos"
            fila0 = 2 if titulo else 0
            df.to_excel(xl, sheet_name=hoja, index=False, startrow=fila0)
            ws = xl.sheets[hoja]
            if titulo:
                ws.merge_range(0, 0, 0, max(0, len(df.columns) - 1), titulo,
                               f_titulo)
                ws.set_row(0, 24)
            if df.empty:
                ws.write(fila0, 0, "Sin datos para exportar", f_encab)
                continue

            for col, columna in enumerate(df.columns):
                ws.write(fila0, col, str(columna), f_encab)
                bajo = str(columna).lower()
                serie = df[columna]
                if any(p in bajo for p in _PATRON_FECHA):
                    fmt = f_fecha
                elif any(p in bajo for p in _PATRON_PCT):
                    fmt = f_pct
                elif any(p in bajo for p in _PATRON_MONTO):
                    fmt = f_monto
                else:
                    fmt = None
                # Ancho segun el contenido real, con techo para que una nota
                # larga no haga una columna de 300 caracteres.
                largo = max([len(str(columna))] +
                            [len(str(v)) for v in serie.head(200)])
                ws.set_column(col, col, min(max(10, largo + 2), 42), fmt)

            ws.freeze_panes(fila0 + 1, 0)
            ws.autofilter(fila0, 0, fila0 + len(df), len(df.columns) - 1)

            # Fila de totales para las columnas de dinero: sin ella hay que
            # sumar a mano justo lo que se va a mirar primero.
            fila_total = fila0 + len(df) + 1
            escribio = False
            for col, columna in enumerate(df.columns):
                bajo = str(columna).lower()
                # Solo dinero. Una tasa NO se suma: "tasa_recupero" contiene
                # "recupero" y entraba por la ventana, dando un total de 2,64
                # que no significa nada y ensucia el informe.
                if any(p in bajo for p in _PATRON_PCT):
                    continue
                if any(p in bajo for p in _PATRON_MONTO) and \
                        pd.api.types.is_numeric_dtype(df[columna]):
                    letra = _letra_col(col)
                    ws.write_formula(
                        fila_total, col,
                        f"=SUM({letra}{fila0 + 2}:{letra}{fila0 + 1 + len(df)})",
                        f_total)
                    escribio = True
            if escribio:
                ws.write(fila_total, 0, "TOTAL", f_total_txt)
    return buf.getvalue()


def _letra_col(indice: int) -> str:
    """0 → A, 25 → Z, 26 → AA. Excel no usa índices en las fórmulas."""
    letras = ""
    indice += 1
    while indice:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
def _detalle_sin_rutas(e: Exception, limite: int = 160) -> str:
    """Mensaje de la excepción sin las rutas del servidor.

    Probado con un archivo que no era audio: la respuesta al usuario era
    `Error opening '/home/.../.uploads/voz_c298d20c…wav': Format not
    recognised.` — le filtra al cliente la ruta interna del servidor y le dice,
    en inglés y en jerga de librería, algo que no puede accionar. Se conserva
    la causa (sirve para diagnosticar) pero sin rutas y acotada.
    """
    import re as _re
    txt = " ".join(str(e).split())
    # Rutas POSIX (/home/…/x.wav) y Windows (C:\Users\…\x.xlsx), con o sin
    # comillas alrededor. Se exige al menos una barra para no confundir una
    # fracción o una fecha con una ruta.
    txt = _re.sub(r"""['"]?(?:[A-Za-z]:)?[\\/][^\s'"]*[\\/][^\s'"]*['"]?""",
                  "el archivo", txt)
    return (txt[:limite] + "…") if len(txt) > limite else txt


def _sanear(valor):
    """Reemplaza NaN e infinitos por None, recursivamente.

    Bug real: la Cartera priorizada devolvía **Error 500** contra un dataset
    del cliente. La causa no estaba en la consulta sino en la serialización:

        ValueError: Out of range float values are not JSON compliant

    JSON no tiene forma de representar NaN ni infinito, y Starlette serializa
    con `allow_nan=False`, así que **una sola celda vacía** en cualquier
    columna numérica tumba la respuesta entera — no la fila, la pantalla
    completa. Con datos sintéticos nunca pasa, porque el generador no deja
    huecos; con una cartera real aparece en cuanto falta un monto o una fecha.

    Se aplica a nivel de aplicación y no en un endpoint suelto a propósito: el
    mismo defecto acecha en cualquier respuesta armada con `to_dict("records")`
    —KPIs, agenda, gestores— y arreglarlos de a uno deja los que vengan.
    """
    if isinstance(valor, float):
        return None if (valor != valor or valor in (float("inf"), float("-inf"))) else valor
    if isinstance(valor, dict):
        return {k: _sanear(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_sanear(v) for v in valor]
    return valor


class JSONLimpia(JSONResponse):
    """JSONResponse que nunca revienta por un NaN que se coló en los datos."""

    def render(self, content) -> bytes:
        return super().render(_sanear(content))


app = FastAPI(title="MV Kobra AI · API", version="1.0",
              default_response_class=JSONLimpia)
# Orden importa: Starlette envuelve con el ÚLTIMO `add_middleware` por AFUERA
# de los anteriores, así que el que se agrega último es el que ve la request
# primero y la respuesta última. `LimitadorGeneral` responde el 429 llamando
# a `send()` directo, sin pasar por nada agregado ANTES que él — así que si
# CORS se agregara antes (como estaba), un 429 salía sin cabeceras CORS: para
# cualquier caller cross-origin (dev en otro puerto, un ERP integrado, una
# app), el navegador lo mostraba como "Failed to fetch" genérico en vez del
# `detail`/`Retry-After` real. Confirmado con TestClient antes del fix
# (`Access-Control-Allow-Origin: None` en la respuesta 429) y después
# (la cabecera aparece). `LimitadorGeneral` va primero para que CORS quede
# más afuera y decore CUALQUIER respuesta que salga, incluida esa.
app.add_middleware(klimite.LimitadorGeneral)
# Red de seguridad general: cubre TODO endpoint público (48+ en este archivo),
# no solo login/licencia/setup, que ya tienen su freno más estricto aparte.
# CORS restringido, no `*`. La interfaz se sirve desde ESTE mismo backend
# (el `StaticFiles` del final del archivo), así que el uso normal es
# same-origin y no necesita CORS en absoluto. Abrirlo a `*` habilitaba un
# ataque concreto sobre la instalación de escritorio, donde el backend queda
# escuchando en localhost:
#
#   1. El usuario instala la app y todavía no configuró su contraseña.
#   2. Visita cualquier página web.
#   3. Esa página hace POST a http://localhost:<puerto>/api/auth/setup.
#   4. Se queda con el admin de la instalación.
#
# El POST lleva `Content-Type: application/json`, así que el navegador hace
# preflight — y con `allow_origins=["*"]` el preflight pasaba. Con la lista
# de abajo, el navegador corta el pedido antes de que salga.
#
# Se permiten los orígenes de desarrollo (el dev server de Vite) y los que la
# empresa declare en KOBRA_CORS_ORIGINS, separados por coma, para el caso de
# servir la interfaz desde otro dominio.
_CORS_DEV = ["http://localhost:5173", "http://127.0.0.1:5173"]
_CORS_ORIGINS = [o.strip() for o in os.environ.get("KOBRA_CORS_ORIGINS", "").split(",")
                 if o.strip()] or _CORS_DEV
app.add_middleware(CORSMiddleware, allow_origins=_CORS_ORIGINS,
                   allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Lo que incluye el plan contratado
# ---------------------------------------------------------------------------
# `kobra/plan.py` decide; acá solo se traduce a HTTP. Dos códigos distintos a
# propósito, porque son dos problemas distintos para el que llama:
#   403 → tu plan nunca incluyó esto (comprar otro plan).
#   402 → tu plan lo incluye pero se te acabó el cupo del mes (esperar al mes
#         que viene o mejorar el plan). 402 Payment Required es exactamente
#         este caso, y deja distinguirlo de un permiso denegado.
@app.exception_handler(kplan.FeatureNoIncluida)
def _feature_no_incluida(request: Request, exc: kplan.FeatureNoIncluida):
    return JSONResponse(status_code=403,
                        content={"detail": exc.mensaje, "plan": exc.estado,
                                 "motivo": "feature_no_incluida"})


@app.exception_handler(kplan.CupoAgotado)
def _cupo_agotado(request: Request, exc: kplan.CupoAgotado):
    return JSONResponse(status_code=402,
                        content={"detail": exc.mensaje, "plan": exc.estado,
                                 "motivo": "cupo_agotado"})


# ---------------------------------------------------------------------------
# Cabeceras de seguridad
# ---------------------------------------------------------------------------
# La API devuelve JSON, CSV, XLSX y PDF con datos de deudores. Sin estas
# cabeceras el navegador queda libre de adivinar el tipo de un archivo subido
# por el cliente (`X-Content-Type-Options`) y de mandar la URL completa —con el
# id del deudor adentro— a cualquier sitio externo al que se navegue después
# (`Referrer-Policy`).
CABECERAS_SEGURIDAD = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Resource-Policy": "same-site",
}
# La CSP depende de QUÉ se está sirviendo. `/api/*` es una API: no ejecuta
# nada, así que `default-src 'none'`. Pero este MISMO proceso también sirve la
# app React compilada (el mount de StaticFiles al final del archivo) — y con
# `'none'` el navegador se niega a cargar el JS/CSS de la propia app: la
# ventana queda con el título puesto y la pantalla NEGRA. Así salió el
# instalador Owner v1.3.0 — el smoke test del workflow solo pegaba a la API,
# nunca miró si la interfaz renderizaba. Para la UI: todo local (`'self'`,
# Vite no usa CDN), `data:`/`blob:` para gráficos e íconos embebidos, y
# `'unsafe-inline'` solo en estilos (React pone estilos inline; scripts
# inline siguen bloqueados, que es lo que importa contra XSS).
CSP_API = "default-src 'none'; frame-ancestors 'none'"
# `media-src` con blob: no es opcional: la pestaña Calidad reproduce la
# grabación subida con <audio src={URL.createObjectURL(...)}> — sin la
# directiva, `default-src 'self'` bloquea el blob y el reproductor queda
# GRIS con el play muerto (bug reportado en v1.3.1/1.3.2).
CSP_UI = ("default-src 'self'; script-src 'self'; "
          "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
          "media-src 'self' data: blob:; "
          "font-src 'self' data:; connect-src 'self'; object-src 'none'; "
          "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


@app.middleware("http")
async def _cabeceras_seguridad(request: Request, call_next):
    respuesta = await call_next(request)
    for k, v in CABECERAS_SEGURIDAD.items():
        respuesta.headers.setdefault(k, v)
    csp = CSP_API if request.url.path.startswith("/api") else CSP_UI
    respuesta.headers.setdefault("Content-Security-Policy", csp)
    return respuesta


# ---------------------------------------------------------------------------
# Límite de intentos en la puerta pública
# ---------------------------------------------------------------------------
# Estos tres endpoints son los únicos que aceptan un secreto sin tener sesión
# —contraseña de admin y token de licencia—, así que son los únicos que se
# pueden probar a fuerza bruta. Cada uno lleva su propio cubo: gastar los
# intentos de licencia no puede dejar afuera a quien está intentando entrar.
_LIMITE_LOGIN = klimite.Limitador()
_LIMITE_LICENCIA = klimite.Limitador()
_LIMITE_SETUP = klimite.Limitador()


def _frenar(limitador: klimite.Limitador, request: Request, accion: str) -> str:
    """Consume un intento o corta con 429. Devuelve la clave, para poder
    perdonar el intento si resultó correcto."""
    clave = f"{accion}:{klimite.ip_de(request)}"
    try:
        limitador.intentar(clave)
    except klimite.LimiteIntentos as e:
        raise HTTPException(
            429,
            f"Demasiados intentos. Esperá {e.espera_seg} segundos y probá de nuevo.",
            headers={"Retry-After": str(e.espera_seg)}) from e
    return clave


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
    if MODO_STANDALONE and not _es_owner():
        raise HTTPException(404, "No encontrado.")


@app.get("/api/auth/estado")
def auth_estado():
    """Sin auth: el login lo consulta al arrancar para saber si mostrar el
    formulario de primer arranque (crear la contraseña de admin) o el de
    ingreso normal. En la copia de un cliente (standalone) no aplica: ahí se
    entra con licencia, así que informa que la puerta es esa."""
    if MODO_STANDALONE and not _es_owner():
        return {"configurado": True, "gestor_configurado": False,
                "por_licencia": True}
    return {"configurado": kauth.configurado(),
            "gestor_configurado": kauth.tiene_password("gestor"),
            "por_licencia": False}


class SetupIn(BaseModel):
    password: str
    empresa: str = EMPRESA_DEFAULT


@app.post("/api/auth/setup")
def auth_setup(datos: SetupIn, request: Request):
    """Primer arranque: crea la contraseña de administrador desde la propia
    webapp (antes había que abrir el dashboard Streamlit, imposible en hosting).
    Solo funciona si TODAVÍA no hay admin — si ya existe, devuelve 409 para no
    permitir reset sin autenticación. Deja la sesión iniciada.

    No existe en la copia instalada de un cliente: ahí se entra por licencia."""
    _frenar(_LIMITE_SETUP, request, "setup")
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
def auth_login(datos: LoginIn, request: Request):
    # El freno va ANTES de verificar: si se comprobara primero la contraseña,
    # el atacante ya habría conseguido lo que buscaba (saber si acertó) y el
    # límite solo le ahorraría trabajo al servidor, no se lo negaría a él.
    clave = _frenar(_LIMITE_LOGIN, request, "login")
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
    # Acertó: se le devuelve el intento. El límite castiga el tanteo, no al
    # usuario que se equivocó una vez y después entró bien.
    _LIMITE_LOGIN.perdonar(clave)
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
    if _es_owner():
        return {"standalone": True, "activa": True, "owner": True,
                "plan": "owner", "trial": False, "dias_restantes": None}
    return {"standalone": True, **_estado_licencia(kconfig.leer_extra(_CLAVE_LICENCIA))}


@app.get("/api/plan")
def plan_estado(u: Usuario = Depends(usuario_actual)):
    """Qué incluye el plan y cuánto queda del cupo del mes.

    Lo consulta la app para mostrar el chip de consumo y el aviso del 80 %.
    Va con sesión: el consumo del mes es información del cliente, no algo
    que tenga que poder leer cualquiera que llegue al puerto."""
    return kplan.estado()


@app.post("/api/licencia/owner-login")
def licencia_owner_login():
    """Entrada directa de la copia del owner: emite el token de admin sin
    licencia ni contraseña. Solo existe cuando el launcher local corre con
    KOBRA_OWNER=1 (server en 127.0.0.1); en hosted o en la copia de un
    cliente devuelve 404 como si el endpoint no existiera."""
    if not (MODO_STANDALONE and _es_owner()):
        raise HTTPException(404, "No encontrado.")
    return {"token": _emitir_token("admin", EMPRESA_DEFAULT), "rol": "admin",
            "empresa": EMPRESA_DEFAULT}


@app.post("/api/licencia/activar")
def licencia_activar(datos: LicenciaIn, request: Request):
    # Un token de licencia es un secreto que se puede tantear: sin freno, un
    # script prueba candidatos hasta dar con uno vigente.
    clave = _frenar(_LIMITE_LICENCIA, request, "licencia")
    if not MODO_STANDALONE:
        raise HTTPException(404, "Este endpoint es solo para la versión standalone.")

    # Credencial del dueño (`mail|codigo`, ver kobra/owner.py) antes que la
    # licencia: es el mismo campo a propósito, así el desbloqueo funciona en
    # CUALQUIER build —incluido el instalador público— sin agregar una
    # pantalla que un cliente no debería ver siquiera.
    #
    # Va DESPUÉS del freno por IP y no antes: el código es la única barrera
    # entre un cliente y el producto completo, así que tantearlo tiene que
    # costar lo mismo que tantear una licencia.
    if kowner.verificar(datos.token):
        kconfig.guardar_extra(_CLAVE_OWNER, "1")
        kplan.invalidar_cache()
        _LIMITE_LICENCIA.perdonar(clave)
        return {"token": _emitir_token("admin", EMPRESA_DEFAULT), "rol": "admin",
                "empresa": EMPRESA_DEFAULT, "owner": True, "plan": "owner",
                "activa": True, "trial": False, "dias_restantes": None}

    r = klicencias.licencia_activa(datos.token)
    if not r["ok"]:
        mensaje = ("Tu licencia venció — comprá un plan en mvkobranzaia.com para seguir usando MV Kobra AI."
                  if r["error"] == "licencia_expirada" else
                  "Licencia inválida — revisá que la copiaste completa.")
        raise HTTPException(400, mensaje)
    _LIMITE_LICENCIA.perdonar(clave)
    kconfig.guardar_extra(_CLAVE_LICENCIA, datos.token)
    kplan.invalidar_cache()
    estado = _estado_licencia(datos.token)
    return {"token": _emitir_token("admin", EMPRESA_DEFAULT), "rol": "admin",
            "empresa": EMPRESA_DEFAULT, **estado}


# ---------------------------------------------------------------------------
# Cuentas por cobrar (kobra/cuentas_por_cobrar.py)
# ---------------------------------------------------------------------------
# El análisis de CxC que Kobra no cubría: antigüedad de saldos, DSO,
# efectividad de cobranza, conciliación de pagos y pagos mal aplicados. Todo
# es cálculo determinístico sobre la cartera real del cliente — no hay que
# pegarle una tabla a un asistente ni verificar después si sumó bien.
@app.get("/api/cxc/antiguedad")
def cxc_antiguedad(top: int = 10, u: Usuario = Depends(usuario_actual)):
    """Antigüedad de saldos + concentración: cuánto se debe en cada tramo y
    qué porcentaje de la cartera son los deudores más grandes."""
    f = _scored(u.empresa)
    return {"antiguedad": kcxc.antiguedad_saldos(f),
            "concentracion": kcxc.concentracion(f, top=top)}


class DsoIn(BaseModel):
    ventas_credito: float
    saldo_cxc: float | None = None
    dias_periodo: int = 30
    plazo_estandar: int | None = None


@app.post("/api/cxc/dso")
def cxc_dso(datos: DsoIn, u: Usuario = Depends(usuario_actual)):
    """Días de cartera (DSO). Las ventas a crédito las pone el usuario —
    Kobra ve la cobranza, no la facturación—; el saldo, si no se envía, sale
    de la cartera cargada."""
    saldo = datos.saldo_cxc
    if saldo is None:
        saldo = float(pd.to_numeric(_scored(u.empresa)["monto_deuda"],
                                    errors="coerce").fillna(0).sum())
    return kcxc.dso(datos.ventas_credito, saldo, datos.dias_periodo,
                    plazo_estandar=datos.plazo_estandar)


@app.get("/api/cxc/efectividad")
def cxc_efectividad(mes: str | None = None, comparar: str | None = None,
                    u: Usuario = Depends(usuario_actual)):
    """Monto cobrado sobre monto gestionado, del mes indicado, comparable
    contra otro mes. Sale de las gestiones que Kobra ya registra."""
    g = _gestiones(u.empresa)
    if g is None or g.empty:
        return {"efectividad": None, "error": "No hay gestiones registradas."}
    if mes is None:
        # El último mes CON DATOS, no el último del archivo: el mes en curso
        # suele estar a medias y daría "sin datos" en un tablero con miles de
        # gestiones cargadas.
        mes = kcxc.ultimo_mes_con_datos(g)
        if mes is None:
            return {"efectividad": None,
                    "error": "Ningún mes tiene monto gestionado cargado."}
    return kcxc.efectividad(g, mes=mes, mes_comparar=comparar)


class ConciliarIn(BaseModel):
    monto: float
    facturas: list[dict]


@app.post("/api/cxc/conciliar")
def cxc_conciliar(datos: ConciliarIn, u: Usuario = Depends(usuario_actual)):
    """¿A qué factura(s) corresponde este pago? Si hay más de una combinación
    posible lo dice y NO elige — aplicar la que 'parece' deja un saldo mal
    imputado que reaparece como un descuadre."""
    return kcxc.conciliar_pago(datos.monto, datos.facturas)


@app.get("/api/cxc/anomalias")
def cxc_anomalias(u: Usuario = Depends(usuario_actual)):
    """Revisa los pagos registrados en el portal de cobros y marca posibles
    duplicados, pagos sin factura y montos que no calzan. Marca, no corrige."""
    pagos = kportal.listar_pagos(_dir_portal(u.empresa))
    return kcxc.anomalias_en_pagos(pagos)


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
    filas = _proteger(filas, u.rol)
    return {"total": total, "pagina": pagina, "tamano": tamano,
            "filas": filas.to_dict("records"),
            "enmascarado": _hay_gobernanza() and u.rol != "admin"}


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
    # El export es la vía por la que un dato se va del programa y ya no vuelve.
    # Si la pantalla enmascara y el CSV no, la protección es decorativa: alcanza
    # con apretar "Exportar" para llevarse la cartera nominal completa.
    f = _proteger(f, u.rol)
    buf = io.StringIO()
    f.to_csv(buf, index=False)
    if _hay_gobernanza():
        kgob.registrar_linaje("export_cartera_csv", ["cartera_scoreada"],
                              "export", filas=len(f),
                              detalle={"rol": u.rol, "empresa": u.empresa})
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition":
                             "attachment; filename=cartera_priorizada.csv"})


# ---------------------------------------------------------------------------
# Gobernanza de datos — endpoints del módulo
# ---------------------------------------------------------------------------
# Estos SÍ usan `exigir`: son el módulo que se paga. Si el plan no lo incluye,
# el handler de FeatureNoIncluida responde con el mensaje y el link para
# mejorar el plan, en vez de un 404 que parecería un error del programa.
_MODULO_GOB = "la gobernanza de datos"


@app.get("/api/gobernanza/resumen")
def gobernanza_resumen(u: Usuario = Depends(usuario_actual)):
    """Todo lo que muestra la pantalla de gobernanza, en una llamada."""
    kplan.exigir("gobernanza", _MODULO_GOB)
    return kgob.resumen(_scored(u.empresa), rol=u.rol)


@app.get("/api/gobernanza/catalogo")
def gobernanza_catalogo(u: Usuario = Depends(usuario_actual)):
    """Qué es cada columna y quién la ve en claro."""
    kplan.exigir("gobernanza", _MODULO_GOB)
    df = _scored(u.empresa)
    return {"clasificacion": kgob.clasificar_tabla(df),
            "visibles": kgob.columnas_visibles(u.rol, df.columns),
            "niveles": list(kgob.NIVELES)}


@app.get("/api/gobernanza/calidad")
def gobernanza_calidad(u: Usuario = Depends(usuario_actual)):
    """Informe de calidad sobre las seis dimensiones DAMA."""
    kplan.exigir("gobernanza", _MODULO_GOB)
    return kgob.evaluar_calidad(_scored(u.empresa))


@app.get("/api/gobernanza/linaje")
def gobernanza_linaje(destino: str | None = None,
                      u: Usuario = Depends(usuario_actual)):
    """De dónde salió un dato y qué se rompe si cambia."""
    kplan.exigir("gobernanza", _MODULO_GOB)
    return {"asientos": kgob.linaje(destino),
            "aguas_arriba": kgob.aguas_arriba(destino) if destino else [],
            "aguas_abajo": kgob.aguas_abajo(destino) if destino else []}


# ---------------------------------------------------------------------------
# Medidas calculadas (módulo de la suite)
# ---------------------------------------------------------------------------
_MODULO_DAX = "las medidas calculadas"
_CLAVE_MEDIDAS = "MEDIDAS"


class MedidaIn(BaseModel):
    nombre: str
    formula: str
    descripcion: str = ""
    formato: str = "numero"


def _clave_medidas(empresa: str) -> str:
    # Por empresa: en hosted multi-tenant, las medidas de una no son de otra.
    return f"{_CLAVE_MEDIDAS}_{empresa}"


def _medidas_guardadas(empresa: str) -> list:
    crudo = kconfig.leer_extra(_clave_medidas(empresa))
    if not crudo:
        return kmedidas.medidas_de_ejemplo()
    try:
        return [kmedidas.Medida.de_dict(d) for d in json.loads(crudo)]
    except (ValueError, TypeError, KeyError):
        # Una configuración corrupta no puede dejar sin tablero al cliente:
        # se vuelve a los ejemplos, que siempre funcionan.
        return kmedidas.medidas_de_ejemplo()


@app.get("/api/medidas")
def medidas_listar(u: Usuario = Depends(usuario_actual)):
    """Las medidas definidas y su valor actual sobre la cartera."""
    kplan.exigir("dax", _MODULO_DAX)
    ms = _medidas_guardadas(u.empresa)
    df = _proteger(_scored(u.empresa), u.rol)
    return {"medidas": [m.a_dict() for m in ms],
            "valores": kmedidas.calcular_todas(ms, df),
            "columnas": sorted(df.columns),
            "funciones": sorted(kmedidas.NOMBRES_FUNCION)}


@app.post("/api/medidas/validar")
def medidas_validar(m: MedidaIn, u: Usuario = Depends(usuario_actual)):
    """Prueba la fórmula sin guardarla — para el botón 'Probar'."""
    kplan.exigir("dax", _MODULO_DAX)
    df = _proteger(_scored(u.empresa), u.rol)
    revision = kmedidas.validar(m.formula, df.columns)
    if not revision["ok"]:
        return revision
    return {**revision, "vista_previa": kmedidas.Medida(
        m.nombre or "prueba", m.formula, m.descripcion, m.formato).calcular(df)}


@app.post("/api/medidas")
def medidas_guardar(lista: list[MedidaIn], u: Usuario = Depends(solo_admin)):
    """Reemplaza el juego de medidas.

    `solo_admin` no es decorativo: una medida es una definición de negocio que
    después ve todo el equipo en el tablero. Que cualquiera la cambie es que
    nadie sepa qué está mirando.
    """
    kplan.exigir("dax", _MODULO_DAX)
    df = _scored(u.empresa)
    invalidas = []
    for m in lista:
        r = kmedidas.validar(m.formula, df.columns)
        if not r["ok"]:
            invalidas.append({"nombre": m.nombre, "error": r["error"]})
    if invalidas:
        # Se rechaza el lote entero: guardar la mitad deja al cliente sin saber
        # cuáles quedaron.
        raise HTTPException(400, {"detail": "Hay fórmulas inválidas.",
                                  "invalidas": invalidas})
    kconfig.guardar_extra(_clave_medidas(u.empresa),
                          json.dumps([m.model_dump() for m in lista]))
    return {"ok": True, "guardadas": len(lista)}


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


# ---------------------------------------------------------------------------
# Carpeta de datos: en qué disco guarda el programa
# ---------------------------------------------------------------------------
# Instalar en D: no alcanzaba: los datos iban siempre a %LOCALAPPDATA%, o sea
# a C:. El que instalaba en otro disco porque su C: estaba lleno chocaba igual
# contra C: en el primer import de cartera. El instalador ya lo pregunta; esto
# es para cambiarlo después, desde el programa y sin tocar una consola.
#
# `solo_admin` no es decorativo: esto elige una carpeta arbitraria del disco y
# copia datos ahí. Un gestor no tiene por qué poder mover la base de la empresa.
@app.get("/api/almacenamiento")
def almacenamiento(u: Usuario = Depends(solo_admin)):
    return krutas.estado()


class AlmacenamientoIn(BaseModel):
    carpeta: str
    copiar_datos: bool = True


@app.post("/api/almacenamiento")
def almacenamiento_guardar(datos: AlmacenamientoIn, u: Usuario = Depends(solo_admin)):
    carpeta = datos.carpeta.strip()
    if not carpeta:
        # Vaciar el campo = volver a la carpeta por defecto. No se copia nada:
        # los datos siguen donde están y el programa vuelve a mirar el default.
        krutas.guardar_eleccion("")
        return {**krutas.estado(), "aviso": "Volviste a la carpeta por defecto. "
                "Cerrá y volvé a abrir el programa para que tome efecto."}

    diag = krutas.revisar(carpeta)
    if not diag["ok"]:
        raise HTTPException(400, diag["motivo"])

    if datos.copiar_datos:
        r = krutas.mover_datos(carpeta)
        if not r["ok"]:
            raise HTTPException(400, r["motivo"])
        aviso = r["motivo"]
    else:
        krutas.guardar_eleccion(carpeta)
        aviso = f"Guardado. El programa va a usar {carpeta}."

    # El cambio recién aplica en el próximo arranque: DIR_DATOS se resuelve una
    # vez al importar y hay módulos que ya calcularon sus rutas contra él.
    # Prometer que ya está aplicado sería mentir sobre dónde se está guardando.
    return {**krutas.estado(), "aviso": aviso + " Cerrá y volvé a abrir el "
            "programa para que empiece a usarla."}


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


def _promesas_vencidas(empresa: str):
    """Promesas vencidas ordenadas por urgencia (mayor monto, luego mas dias
    vencida). Devuelve el DataFrame completo: quien llama decide si pagina."""
    g = _gestiones(empresa)
    if g is None or g.empty:
        return None
    venc = kseg.promesas_incumplidas(g)
    if len(venc) and {"monto_acordado", "dias_vencida"} <= set(venc.columns):
        venc = venc.sort_values(["monto_acordado", "dias_vencida"],
                                ascending=[False, False])
    return venc


@app.get("/api/agenda")
def agenda(u: Usuario = Depends(usuario_actual), pagina: int = 1,
           tamano: int = 100, limite: int | None = None):
    """Promesas vencidas a retomar HOY, **paginadas**.

    Antes se devolvian solo las 200 mas urgentes y el resto quedaba
    inalcanzable: con 2.258 promesas vencidas, el 91% de la cartera en riesgo
    no se podia ver ni exportar desde la pantalla. Renderizar miles de filas de
    una congela la pagina ~15 s, asi que la solucion no es subir el tope sino
    paginar: se llega al 100% de a paginas.

    `limite` se conserva por compatibilidad con el frontend anterior.
    """
    venc = _promesas_vencidas(u.empresa)
    if venc is None:
        return {"vencidas": [], "total": 0, "mostrando": 0,
                "pagina": 1, "tamano": tamano, "paginas": 0}
    total = int(len(venc))
    if limite is not None:            # modo viejo: las N mas urgentes
        tamano, pagina = max(1, min(int(limite), 1000)), 1
    tamano = max(1, min(int(tamano), 500))
    pagina = max(1, int(pagina))
    ini = (pagina - 1) * tamano
    hoja = venc.iloc[ini:ini + tamano]
    return {"total": total, "mostrando": int(len(hoja)),
            "pagina": pagina, "tamano": tamano,
            "paginas": (total + tamano - 1) // tamano if total else 0,
            "vencidas": hoja.to_dict("records")}


@app.get("/api/agenda/export.xlsx")
def agenda_export_xlsx(u: Usuario = Depends(usuario_actual)):
    """**Todas** las promesas vencidas en Excel con formato — no la pagina que
    se este viendo. Lo que no entra en pantalla tiene que poder salir igual."""
    venc = _promesas_vencidas(u.empresa)
    if venc is None:
        venc = pd.DataFrame()
    datos = _excel_formateado(
        {"Promesas vencidas": venc},
        titulo=f"MV Kobra AI · Promesas vencidas · {len(venc)} casos")
    nombre = f"MVKobraAI_Promesas_Vencidas_{_hoy_str()}.xlsx"
    return Response(
        content=datos,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


def _totales_gestores(ranking: pd.DataFrame) -> dict:
    """Fila de totales del ranking de gestores.

    La tabla mostraba 14 filas de montos sin ninguna suma: para saber cuánto
    recuperó el equipo había que sacar la calculadora. Las tasas y la calidad
    NO se suman — se promedian, y ponderadas por volumen: promediar los
    porcentajes de cada gestor le da el mismo peso al que hizo 840 gestiones
    que al que hizo 449, y el número sale mal.
    """
    if ranking is None or ranking.empty:
        return {}
    gestiones = float(ranking.get("gestiones", pd.Series(dtype=float)).sum())
    recupero = float(ranking.get("recupero", pd.Series(dtype=float)).sum())
    monto = float(ranking.get("monto", pd.Series(dtype=float)).sum())

    def _ponderado(columna: str) -> float | None:
        if columna not in ranking.columns or not gestiones:
            return None
        pesos = ranking["gestiones"].fillna(0)
        valores = ranking[columna].fillna(0)
        return float((valores * pesos).sum() / pesos.sum()) if pesos.sum() else None

    return {
        "gestores": int(len(ranking)),
        "gestiones": int(gestiones),
        "recupero": recupero,
        "monto": monto,
        # Sobre el total, no promediando promedios.
        "tasa_recupero": (recupero / monto) if monto else None,
        "calidad_prom": _ponderado("calidad_gestion")
                        if "calidad_gestion" in ranking.columns
                        else _ponderado("calidad_prom"),
        "tasa_conversion": _ponderado("tasa_conversion"),
        "usan_kobra": int(ranking.get("usa_kobra", pd.Series(dtype=float))
                          .fillna(0).astype(bool).sum()),
    }


def _origen_gestiones(empresa: str) -> dict:
    """De dónde salen las gestiones que se están mostrando.

    La pantalla de gestores decía «en la demo son sintéticos» en un texto fijo,
    que seguía diciendo lo mismo con datos reales cargados. Que el programa
    avise de verdad exige mirar el dato, no repetir una leyenda."""
    modo = _modo_cartera(empresa)
    real = modo == "real"
    return {"tipo": modo, "es_real": real,
            "etiqueta": "Datos reales" if real else "Demo · datos sintéticos",
            "detalle": ("Del dataset cargado por la empresa."
                        if real else
                        "Generados sintéticamente: sirven para evaluar el "
                        "producto, no son resultados de una operación real.")}


@app.get("/api/gestores/resumen")
def gestores_resumen(u: Usuario = Depends(usuario_actual)):
    g = _gestiones(u.empresa)
    if g is None or g.empty:
        return {"ranking": [], "impacto": None}
    completo = kanalitica.ranking_gestores(g)
    ranking = completo.head(15)
    impacto = kanalitica.impacto_kobra(g)
    return {"ranking": ranking.reset_index().to_dict("records"),
            "totales": _totales_gestores(completo),
            "origen": _origen_gestiones(u.empresa),
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
    kplan.exigir("voz", "la evaluación automática de audios")
    nombre = (archivo.filename or "").lower()
    if not nombre.endswith((".wav", ".mp3")):
        raise HTTPException(400, "Subí un archivo .wav o .mp3.")

    from kobra import voz as kvoz
    # Sin Whisper la transcripción sería vacía y diarizar es caro: cortamos ya.
    if not kvoz.whisper_disponible():
        return {"archivo": archivo.filename, "modo_transcripcion": "sin_whisper",
                "turnos": [], "evaluacion": None, "aviso": _AVISO_SIN_WHISPER}

    # Va acá y no arriba: sin Whisper no se procesa nada, y cobrarle una
    # gestión a quien recibe un aviso de "falta configurar" sería un robo.
    kplan.verificar_cupo()
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
        raise HTTPException(
            400, "No pude procesar esa grabación. Verificá que sea un .wav o .mp3 "
                 "válido y que no esté cortado. "
                 f"(detalle: {_detalle_sin_rutas(e)})") from e
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
            "guardado": guardado, "plan": kplan.registrar_gestion()}


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
    import uuid

    from kobra import calidad_gestion as kcalidad
    if not fecha:
        fecha = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    fila = kcalidad.fila_evaluacion(gestor, fecha, canal, archivo, evaluacion,
                                    uuid.uuid4().hex[:12])
    ruta = _archivo_calidad(empresa)
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    # Sin lock, dos evaluaciones subidas casi juntas (dos supervisores
    # cargando llamadas al mismo tiempo) leen el mismo CSV de N filas antes
    # de que cualquiera escriba: las dos calculan N+1 y la segunda pisa a la
    # primera — una evaluación desaparece sin error para nadie. Mismo patrón
    # que ya usa `kobra/registro.py` para el mismo tipo de problema.
    with portalocker.Lock(ruta + ".lock", timeout=10):
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


@app.get("/api/calidad/panel")
def calidad_panel(gestor: str | None = None, anio: str | None = None,
                  mes: str | None = None, canal: str | None = None,
                  u: Usuario = Depends(usuario_actual)):
    """Tablero de calidad de llamadas con el desglose de una supervisión real:
    por gestor, mes y año, por aspecto de la negociación, y **cada aspecto
    comparado contra la media del equipo**.

    La comparación es el punto: saber que un gestor tiene 68 de calidad no dice
    qué entrenarle; saber que está 22 puntos por debajo de la media en
    "Negociación deuda total" y 9 por encima en "Escucha activa", sí.
    """
    from kobra import calidad_gestion as kcalidad
    panel = kcalidad.panel_calidad(_leer_calidad(u.empresa), gestor=gestor,
                                   anio=anio, mes=mes, canal=canal)
    panel["origen"] = _origen_gestiones(u.empresa)
    return panel


@app.get("/api/calidad/export.xlsx")
def calidad_export_xlsx(gestor: str | None = None, anio: str | None = None,
                        mes: str | None = None, canal: str | None = None,
                        u: Usuario = Depends(usuario_actual)):
    """El tablero de calidad completo en Excel: una hoja por vista, con el
    mismo formato que el resto de los exports."""
    from kobra import calidad_gestion as kcalidad
    panel = kcalidad.panel_calidad(_leer_calidad(u.empresa), gestor=gestor,
                                   anio=anio, mes=mes, canal=canal)
    quien = gestor or "Equipo"
    hojas = {
        "Por aspecto": pd.DataFrame(panel.get("por_criterio", [])),
        "Ranking gestores": pd.DataFrame(panel.get("ranking", [])),
        "Evolucion mensual": pd.DataFrame(panel.get("evolucion", [])),
        "Distribucion": pd.DataFrame(panel.get("distribucion", [])),
        "Por canal": pd.DataFrame(panel.get("por_canal", [])),
    }
    periodo = mes or anio or "todo el período"
    datos = _excel_formateado(
        hojas, titulo=f"MV Kobra AI · Calidad de llamadas · {quien} · {periodo}")
    nombre = f"MVKobraAI_Calidad_{_hoy_str()}.xlsx"
    return Response(
        content=datos,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


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
    """Con qué proveedor Y modelo de IA (traé tu propia cuenta corporativa)
    razona el Asistente, el Copiloto y el Gestor IA — Claude, Gemini,
    ChatGPT/OpenAI o Grok. Eligiendo el modelo el cliente regula su consumo
    de tokens; `modelos` trae el catálogo cacheado de cada proveedor (ver
    /actualizar_modelos para refrescarlo contra la API del proveedor)."""
    kconfig.aplicar()
    return {"proveedor": kllm.proveedor_activo(), "proveedores": list(kllm.PROVEEDORES),
            "claves_configuradas": {p: kllm.disponible(proveedor=p) for p in kllm.PROVEEDORES},
            "modelos": {p: {"activo": kllm.modelo_de(p),
                            "disponibles": kllm.modelos_disponibles(p),
                            "actualizado": kllm.fecha_actualizacion_modelos(p)}
                        for p in kllm.PROVEEDORES}}


class ProveedorIAIn(BaseModel):
    proveedor: str
    modelo: str | None = None


@app.post("/api/config/proveedor_ia")
def proveedor_ia_guardar(datos: ProveedorIAIn, u: Usuario = Depends(solo_admin)):
    if datos.proveedor not in kllm.PROVEEDORES:
        raise HTTPException(400, f"Proveedor '{datos.proveedor}' no soportado "
                                 f"(válidos: {', '.join(kllm.PROVEEDORES)}).")
    kllm.establecer_proveedor(datos.proveedor)
    if datos.modelo and datos.modelo.strip():
        kllm.establecer_modelo(datos.proveedor, datos.modelo.strip())
    return {"proveedor": datos.proveedor, "modelo": kllm.modelo_de(datos.proveedor)}


@app.post("/api/config/proveedor_ia/actualizar_modelos")
def proveedor_ia_actualizar_modelos(datos: ProveedorIAIn, u: Usuario = Depends(solo_admin)):
    """Botón "Actualizar": consulta a la API del proveedor por sus últimos
    modelos publicados (con la key del cliente) y cachea el catálogo."""
    if datos.proveedor not in kllm.PROVEEDORES:
        raise HTTPException(400, f"Proveedor '{datos.proveedor}' no soportado "
                                 f"(válidos: {', '.join(kllm.PROVEEDORES)}).")
    kconfig.aplicar()
    res = kllm.actualizar_modelos(datos.proveedor)
    if not res["ok"]:
        raise HTTPException(502, res["detalle"])
    return {"proveedor": datos.proveedor, "modelos": res["modelos"],
            "detalle": res["detalle"],
            "actualizado": kllm.fecha_actualizacion_modelos(datos.proveedor)}


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
    kplan.exigir("erp", "la integración con tu ERP/core")
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
        raise HTTPException(
            400, "No pude leer ese archivo. Tiene que ser un .csv o un .xlsx con "
                 "una fila de encabezados. "
                 f"(detalle: {_detalle_sin_rutas(e)})") from e

    # Se adapta solo a nombres de columna parecidos (MontoDeuda, Saldo Vencido,
    # Dívida, Total Debt…); mostramos que reconoció para que el cliente confíe.
    mapeo = kcartera.mapear_columnas(df_bruto.columns)
    try:
        full = kcartera.importar_y_scorear(df_bruto.fillna(""))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

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
    kplan.exigir("erp", "la importación directa desde tu base de datos")
    try:
        contactos = kcartera.desde_base_de_datos(datos.conn_url, datos.consulta)  # limite=None
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except Exception as e:
        raise HTTPException(
            400, "No pude conectar a la base o la consulta falló. Revisá la cadena "
                 "de conexión, que el servidor sea alcanzable y que la consulta "
                 "sea válida. "
                 f"(detalle: {_detalle_sin_rutas(e)})") from e
    if not contactos:
        raise HTTPException(422, "La consulta no devolvió ninguna fila con un monto de "
                                 "deuda válido (columna 'deuda', 'monto' o 'monto_deuda').")
    try:
        full = kcartera.importar_y_scorear(pd.DataFrame(contactos))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

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
    kplan.exigir("voz", "el copiloto de voz")
    kplan.verificar_cupo()
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
        raise HTTPException(
            400, "No pude analizar esa grabación. Verificá que sea un .wav o .mp3 "
                 "válido y que no esté cortado. "
                 f"(detalle: {_detalle_sin_rutas(e)})") from e
    finally:
        try:
            os.remove(destino)
        except OSError:
            pass

    # El análisis salió bien: recién ahora consume cupo (ver plan.verificar_cupo).
    plan_estado_actual = kplan.registrar_gestion()

    return {"archivo": archivo.filename, "voz": res["voz"],
            "modo_transcripcion": res["modo_transcripcion"], "turnos": res["turnos"],
            "copiloto": res["copiloto"], "calidad": res["calidad"],
            "tecnicas": res["tecnicas"], "plan": plan_estado_actual}


# Deudor sintético por default de la demo del Gestor IA — el caso que se le
# muestra a un prospecto: 3 cuotas adeudadas, sueldo declarado, etc.
#
# El teléfono es INVENTADO y tiene que seguir siéndolo. Acá había un celular
# uruguayo real, commiteado en un repositorio público: eso lo indexa Google y
# lo levantan los bots que rastrean GitHub buscando exactamente eso. Cuando la
# demostración tiene que llamar a un teléfono de verdad, el número sale de la
# configuración cifrada de la máquina (`kobra/demo_vivo.py`), nunca de acá.
# `tests/test_sin_datos_personales.py` falla si vuelve a entrar uno real.
_DEUDOR_DEMO_GESTOR = {
    "id_deudor": "DEMO-001", "nombre": "Cliente de Demostración",
    "telefono": "099000001",
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
    kplan.exigir("whatsapp" if canal == "WhatsApp" else "voz",
                 "el canal WhatsApp" if canal == "WhatsApp" else "el canal de voz")
    kplan.exigir("copiloto", "el Agente IA Negociador")
    kplan.verificar_cupo()
    bruto = pd.DataFrame([datos.deudor or _DEUDOR_DEMO_GESTOR])
    try:
        full = kcartera.importar_y_scorear(bruto.astype(str))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
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
        "plan": kplan.registrar_gestion(),
    }


# ---------------------------------------------------------------------------
# Portal de cobros centralizado
# ---------------------------------------------------------------------------
# El deudor paga solo: entra por link/QR (token HMAC) o con usuario+código,
# ve sus facturas y paga total o parcial por transferencia o MercadoPago.
# Cada pago queda imputado en la cola ERP (webhook saliente + pull por API).
# Dominio en kobra/portal_pagos.py; acá solo la capa HTTP.
from kobra import portal_pagos as kportal  # noqa: E402

# El código de acceso es de 6 dígitos: SIN freno se prueba entero en horas.
_LIMITE_PORTAL = klimite.Limitador()


def _dir_portal(empresa: str) -> str:
    """Los archivos del portal viven junto a los datos del tenant."""
    return os.path.dirname(_datos_de(empresa)["gestiones"])


def _fila_deudor(empresa: str, id_deudor: str) -> dict:
    f = _scored(empresa)
    fila = f[f["id_deudor"] == id_deudor]
    if fila.empty:
        raise HTTPException(404, "No encontramos esa deuda. Verificá el acceso.")
    return {k: (None if pd.isna(v) else (v.item() if hasattr(v, "item") else v))
            for k, v in fila.iloc[0].items()}


def _deudor_desde_token(t: str) -> tuple[str, str]:
    par = kportal.validar_token(_secreto(), t or "")
    if par is None:
        raise HTTPException(401, "El link de pago no es válido o venció. "
                                 "Pedile a la empresa uno nuevo.")
    return par


@app.get("/api/portal/config")
def portal_config(u: Usuario = Depends(solo_admin)):
    cfg = kportal.cargar_config(_dir_portal(u.empresa))
    # La API key efectiva se muestra para poder configurar el ERP; si la
    # empresa no definió una, es la derivada del secreto (nunca queda vacía).
    return {**cfg, "erp_api_key_efectiva":
            kportal.api_key_erp(_dir_portal(u.empresa), _secreto())}


class PortalConfigIn(BaseModel):
    transferencia: dict | None = None
    mercadopago: dict | None = None
    erp: dict | None = None


@app.post("/api/portal/config")
def portal_config_guardar(datos: PortalConfigIn, u: Usuario = Depends(solo_admin)):
    cfg = kportal.guardar_config(_dir_portal(u.empresa), datos.model_dump(exclude_none=True))
    return {**cfg, "erp_api_key_efectiva":
            kportal.api_key_erp(_dir_portal(u.empresa), _secreto())}


@app.get("/api/portal/acceso/{id_deudor}")
def portal_acceso(id_deudor: str, u: Usuario = Depends(usuario_actual)):
    """Credenciales de acceso del deudor, para compartir por WhatsApp/mail o
    imprimir el QR: link con token firmado + usuario y código."""
    _fila_deudor(u.empresa, id_deudor)          # 404 si no existe
    token = kportal.token_portal(_secreto(), u.empresa, id_deudor)
    return {
        "id_deudor": id_deudor,
        "token": token,
        "ruta": f"/#/pagar?t={token}",
        "usuario": id_deudor,
        "codigo": kportal.codigo_acceso(_secreto(), u.empresa, id_deudor),
    }


@app.get("/api/portal/pagos")
def portal_pagos_recibidos(u: Usuario = Depends(usuario_actual)):
    pagos = kportal.listar_pagos(_dir_portal(u.empresa))
    pagos.sort(key=lambda p: p.get("creado", ""), reverse=True)
    return {"pagos": pagos[:500], "total": len(pagos)}


class PortalLoginIn(BaseModel):
    usuario: str
    codigo: str
    empresa: str = EMPRESA_DEFAULT


@app.post("/api/portal/public/login")
def portal_public_login(datos: PortalLoginIn, request: Request):
    clave = _frenar(_LIMITE_PORTAL, request, "portal")
    id_deudor = datos.usuario.strip().upper()
    esperado = kportal.codigo_acceso(_secreto(), datos.empresa, id_deudor)
    if not hmac.compare_digest(esperado, datos.codigo.strip()):
        raise HTTPException(401, "Usuario o código incorrectos.")
    _LIMITE_PORTAL.perdonar(clave)
    _fila_deudor(datos.empresa, id_deudor)      # 404 si el id no existe
    return {"token": kportal.token_portal(_secreto(), datos.empresa, id_deudor)}


@app.get("/api/portal/public/estado")
def portal_public_estado(t: str):
    empresa, id_deudor = _deudor_desde_token(t)
    fila = _fila_deudor(empresa, id_deudor)
    d = _dir_portal(empresa)
    cfg = kportal.cargar_config(d)
    pais = kpaises.obtener(_pais_de(empresa))
    total = float(fila.get("monto_deuda") or 0)
    return {
        "id_deudor": id_deudor,
        "saldo": kportal.saldo_pendiente(d, id_deudor, total),
        "total": round(total, 2),
        "facturas": kportal.facturas_de(fila),
        "pagos": [{k: p[k] for k in ("referencia", "monto", "metodo", "estado", "creado")}
                  for p in kportal.listar_pagos(d, id_deudor)],
        "metodos": {
            "transferencia": {k: v for k, v in cfg["transferencia"].items()
                              if k != "habilitado"} if cfg["transferencia"]["habilitado"] else None,
            "mercadopago": bool(cfg["mercadopago"]["habilitado"]),
        },
        "moneda": {"simbolo": pais.simbolo, "locale": pais.locale},
    }


class PortalPagoIn(BaseModel):
    t: str
    monto: float
    metodo: str


@app.post("/api/portal/public/pagar")
def portal_public_pagar(datos: PortalPagoIn):
    empresa, id_deudor = _deudor_desde_token(datos.t)
    fila = _fila_deudor(empresa, id_deudor)
    d = _dir_portal(empresa)
    cfg = kportal.cargar_config(d)
    if datos.metodo == "transferencia" and not cfg["transferencia"]["habilitado"]:
        raise HTTPException(400, "La empresa no habilitó pagos por transferencia.")
    if datos.metodo == "mercadopago" and not cfg["mercadopago"]["habilitado"]:
        raise HTTPException(400, "La empresa no habilitó MercadoPago.")
    try:
        pago = kportal.crear_pago(d, empresa, id_deudor, datos.monto,
                                  datos.metodo, float(fila.get("monto_deuda") or 0))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    out = {"referencia": pago["referencia"], "monto": pago["monto"],
           "tipo": pago["tipo"], "metodo": pago["metodo"]}
    if datos.metodo == "transferencia":
        out["transferencia"] = {k: v for k, v in cfg["transferencia"].items()
                                if k != "habilitado"}
    else:
        out["url_pago"] = kportal.link_mercadopago(
            cfg, pago["referencia"], pago["monto"],
            descripcion=f"Deuda {id_deudor} · {empresa}",
            base_url=os.environ.get("PUBLIC_BASE_URL", ""))
        # Con access token cargado el checkout es real; si además es una
        # credencial TEST, el que paga usa tarjetas ficticias. El portal lo
        # dice en pantalla para que nadie confunda un ensayo con un cobro.
        from kobra import mercadopago as kmp
        if kmp.es_credencial_de_prueba(cfg["mercadopago"].get("access_token", "")):
            out["modo_prueba"] = True
    return out


class PortalConfirmarIn(BaseModel):
    t: str
    referencia: str
    # `payment_id` lo devuelve MercadoPago al volver del checkout. Cuando
    # llega —y la empresa cargó su access token— el pago se VERIFICA contra la
    # API antes de imputarlo, y recién ahí puede quedar `aprobado`.
    payment_id: str | None = None


@app.post("/api/portal/public/confirmar")
def portal_public_confirmar(datos: PortalConfirmarIn):
    """El deudor informa que pagó. Qué tan lejos llega esa afirmación depende
    de si se puede verificar:

    * **Con `payment_id` y access token de MercadoPago** → se le pregunta a
      MercadoPago por ese pago y se comparan estado, referencia y monto
      (`kobra/mercadopago.py`). Si todo cierra, el pago queda **`aprobado`**:
      la plata entró y hay con qué probarlo.
    * **Sin eso** —transferencia bancaria, o MercadoPago sin credenciales—
      queda **`informado`**: imputado (cola ERP + webhook) pero pendiente de
      conciliar. Una transferencia no se puede confirmar sin integrar el banco
      de la empresa, y afirmar lo contrario sería inventar una verificación.

    La distinción no es burocracia: marcar `aprobado` solo porque alguien dice
    que pagó permitía a cualquier deudor con su token de acceso saldar su
    propia deuda sin pagar un peso. La única fuente de verdad sobre si entró
    la plata es MercadoPago, nunca el navegador del que paga.
    """
    empresa, id_deudor = _deudor_desde_token(datos.t)
    d = _dir_portal(empresa)
    pago = next((p for p in kportal.listar_pagos(d, id_deudor)
                 if p["referencia"] == datos.referencia), None)
    if pago is None:
        raise HTTPException(404, "No existe ese pago para esta deuda.")
    cfg = kportal.cargar_config(d)

    estado, verificacion = "informado", None
    token_mp = (cfg["mercadopago"].get("access_token") or "").strip()
    if datos.payment_id and token_mp and pago["metodo"] == "mercadopago":
        from kobra import mercadopago as kmp
        v = kmp.verificar_pago(token_mp, datos.payment_id,
                               referencia_esperada=datos.referencia,
                               monto_esperado=pago["monto"])
        verificacion = {"estado_mp": v["estado"], "detalle": v["detalle"]}
        if v["aprobado"]:
            estado = "aprobado"

    registro = kportal.confirmar_pago(d, datos.referencia, estado,
                                      webhook_url=cfg["erp"]["webhook_url"])
    salida = {"referencia": registro["referencia"], "estado": registro["estado"],
              "monto": registro["monto"]}
    if verificacion:
        salida["verificacion"] = verificacion
    return salida


@app.get("/api/erp/imputaciones")
def erp_imputaciones(request: Request, desde: str = "",
                     empresa: str = EMPRESA_DEFAULT):
    """Pull para el ERP/CRM: pagos imputados, opcionalmente incrementales
    (`desde` = último `imputado_en` ya sincronizado, exclusivo). Autenticado
    por API key (cabecera X-API-Key) — la que muestra la pantalla Portal de
    cobros o la que la empresa configuró."""
    esperada = kportal.api_key_erp(_dir_portal(empresa), _secreto())
    recibida = request.headers.get("X-API-Key", "")
    if not hmac.compare_digest(esperada, recibida):
        raise HTTPException(401, "API key inválida (cabecera X-API-Key).")
    # El chequeo del plan va DESPUÉS de la API key: si fuera antes, este
    # endpoint le contestaría distinto a quien no tiene la clave según el plan
    # del cliente, y eso es información que un desconocido no tiene por qué
    # poder sonsacar.
    kplan.exigir("erp", "el pull de imputaciones para tu ERP")
    imps = kportal.listar_imputaciones(_dir_portal(empresa), desde=desde)
    return {"imputaciones": imps, "total": len(imps)}


# ---------------------------------------------------------------------------
# Demostración en vivo (kobra/demo_vivo.py)
# ---------------------------------------------------------------------------
# Todo el circuito se opera desde la pantalla: nadie tiene que abrir una
# consola en el medio de una reunión con un cliente. El dominio vive en
# demo_vivo.py; acá está solo la capa HTTP.
from kobra import demo_vivo as kdemo  # noqa: E402


def _dir_demo(empresa: str) -> str:
    """Los pagos de la demo van al mismo lugar que los del portal del tenant,
    así el cobro aparece en las mismas pantallas que uno real."""
    return _dir_portal(empresa)


@app.get("/api/demo/estado")
def demo_estado(u: Usuario = Depends(usuario_actual)):
    """Todo lo que la pantalla necesita para dibujarse entera, en un solo GET:
    el caso, el saldo, el guion, las propuestas y qué falta configurar."""
    d = _dir_demo(u.empresa)
    saldo_actual = kdemo.saldo(d)
    return {
        "caso": kdemo.caso(),
        "contacto_ok": kdemo.configurado(),
        "claves": kdemo.CLAVES,
        "base_url": os.environ.get("PUBLIC_BASE_URL", ""),
        "saldo": saldo_actual,
        "pago_demo": kdemo.PAGO_DEMO,
        "guion": kdemo.guion(),
        "propuestas": kdemo.propuestas(saldo_actual) if saldo_actual > 0 else [],
        "pagos": kportal.listar_pagos(d, kdemo.ID_DEUDOR),
    }


class DemoContactoIn(BaseModel):
    valores: dict


@app.post("/api/demo/contacto")
def demo_contacto(datos: DemoContactoIn, u: Usuario = Depends(solo_admin)):
    """Guarda el contacto del caso en el almacén cifrado de la máquina — nunca
    en el repositorio, que es público. Un campo vacío conserva lo que había."""
    guardadas = []
    for clave, valor in (datos.valores or {}).items():
        if clave in kdemo.CLAVES and isinstance(valor, str) and valor.strip():
            kconfig.guardar_extra(clave, valor.strip())
            guardadas.append(clave)
    if not guardadas:
        raise HTTPException(400, "No llegó ningún dato para guardar.")
    return {"guardadas": sorted(guardadas), "contacto_ok": kdemo.configurado()}


@app.post("/api/demo/contactar")
def demo_contactar(u: Usuario = Depends(solo_admin)):
    """Llama y escribe por WhatsApp, de verdad. Es un endpoint aparte a
    propósito: hacer sonar el teléfono de alguien no puede ser un efecto
    secundario de abrir una pantalla."""
    if not kdemo.configurado():
        raise HTTPException(400, "Falta DEMO_VIVO_TELEFONO: sin número no hay "
                                 "llamada ni WhatsApp.")
    base = os.environ.get("PUBLIC_BASE_URL", "")
    if not base:
        raise HTTPException(400, "Falta PUBLIC_BASE_URL: sin una URL pública, "
                                 "Twilio no encuentra el webhook de voz.")
    llamada = kdemo.llamar(base_url=base)
    whatsapp = kdemo.escribir_whatsapp()
    return {"pasos": [
        {"orden": 1, "titulo": "Llamada", "ok": bool(llamada.get("ok")),
         "detalle": llamada.get("detalle")},
        {"orden": 2, "titulo": "WhatsApp", "ok": bool(whatsapp.get("ok")),
         "detalle": whatsapp.get("detalle")},
    ]}


class DemoCobroIn(BaseModel):
    monto: float
    metodo: str = "mercadopago"


@app.post("/api/demo/cobrar")
def demo_cobrar(datos: DemoCobroIn, u: Usuario = Depends(solo_admin)):
    """El link de pago con el monto exacto. Con un access token `TEST-…`
    devuelve además las tarjetas ficticias para pagarlo — que es como se
    ensaya el cobro sin mover un peso."""
    if datos.metodo not in ("mercadopago", "transferencia"):
        raise HTTPException(400, "Método de pago desconocido.")
    try:
        pago = kdemo.link_de_pago(_dir_demo(u.empresa), monto=datos.monto,
                                  metodo=datos.metodo, empresa=u.empresa,
                                  base_url=os.environ.get("PUBLIC_BASE_URL", ""))
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if pago.get("modo_prueba"):
        from kobra import mercadopago as kmp
        pago["datos_prueba"] = kmp.datos_de_prueba()
    return pago


class DemoAcreditarIn(BaseModel):
    referencia: str
    payment_id: str | None = None


@app.post("/api/demo/acreditar")
def demo_acreditar(datos: DemoAcreditarIn, u: Usuario = Depends(solo_admin)):
    """Da por cobrado el pago. Con `payment_id` se verifica contra MercadoPago
    y puede quedar `aprobado`; sin él queda `informado`. Si la verificación
    falla, no se imputa nada y se devuelve el motivo."""
    try:
        r = kdemo.acreditar(_dir_demo(u.empresa), datos.referencia,
                            payment_id=(datos.payment_id or "").strip())
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    if r.get("estado") == "pendiente" and r.get("detalle"):
        raise HTTPException(422, r["detalle"])
    return r


class DemoPromesaIn(BaseModel):
    monto_acordado: float
    cuotas: int = 1
    descuento: float = 0.0
    fecha_compromiso: str = ""


@app.post("/api/demo/promesa")
def demo_promesa(datos: DemoPromesaIn, u: Usuario = Depends(solo_admin)):
    """Registra el acuerdo por el saldo. A partir de acá el caso entra al
    seguimiento normal: si la fecha pasa sin el pago, aparece en la agenda."""
    kdemo.registrar_acuerdo(monto_acordado=datos.monto_acordado, cuotas=datos.cuotas,
                            descuento=datos.descuento,
                            fecha_compromiso=datos.fecha_compromiso)
    return {"ok": True, "saldo": kdemo.saldo(_dir_demo(u.empresa))}


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
