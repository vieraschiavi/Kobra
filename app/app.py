# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Dashboard Gerencial de Cobranzas Inteligentes
====================================================
App Streamlit end-to-end: ProbPago + Agente IA Negociador sobre una cartera
de cobranzas. Filtros, KPIs, gráficos, tablas y exportación a Excel/CSV.

Ejecutar:
    streamlit run app/app.py
"""
import io
import json
import os
import sys

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import (
    analitica,  # noqa: E402
    copiloto,  # noqa: E402
    negociador,  # noqa: E402
)
from kobra import config as kconfig  # noqa: E402
from kobra import roi as kroi  # noqa: E402
from kobra import rutas as krutas  # noqa: E402
from kobra.probpago import ProbPagoModel  # noqa: E402

# Escribible siempre: instalado en Program Files, ROOT es de solo lectura
# para un usuario sin admin (PermissionError). Ver kobra/rutas.py.
SCRATCH = os.path.join(krutas.DIR_DATOS, ".uploads")
from kobra import auditoria as kauditoria  # noqa: E402
from kobra import ayuda as kayuda  # noqa: E402
from kobra import campana as kcampana  # noqa: E402
from kobra import consulta_bd as kconsulta  # noqa: E402
from kobra import integracion as kerp  # noqa: E402
from kobra import llm as kllm  # noqa: E402
from kobra import seguimiento as kseg  # noqa: E402
from kobra import twilio_setup as ktwilio  # noqa: E402
from kobra import voz_tts  # noqa: E402

kconfig.aplicar()   # carga API keys guardadas al entorno

# ----------------------------------------------------------------------------
# Config & estilo
# ----------------------------------------------------------------------------
_ICON_PATH = os.path.join(ROOT, "assets", "brand", "mv_icon_64.png")
# Ícono a nivel PC (ventana/pestaña del navegador): logo MV.
_PC_ICON = os.path.join(ROOT, "assets", "brand", "mv_icon_64.png")
st.set_page_config(page_title="MV Kobra AI · Cobranzas Inteligentes",
                   page_icon=_PC_ICON if os.path.exists(_PC_ICON)
                   else (_ICON_PATH if os.path.exists(_ICON_PATH) else None),
                   layout="wide", initial_sidebar_state="expanded")

PRIMARY = "#00C896"       # verde MV Kobra AI
DARK = "#0E1117"
ACCENT = "#6C5CE7"
YELLOW = "#FDCB6E"
SEQ = ["#00C896", "#6C5CE7", "#FDCB6E", "#FF7675", "#74B9FF"]

st.markdown(f"""
<style>
    .stApp {{ background: linear-gradient(180deg,#0E1117 0%,#12151f 100%); }}
    .block-container {{ padding-top: 1.2rem; }}
    h1,h2,h3,h4 {{ color:#F5F6FA; font-family:'Segoe UI',sans-serif; }}
    [data-testid="stMetric"] {{
        background: #1a1f2e; border:1px solid #262b3d; border-radius:14px;
        padding:14px 16px; box-shadow:0 2px 10px rgba(0,0,0,.35);
    }}
    [data-testid="stMetricValue"] {{ color:{PRIMARY}; font-weight:700; font-size:1.55rem; }}
    [data-testid="stMetricLabel"] {{ color:#9aa4b2; }}
    .kobra-badge {{
        display:inline-block; background:{PRIMARY}; color:#08110d;
        padding:2px 10px; border-radius:20px; font-weight:700; font-size:.75rem;
    }}
    .guion-box {{
        background:#141b2d; border-left:4px solid {PRIMARY}; border-radius:8px;
        padding:14px 16px; color:#dfe6f0; font-size:.95rem; margin-top:8px;
    }}
    section[data-testid="stSidebar"] {{ background:#0b0e16; }}
    /* --- Guía & Ayuda --- */
    .kh-hero {{
        background:linear-gradient(120deg,#141b2d 0%,#101627 60%,#0d1b17 100%);
        border:1px solid #26304a; border-radius:18px; padding:26px 28px; margin:6px 0 18px;
    }}
    .kh-hero h2 {{ margin:0 0 6px; font-size:1.55rem; }}
    .kh-hero p {{ margin:0; color:#aeb9cc; font-size:.98rem; }}
    .kh-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(270px,1fr));
        gap:14px; margin:6px 0 8px; }}
    .kh-card {{ background:#161c2b; border:1px solid #26304a; border-radius:14px;
        padding:18px 18px 16px; position:relative; }}
    .kh-card h4 {{ margin:2px 0 8px; font-size:1.05rem; color:#f2f5fa; }}
    .kh-card p, .kh-card li {{ color:#c2cbdb; font-size:.9rem; line-height:1.5; }}
    .kh-card ul {{ margin:6px 0 0; padding-left:18px; }}
    .kh-num {{ display:inline-flex; align-items:center; justify-content:center;
        width:30px; height:30px; border-radius:9px; background:{PRIMARY}; color:#062018;
        font-weight:800; font-size:1rem; margin-bottom:8px; }}
    .kh-pill {{ display:inline-block; background:#0f1523; border:1px solid #2b3550;
        color:#9fb0c6; border-radius:20px; padding:2px 10px; font-size:.72rem;
        font-weight:600; margin-left:6px; }}
    .kh-key {{ background:#0f1523; border:1px solid #2b3550; border-radius:6px;
        padding:1px 7px; font-family:Consolas,monospace; font-size:.82rem; color:#7ff0c6; }}
    .kh-ok {{ color:#00C896; font-weight:700; }} .kh-off {{ color:#8593a8; }}
</style>
""", unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# Acceso: login/setup obligatorio antes de mostrar cualquier dato (ver
# kobra/autenticacion.py). Roles: admin (todo) / gestor (sin Configuración).
# ----------------------------------------------------------------------------
from kobra import autenticacion as kauth  # noqa: E402
from kobra import backup as kbackup  # noqa: E402
from kobra import edicion as kedicion  # noqa: E402
from kobra import plan as kplan  # noqa: E402
from kobra import sso_oidc as ksso  # noqa: E402

# Vigencia de la edición ANTES del login: si la evaluación venció, no tiene
# sentido pedir una contraseña para después mostrar el bloqueo. Corriendo
# desde el repo (sin `edicion.json`) esto no bloquea nada.
_EDICION = kedicion.vigencia()
if not _EDICION["ok"]:
    st.error(
        "Tu período de evaluación de MV Kobra AI terminó.\n\n"
        "Escribinos para activar tu licencia y seguir usando el programa con "
        "tus datos: **mvkobranzaia.com**"
        if _EDICION["motivo"] == "licencia_expirada" else
        "La licencia de esta copia no es válida. Escribinos a "
        "**mvkobranzaia.com** para regularizarla.")
    st.stop()

ROL_ACTIVO = kauth.render_gate()
if ROL_ACTIVO is None:
    st.stop()


# ----------------------------------------------------------------------------
# Datos + modelo (cacheado)
# ----------------------------------------------------------------------------
@st.cache_data(show_spinner="Entrenando ProbPago y corriendo el negociador…")
def cargar():
    csv = os.path.join(ROOT, "data", "kobra_cartera.csv")
    if os.path.exists(csv):
        df = pd.read_csv(csv)
    else:
        from data.generate_dataset import generar
        df = generar(12000, 42)
    # `fit_seleccionado` y no `fit`: el pipeline (`kobra/pipeline.py`) y la
    # cartera manual usan el modelo elegido por validación cruzada y calibrado;
    # este tablero usaba el Gradient Boosting ad-hoc de `fit()`. O sea que el
    # MISMO deudor tenía dos ProbPago según qué pantalla se mirara — medido
    # sobre la cartera de 12.000: 4.635 caían en un decil distinto y la
    # diferencia máxima era de 0,43. El decil decide la prioridad de llamado y
    # el descuento autorizado, así que no es un detalle de presentación.
    #
    # Si el modelo seleccionado no está entrenado todavía, `fit_seleccionado`
    # cae solo en `fit()` y lo dice en `metrics["modelo"]`.
    model = ProbPagoModel().fit_seleccionado(df)
    scored = model.score(df)
    full = negociador.recomendar(scored)
    return full, model.metrics, model.feature_importance()


df, metrics, importancia = cargar()


@st.cache_data(show_spinner="Cargando historial de gestiones…")
def cargar_gestiones():
    csv = os.path.join(ROOT, "data", "kobra_gestiones.csv")
    if os.path.exists(csv):
        return pd.read_csv(csv)
    from data.generate_gestiones import generar as gen_g
    return gen_g(42)


gest = cargar_gestiones()


@st.cache_resource(show_spinner="Preparando el Gestor IA…")
def cargar_modelo_prueba():
    """Modelo ProbPago + baseline para el modo 'Probar mi cartera'."""
    from realtime.mi_cartera import preparar_modelo
    return preparar_modelo()

# ----------------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------------
c1, c2 = st.columns([0.7, 0.3])
with c1:
    _logo_html = ""
    if os.path.exists(_ICON_PATH):
        import base64 as _b64
        with open(_ICON_PATH, "rb") as _f:
            _logo_html = (f"<img src='data:image/png;base64,"
                          f"{_b64.b64encode(_f.read()).decode()}' "
                          f"style='height:52px;vertical-align:-12px;margin-right:10px;'>")
    st.markdown(f"# {_logo_html}MV Kobra AI <span class='kobra-badge'>Cobranzas Inteligentes</span>",
                unsafe_allow_html=True)
    st.caption("ProbPago · Agente IA Negociador · Priorización por valor esperado de recupero")
with c2:
    st.markdown(
        f"<div style='text-align:right;color:#9aa4b2;margin-top:18px'>"
        f"Modelo ProbPago · <b style='color:{PRIMARY}'>AUC {metrics['auc_roc']}</b> · "
        f"Lift decil 10: <b style='color:{PRIMARY}'>{metrics['lift_decil10']}x</b> · "
        f"<i>demo sintética</i></div>",
        unsafe_allow_html=True)

# ----------------------------------------------------------------------------
# Sidebar · filtros
# ----------------------------------------------------------------------------
st.sidebar.header("Filtros")
seg = st.sidebar.multiselect("Segmento", sorted(df["segmento"].unique()),
                             default=sorted(df["segmento"].unique()))
prod = st.sidebar.multiselect("Producto", sorted(df["producto"].unique()),
                              default=sorted(df["producto"].unique()))
tramos_orden = ["1-30", "31-60", "61-90", "91-180", "180+"]
tramo = st.sidebar.multiselect("Tramo de mora", tramos_orden, default=tramos_orden)
prop = st.sidebar.multiselect("Propensión (ProbPago)", ["Alta", "Media", "Baja"],
                              default=["Alta", "Media", "Baja"])
deptos = sorted(df["departamento"].unique())
depto = st.sidebar.multiselect("Departamento", deptos, default=deptos)
monto_min, monto_max = int(df["monto_deuda"].min()), int(df["monto_deuda"].max())
rango_monto = st.sidebar.slider("Monto de deuda (UYU)", monto_min, monto_max,
                                (monto_min, monto_max), step=1000)
prob_min = st.sidebar.slider("ProbPago mínima", 0.0, 1.0, 0.0, 0.05)

st.sidebar.markdown("---")
st.sidebar.caption("Dataset sintético (Uruguay) · sin nombres de clientes · demo comercial")
st.sidebar.markdown("---")
# Consumo del plan, igual que el chip de la app React: el tope no puede
# aparecer recién cuando el cliente ya se chocó contra él.
_PLAN = kplan.estado()
if not _PLAN["ilimitado"]:
    st.sidebar.caption(f"Plan {_PLAN['plan'] or ''} · "
                       f"{_PLAN['usado']} de {_PLAN['cupo']} gestiones este mes")
    st.sidebar.progress(min(1.0, _PLAN["usado"] / _PLAN["cupo"]) if _PLAN["cupo"] else 0.0)
    if _PLAN["bloqueado"]:
        st.sidebar.warning("Cupo del mes agotado. Tu cartera y tus informes siguen "
                           "disponibles; para volver a gestionar, mejorá tu plan en "
                           "mvkobranzaia.com")
    elif _PLAN["excedente"]:
        st.sidebar.info(f"{_PLAN['excedente']} gestiones por encima del plan — "
                        "se facturan como excedente.")
    st.sidebar.markdown("---")
_rol_txt = "Administrador" if ROL_ACTIVO == "admin" else "Gestor"
st.sidebar.caption(f"Sesión: {_rol_txt}")
if st.sidebar.button("Cerrar sesión", use_container_width=True):
    kauth.cerrar_sesion()
    st.rerun()

f = df[
    df["segmento"].isin(seg) & df["producto"].isin(prod) &
    df["tramo_mora"].isin(tramo) & df["segmento_propension"].isin(prop) &
    df["departamento"].isin(depto) &
    df["monto_deuda"].between(*rango_monto) & (df["probpago"] >= prob_min)
].copy()

if f.empty:
    st.warning("No hay deudores para los filtros seleccionados.")
    st.stop()

# ----------------------------------------------------------------------------
# KPIs
# ----------------------------------------------------------------------------
cartera = f["monto_deuda"].sum()
recupero = f["valor_esperado_recupero"].sum()
en_riesgo = f.loc[f["segmento_propension"] == "Baja", "monto_deuda"].sum()

k = st.columns(6)
k[0].metric("Deudores", f"{len(f):,}")
k[1].metric("Cartera (UYU)", f"$U {cartera/1e6:,.1f}M")
k[2].metric("Recupero esperado", f"$U {recupero/1e6:,.1f}M",
            f"{recupero/cartera:.1%} de la cartera")
k[3].metric("ProbPago promedio", f"{f['probpago'].mean():.1%}")
k[4].metric("Mora promedio", f"{f['dias_mora'].mean():.0f} días")
k[5].metric("Cartera en riesgo", f"$U {en_riesgo/1e6:,.1f}M",
            f"{en_riesgo/cartera:.1%}", delta_color="inverse")

st.markdown("---")

# ----------------------------------------------------------------------------
# Tabs
# ----------------------------------------------------------------------------
(tabH, tab1, tab2, tab3, tab4, tab5, tab6, tabAgenda, tab8, tab9, tabERP,
 tabNL2SQL, tabDemoVivo, tab7) = st.tabs(
    ["Guía & Ayuda", "Visión general", "Agente Negociador", "Cartera & Export",
     "Modelo ProbPago", "Copiloto en Vivo", "Gestores & Evolución",
     "Agenda de seguimiento", "Probar mi cartera", "Caso de negocio",
     "Integración ERP", "Preguntá a tu base de datos", "Demo en vivo",
     "⚙ Configuración"])

# ---- Tab Ayuda: guía paso a paso -------------------------------------------
with tabH:
    _est = kconfig.estado()
    def _chip(clave, etiqueta):
        on = _est.get(clave)
        marca = "<span class='kh-ok'>configurada</span>" if on else "<span class='kh-off'>sin configurar</span>"
        return f"<div style='margin:3px 0'><span class='kh-key'>{clave}</span> — {etiqueta} · {marca}</div>"

    st.markdown(
        "<div class='kh-hero'><h2>Bienvenido a MV Kobra AI</h2>"
        "<p>Plataforma de cobranzas inteligentes: prioriza tu cartera, negocia con IA "
        "(voz o WhatsApp), asesora en vivo y mide resultados. Esta guía te lleva paso a "
        "paso; no necesitás saber de programación.</p></div>", unsafe_allow_html=True)

    st.markdown(
        "<div class='kh-grid'>"
        "<div class='kh-card'><div class='kh-num'>1</div><h4>Mirá la demo</h4>"
        "<p>Arranca con una <b>cartera sintética</b> (datos ficticios, sin personas reales). "
        "Recorré <b>Visión general</b>, <b>Agente Negociador</b> y <b>Cartera &amp; Export</b> "
        "para ver KPIs, estrategias y descargas a Excel/CSV.</p></div>"

        "<div class='kh-card'><div class='kh-num'>2</div><h4>Configurá tus claves "
        "<span class='kh-pill'>se guardan</span></h4>"
        "<p>En la pestaña <b>⚙ Configuración</b> cargás las API keys <b>una sola vez</b>: "
        "quedan guardadas y se cargan solas en cada arranque. No hace falta reingresarlas.</p></div>"

        "<div class='kh-card'><div class='kh-num'>3</div><h4>Probá tu propia cartera</h4>"
        "<p>En <b>Probar mi cartera</b> escribís tus contactos en una tabla o subís un "
        "CSV/Excel; el Gestor IA negocia cada caso y descargás los resultados. Privado: "
        "no se sube a ningún lado.</p></div>"

        "<div class='kh-card'><div class='kh-num'>4</div><h4>Llamá de verdad</h4>"
        "<p>Con Twilio configurado (paso 2), el Gestor IA <b>llama por teléfono</b>, negocia "
        "y registra la gestión. Se dispara desde la página <span class='kh-key'>/llamar</span> "
        "del servidor de voz. Guía completa: <b>docs/GUIA_LLAMADA_REAL_TWILIO.md</b>.</p></div>"

        "<div class='kh-card'><div class='kh-num'>5</div><h4>Medí y cumplí</h4>"
        "<p><b>Caso de negocio</b> estima el ROI con tus supuestos. El módulo de "
        "<b>cumplimiento</b> respeta horarios, topes y la lista <i>No Contactar</i> "
        "(opt-out) automáticamente.</p></div>"

        "<div class='kh-card'><div class='kh-num'>6</div><h4>PC y celular, igual de completo</h4>"
        "<p>El dashboard es una <b>app web</b>: en la compu corre local; desde el "
        "<b>celular (Android/iPhone)</b> abrís la misma dirección en el navegador y tenés "
        "<b>exactamente las mismas funciones</b>. En Chrome → <i>Agregar a pantalla de "
        "inicio</i> y queda como una app.</p></div>"
        "</div>", unsafe_allow_html=True)

    st.markdown("### Tus API keys (guardadas, no las reingresás)")
    ca, cb = st.columns([0.62, 0.38])
    with ca:
        st.markdown(
            "<div class='kh-card'>"
            + _chip("OPENAI_API_KEY", "Transcripción de voz (Whisper) — opcional")
            + _chip("ANTHROPIC_API_KEY", "Claude: redacción más natural del Gestor IA — opcional")
            + _chip("TWILIO_ACCOUNT_SID", "Llamadas reales — Account SID")
            + _chip("TWILIO_AUTH_TOKEN", "Llamadas reales — Auth Token")
            + _chip("TWILIO_FROM", "Llamadas reales — tu número Twilio")
            + "<p style='margin-top:10px'>Se cargan y guardan en la pestaña "
              "<b>⚙ Configuración</b>. MV Kobra AI funciona igual sin claves (con menos "
              "extras). Se guardan cifradas/con permisos restringidos, fuera del repo.</p>"
            "</div>", unsafe_allow_html=True)
    with cb:
        st.info("Para editar o guardar tus claves, andá a la pestaña **⚙ Configuración** "
                "(última). Se guardan una vez y listo.")
        st.caption("En el celular: abrí la misma URL del dashboard en Chrome/Safari. "
                   "Mismas pestañas, mismas funciones que en la PC.")

    with st.expander("Cómo hacer una llamada real (Twilio) — paso a paso"):
        st.markdown(
            "1. Creá una cuenta en **twilio.com/try-twilio** (trial gratis) y verificá tu "
            "celular en *Verified Caller IDs*.\n"
            "2. Comprá un número con *Voice* y anotá **Account SID**, **Auth Token** y el número.\n"
            "3. Cargalos en **⚙ Configuración** (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM`).\n"
            "4. Poné el servidor de voz accesible (ngrok) y abrí `…/llamar`.\n"
            "5. Ingresá el teléfono y el monto → **Llamar ahora**. El bot negocia y registra la gestión.\n\n"
            "⚠ Necesitás el **consentimiento** de la persona. Empezá probando con tu propio celular.")
    with st.expander("⚖ Registrar MV Kobra AI legalmente en Uruguay (para que no te la copien)"):
        st.markdown(
            "- El **código ya es tuyo** por derecho de autor automático (Ley 9.739/17.616).\n"
            "- Registralo barato en la **Biblioteca Nacional** (~USD 20–60) para tener fecha cierta.\n"
            "- Registrá la **marca “MV Kobra AI”** en la **DNPI** (~USD 200–500 por 10 años) al salir a vender.\n"
            "- La **idea** no se registra; te protegés con código + marca + contratos/NDAs.\n\n"
            "Guía completa: **docs/GUIA_REGISTRO_LEGAL_URUGUAY.md**.")

    st.divider()
    st.markdown("### Asistente de ayuda — preguntale al programa")
    st.caption("Escribí tu duda sobre MV Kobra AI en español y te responde al instante, "
               "usando la propia documentación del producto (no inventa funciones). "
               "Con `ANTHROPIC_API_KEY` cargada responde redactado; sin key, te muestra "
               "la sección exacta de la documentación que contesta tu duda.")
    if "ayuda_chat" not in st.session_state:
        st.session_state["ayuda_chat"] = []
    for _p, _r in st.session_state["ayuda_chat"]:
        with st.chat_message("user"):
            st.markdown(_p)
        with st.chat_message("assistant"):
            st.markdown(_r["respuesta"])
            if _r.get("fuentes"):
                st.caption("Fuentes: " + " · ".join(f"`{f}`" for f in _r["fuentes"]))
    with st.form("form_ayuda_ia", clear_on_submit=True):
        _ay_c1, _ay_c2 = st.columns([0.82, 0.18])
        _ay_preg = _ay_c1.text_input(
            "Tu pregunta", key="ayuda_pregunta", label_visibility="collapsed",
            placeholder="Ej.: ¿qué necesito para que llame de verdad por teléfono?")
        _ay_enviar = _ay_c2.form_submit_button("Preguntar", type="primary",
                                               use_container_width=True)
    if _ay_enviar and _ay_preg.strip():
        try:
            with st.spinner("Buscando en la documentación…"):
                _ay_resp = kayuda.responder(_ay_preg.strip())
        except Exception as _ay_e:
            _ay_resp = {"respuesta": f"No pude responder ahora ({str(_ay_e)[:120]}). "
                                     "Probá de nuevo o usá el buzón de contacto de abajo.",
                        "fuentes": [], "modo": "error"}
        st.session_state["ayuda_chat"].append((_ay_preg.strip(), _ay_resp))
        st.rerun()

    st.divider()
    st.markdown("### Buzón de contacto")
    st.caption("Enviá tu consulta y se abre tu correo con el mensaje listo para "
               "**vieraschiavi@gmail.com** (asunto, pregunta y tus datos de contacto).")
    import urllib.parse as _urlparse
    _cc1, _cc2, _cc3 = st.columns(3)
    _ct_nom = _cc1.text_input("Nombre", key="ct_nom")
    _ct_mail = _cc2.text_input("Tu email", key="ct_mail")
    _ct_tel = _cc3.text_input("Teléfono de contacto", key="ct_tel")
    _ct_asu = st.text_input("Asunto", key="ct_asu")
    _ct_pre = st.text_area("Consulta / pregunta", key="ct_pre", height=120)
    _ct_subject = "[MV Kobra AI] " + (_ct_asu.strip() or "Consulta")
    _ct_body = (_ct_pre.strip() + "\n\n----------------------------\nDatos de contacto\n"
                + "Nombre: " + (_ct_nom.strip() or "-") + "\n"
                + "Email: " + (_ct_mail.strip() or "-") + "\n"
                + "Teléfono: " + (_ct_tel.strip() or "-") + "\n"
                + "Enviado desde: app MV Kobra AI")
    _ct_mailto = ("mailto:vieraschiavi@gmail.com?subject="
                  + _urlparse.quote(_ct_subject) + "&body=" + _urlparse.quote(_ct_body))
    st.link_button("✉ Enviar consulta por email", _ct_mailto, use_container_width=True)
    st.caption("Se abre tu app de correo (Gmail/Outlook) con el mensaje listo. "
               "También podés escribir directo a vieraschiavi@gmail.com.")

# ---- Tab 1: Visión general -------------------------------------------------
with tab1:
    g1, g2 = st.columns(2)
    with g1:
        rec_tramo = f.groupby("tramo_mora", observed=True).agg(
            cartera=("monto_deuda", "sum"),
            recupero=("valor_esperado_recupero", "sum")).reindex(tramos_orden).dropna()
        fig = go.Figure()
        fig.add_bar(x=rec_tramo.index, y=rec_tramo["cartera"]/1e6,
                    name="Cartera", marker_color="#3a4157")
        fig.add_bar(x=rec_tramo.index, y=rec_tramo["recupero"]/1e6,
                    name="Recupero esperado", marker_color=PRIMARY)
        fig.update_layout(title="Cartera vs. recupero esperado por tramo de mora (M$U)",
                          barmode="overlay", template="plotly_dark", height=360,
                          legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)
    with g2:
        prop_cnt = f["segmento_propension"].value_counts().reindex(["Alta", "Media", "Baja"])
        fig = px.pie(values=prop_cnt.values, names=prop_cnt.index, hole=0.55,
                     color=prop_cnt.index,
                     color_discrete_map={"Alta": PRIMARY, "Media": "#FDCB6E", "Baja": "#FF7675"})
        fig.update_layout(title="Distribución por propensión de pago",
                          template="plotly_dark", height=360)
        st.plotly_chart(fig, use_container_width=True)

    g3, g4 = st.columns(2)
    with g3:
        seg_rec = f.groupby("segmento").agg(
            recupero=("valor_esperado_recupero", "sum")).reset_index()
        fig = px.bar(seg_rec, x="segmento", y="recupero", color="segmento",
                     color_discrete_sequence=SEQ,
                     title="Recupero esperado por segmento (UYU)")
        fig.update_layout(template="plotly_dark", height=340, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)
    with g4:
        top_dep = f.groupby("departamento").agg(
            cartera=("monto_deuda", "sum")).nlargest(10, "cartera").reset_index()
        fig = px.bar(top_dep, x="cartera", y="departamento", orientation="h",
                     color="cartera", color_continuous_scale="Teal",
                     title="Top 10 departamentos por cartera (UYU)")
        fig.update_layout(template="plotly_dark", height=340,
                          yaxis=dict(autorange="reversed"), coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

# ---- Tab 2: Agente Negociador ----------------------------------------------
with tab2:
    st.subheader("Estrategias recomendadas por el Agente IA")
    res = negociador.resumen_estrategias(f)
    cc = st.columns([0.55, 0.45])
    with cc[0]:
        fig = px.bar(res, x="recupero_esperado_uyu", y="estrategia", orientation="h",
                     color="estrategia", color_discrete_sequence=SEQ,
                     title="Recupero esperado por estrategia (UYU)")
        fig.update_layout(template="plotly_dark", height=380, showlegend=False,
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)
    with cc[1]:
        st.dataframe(
            res.assign(
                cartera_uyu=res["cartera_uyu"].map("{:,.0f}".format),
                recupero_esperado_uyu=res["recupero_esperado_uyu"].map("{:,.0f}".format),
                probpago_prom=res["probpago_prom"].map("{:.1%}".format),
                descuento_prom=res["descuento_prom"].map("{:.0%}".format)),
            use_container_width=True, hide_index=True, height=380)

    st.markdown("### Simulador de negociación por deudor")
    st.caption("Elegí un deudor prioritario y obtené el guion listo para enviar.")
    top = f.nsmallest(200, "prioridad")[
        ["id_deudor", "prioridad", "probpago", "monto_deuda", "estrategia"]]
    sel = st.selectbox(
        "Deudor (Top 200 por prioridad)",
        top["id_deudor"].tolist(),
        format_func=lambda x: (
            f"{x} · prio #{int(top.loc[top.id_deudor==x,'prioridad'].iloc[0])} · "
            f"ProbPago {top.loc[top.id_deudor==x,'probpago'].iloc[0]:.0%} · "
            f"$U {top.loc[top.id_deudor==x,'monto_deuda'].iloc[0]:,.0f}"))
    r = f[f["id_deudor"] == sel].iloc[0]
    m = st.columns(4)
    m[0].metric("ProbPago", f"{r['probpago']:.0%}")
    m[1].metric("Estrategia", r["estrategia"])
    m[2].metric("Descuento sug.", f"{r['descuento_recomendado']:.0%}")
    m[3].metric("Recupero esperado", f"$U {r['valor_esperado_recupero']:,.0f}")
    m2 = st.columns(4)
    m2[0].metric("Canal", r["canal_recomendado"])
    m2[1].metric("Plan", f"{int(r['plan_cuotas'])} cuota(s)")
    m2[2].metric("Días de mora", f"{int(r['dias_mora'])}")
    m2[3].metric("Score buró", f"{int(r['score_buro'])}")
    st.markdown(f"<div class='guion-box'><b>Guion sugerido</b><br>{r['guion']}</div>",
                unsafe_allow_html=True)

# ---- Tab 3: Cartera & Export -----------------------------------------------
with tab3:
    st.subheader("Cartera priorizada")
    cols_show = ["prioridad", "id_deudor", "segmento", "producto", "departamento",
                 "tramo_mora", "monto_deuda", "probpago", "segmento_propension",
                 "estrategia", "descuento_recomendado", "canal_recomendado",
                 "valor_esperado_recupero"]
    tabla = f.sort_values("prioridad")[cols_show].reset_index(drop=True)
    tabla["probpago"] = (tabla["probpago"] * 100).round(0)
    tabla["descuento_recomendado"] = (tabla["descuento_recomendado"] * 100).round(0)
    st.dataframe(
        tabla, use_container_width=True, height=460, hide_index=True,
        column_config={
            "monto_deuda": st.column_config.NumberColumn("Monto (UYU)", format="%.0f"),
            "valor_esperado_recupero": st.column_config.NumberColumn(
                "Recupero esp. (UYU)", format="%.0f"),
            "probpago": st.column_config.ProgressColumn(
                "ProbPago", format="%.0f%%", min_value=0, max_value=100),
            "descuento_recomendado": st.column_config.NumberColumn(
                "Descuento", format="%.0f%%"),
        })

    st.markdown("#### ⬇ Exportar para reporting")
    exp = f.sort_values("prioridad")[cols_show + ["guion"]]
    csv_bytes = exp.to_csv(index=False).encode("utf-8-sig")
    xbuf = io.BytesIO()
    with pd.ExcelWriter(xbuf, engine="xlsxwriter") as xl:
        exp.to_excel(xl, sheet_name="Cartera_priorizada", index=False)
        negociador.resumen_estrategias(f).to_excel(
            xl, sheet_name="Resumen_estrategias", index=False)
    e1, e2, e3 = st.columns([0.2, 0.2, 0.6])
    e1.download_button("Descargar CSV", csv_bytes, "kobra_cartera.csv",
                       "text/csv", use_container_width=True)
    e2.download_button("Descargar Excel", xbuf.getvalue(), "kobra_cartera.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)
    e3.caption(f"{len(exp):,} registros filtrados · incluye estrategia y guion por deudor.")

# ---- Tab 4: Modelo ---------------------------------------------------------
with tab4:
    st.subheader("Cómo funciona ProbPago")
    mc = st.columns(4)
    mc[0].metric("AUC-ROC", metrics["auc_roc"])
    mc[1].metric("AUC-PR", metrics["auc_pr"])
    mc[2].metric("Lift decil 10", f"{metrics['lift_decil10']}x")
    mc[3].metric("Tasa pago base", f"{metrics['tasa_pago_base']:.1%}")
    st.caption(f"Entrenado con {metrics['n_train']:,} casos · validado con "
               f"{metrics['n_test']:,} · {metrics.get('modelo', 'Gradient Boosting')}. "
               "`kobra.train` compara LogReg/RF/GBM/HistGB con CV, elige el mejor por "
               "ROC-AUC y lo calibra — ese es el modelo que se usa acá cuando está entrenado.")
    st.warning("⚠ **Métricas sobre datos sintéticos (demo).** La etiqueta de pago se genera "
               "con una función conocida, así que un AUC alto acá es esperable por construcción "
               "y **no es evidencia de desempeño real**. Con la cartera real del cliente, el "
               "modelo se selecciona y valida de nuevo con **validación temporal (walk-forward)** "
               "y features sin leakage. Lo demostrable es la metodología, no este número.")

    ci1, ci2 = st.columns(2)
    with ci1:
        imp = importancia.head(12).sort_values("importancia")
        fig = px.bar(imp, x="importancia", y="feature", orientation="h",
                     color="importancia", color_continuous_scale="Teal",
                     title="Principales drivers de la probabilidad de pago")
        fig.update_layout(template="plotly_dark", height=440, coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)
    with ci2:
        fig = px.histogram(f, x="probpago", nbins=30, color="segmento_propension",
                           color_discrete_map={"Alta": PRIMARY, "Media": "#FDCB6E",
                                               "Baja": "#FF7675"},
                           title="Distribución de ProbPago en la cartera filtrada")
        fig.update_layout(template="plotly_dark", height=440,
                          legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, use_container_width=True)
    st.info("**ProbPago** estima la probabilidad de recupero de cada deudor. "
            "El **Agente Negociador** usa esa probabilidad + monto + mora para elegir "
            "la estrategia que **maximiza el recupero esperado minimizando la quita**, "
            "y prioriza la cartera por valor esperado (UYU).")

# ---- Tab 5: Copiloto de Negociación en Vivo -------------------------------
with tab5:
    st.subheader("Copiloto de Negociación en Vivo")
    st.caption("Analiza la conversación (WhatsApp o transcripción de llamada) en tiempo real: "
               "sentimiento del cliente, técnicas del gestor, calidad y la próxima jugada sugerida.")

    ejemplo_path = os.path.join(ROOT, "data", "ejemplo_whatsapp.txt")
    ejemplo_txt = ""
    if os.path.exists(ejemplo_path):
        with open(ejemplo_path, encoding="utf-8") as fh:
            ejemplo_txt = fh.read()

    cfg = st.columns([0.5, 0.25, 0.25])
    with cfg[0]:
        up = st.file_uploader("Subir conversación (.txt export de WhatsApp o transcripción)",
                              type=["txt"])
    with cfg[1]:
        canal = st.selectbox("Canal", ["whatsapp", "llamada"])
    with cfg[2]:
        deudor_ref = st.selectbox(
            "Vincular deudor (ProbPago)",
            ["(ninguno)"] + f.nsmallest(100, "prioridad")["id_deudor"].tolist())

    texto_conv = up.read().decode("utf-8", errors="ignore") if up else st.text_area(
        "…o pegá la conversación acá", value=ejemplo_txt, height=220,
        help="Formato WhatsApp: [DD/MM/AAAA, HH:MM:SS] Nombre: mensaje  ·  "
             "o transcripción: 'Gestor: …' / 'Cliente: …'")

    probpago_ref, estrategia_ref = None, None
    if deudor_ref != "(ninguno)":
        rr = f[f["id_deudor"] == deudor_ref].iloc[0]
        probpago_ref, estrategia_ref = float(rr["probpago"]), rr["estrategia"]

    if st.button("⚡ Analizar negociación", type="primary") or texto_conv:
        if not texto_conv.strip():
            st.info("Cargá o pegá una conversación para analizar.")
        else:
            res = copiloto.analizar_conversacion(
                texto_conv, canal=canal, probpago=probpago_ref, estrategia=estrategia_ref,
                idioma=copiloto.idioma_configurado())
            cop = res["copiloto"]
            meta = res["meta"]

            mc = st.columns(5)
            mc[0].metric("Calidad de gestión", f"{res['calidad']['score_total']:.0f}/100")
            clima_emoji = {"positivo": "●", "neutro": "●", "negativo": "●"}[cop["clima_etiqueta"]]
            mc[1].metric("Clima del cliente", f"{clima_emoji} {cop['clima_etiqueta']}",
                         f"{cop['clima_emocional']:+.2f}")
            mc[2].metric("Mensajes", meta["mensajes"])
            mc[3].metric("1ª respuesta",
                         f"{meta['tiempo_primera_respuesta_min']:.0f} min"
                         if meta["tiempo_primera_respuesta_min"] else "—")
            tec_on = [k for k, v in res["tecnicas"].items() if v]
            mc[4].metric("Técnicas usadas", len(tec_on))

            cL, cR = st.columns([0.58, 0.42])
            with cL:
                st.markdown("##### Sentimiento turno a turno")
                turnos = cop["sentimientos_turnos"]
                dft = pd.DataFrame(turnos)
                dft["Turno"] = dft["orden"] + 1
                fig = go.Figure()
                for emisor, col in [("cliente", "#FF7675"), ("gestor", PRIMARY)]:
                    d = dft[dft["emisor"] == emisor]
                    fig.add_trace(go.Scatter(
                        x=d["Turno"], y=d["score"], mode="lines+markers",
                        name=emisor.capitalize(), line=dict(color=col, width=3),
                        hovertext=d["texto"], hoverinfo="text+y"))
                fig.add_hline(y=0, line_dash="dot", line_color="#555")
                fig.update_layout(template="plotly_dark", height=330,
                                  yaxis=dict(title="Sentimiento", range=[-1, 1]),
                                  legend=dict(orientation="h", y=1.15))
                st.plotly_chart(fig, use_container_width=True)

                if cop["emociones_cliente"]:
                    st.markdown("**Emociones detectadas en el cliente:** " +
                                " ".join(f"`{e}`" for e in cop["emociones_cliente"]))
                if tec_on:
                    st.markdown("**Técnicas de negociación del gestor:** " +
                                " ".join(f"`{t}`" for t in tec_on))

            with cR:
                st.markdown("##### Sugerencias para el gestor")
                for titulo, detalle in cop["sugerencias"]:
                    st.markdown(
                        f"<div class='guion-box'><b>{titulo}</b><br>{detalle}</div>",
                        unsafe_allow_html=True)
                st.markdown("##### Próxima frase sugerida")
                st.markdown(f"<div class='guion-box'>{cop['proxima_frase']}</div>",
                            unsafe_allow_html=True)

            with st.expander("Detalle de criterios de calidad"):
                crit = pd.DataFrame([
                    {"Criterio": c["nombre"], "Peso %": c["peso"],
                     "Score": c["score"], "Cumple": "✓" if c["cumple"] else "⚠"}
                    for c in res["calidad"]["criterios"].values()])
                st.dataframe(crit, use_container_width=True, hide_index=True)

            if os.getenv("ANTHROPIC_API_KEY"):
                with st.spinner("Enriqueciendo con Claude…"):
                    extra = copiloto.evaluar_con_claude(texto_conv)
                if extra:
                    st.success("Evaluación cualitativa (Claude)")
                    st.json(extra)
            else:
                st.caption("Configurá `ANTHROPIC_API_KEY` (evaluación Claude) u "
                           "`OPENAI_API_KEY` (transcripción Whisper) para enriquecer el análisis. "
                           "El copiloto funciona sin claves.")

    # --- Análisis de VOZ: diarización + emoción acústica ---
    st.markdown("---")
    st.markdown("### Analizar grabación de la llamada (voz)")
    st.caption("Diarización (quién habla) + emoción acústica por prosodia (tono, energía, "
               "ritmo). Detecta la tensión del cliente en la voz, más allá de las palabras.")
    from kobra import voz as kvoz
    audio_up = st.file_uploader("Subir grabación (.wav)", type=["wav"], key="audio_up")
    audio_demo = os.path.join(ROOT, "data", "ejemplo_llamada.wav")
    usar_demo = st.checkbox("Usar grabación de demo (dual-channel)", value=not audio_up)

    audio_path = None
    if audio_up:
        audio_path = os.path.join(SCRATCH, "subida.wav")
        os.makedirs(SCRATCH, exist_ok=True)
        with open(audio_path, "wb") as fh:
            fh.write(audio_up.read())
    elif usar_demo and os.path.exists(audio_demo):
        audio_path = audio_demo

    if audio_path and os.path.exists(audio_path):
        # Transcripción: Whisper si hay OPENAI_API_KEY; si no, alinea el texto
        # de la conversación pegada arriba a los hablantes diarizados.
        tt = None
        if texto_conv.strip():
            _c = copiloto.parsear_conversacion(texto_conv, nombre_gestor="Gestor")
            tt = [{"emisor": t.emisor, "texto": t.texto} for t in _c.turnos]
        try:
            # El plan se aplica IGUAL por las dos vías de arranque. Si el cupo
            # solo se controlara en la app React, abrir el mismo paquete por
            # el dashboard daría gestiones infinitas — exactamente el agujero
            # que ya había con el vencimiento de la demo (ver kobra/edicion.py).
            kplan.exigir("voz", "el copiloto de voz")
            kplan.verificar_cupo()
            res_audio = kvoz.copiloto_desde_audio(
                audio_path, transcript_turnos=tt, probpago=probpago_ref,
                estrategia=estrategia_ref, idioma=copiloto.idioma_configurado())
            va = res_audio["voz"]
            kplan.registrar_gestion()
        except kplan.LimitePlan as e:
            va = res_audio = None
            st.warning(e.mensaje)
        except Exception as e:
            va = res_audio = None
            st.error(f"No se pudo analizar el audio: {e}")
        if va:
            st.audio(audio_path)
            vm = st.columns(4)
            vm[0].metric("Canales", va["canales"])
            vm[1].metric("Diarización", va["modo_diarizacion"])
            vm[2].metric("Duración", f"{va['duracion_seg']:.0f}s")
            vm[3].metric("Segmentos", len(va["timeline"]))

            tl = pd.DataFrame(va["timeline"])
            EMO_COL = {"enojo": "#FF4757", "frustracion": "#FF7675", "ansiedad": "#FDCB6E",
                       "resignacion": "#a29bfe", "neutro": "#74B9FF", "positivo": PRIMARY}
            v1, v2 = st.columns([0.6, 0.4])
            with v1:
                fig = go.Figure()
                vistos = set()
                for _, r in tl.iterrows():
                    emo = r["emocion_voz"]
                    fig.add_trace(go.Bar(
                        y=[r["hablante"]], x=[r["fin"] - r["inicio"]], base=[r["inicio"]],
                        orientation="h", marker_color=EMO_COL.get(emo, "#74B9FF"),
                        name=emo, legendgroup=emo, showlegend=emo not in vistos,
                        hovertemplate=(f"{r['hablante']} · {emo}<br>"
                                       f"{r['inicio']}-{r['fin']}s<br>"
                                       f"arousal {r['arousal']:.2f} · val {r['valencia']:+.2f}"
                                       "<extra></extra>")))
                    vistos.add(emo)
                fig.update_layout(template="plotly_dark", height=300, barmode="overlay",
                                  title="Diarización + emoción acústica en el tiempo",
                                  xaxis_title="segundos", legend=dict(orientation="h", y=1.3))
                st.plotly_chart(fig, use_container_width=True)
            with v2:
                fig = go.Figure()
                for h, col in [("Cliente", "#FF7675"), ("Gestor", PRIMARY)]:
                    d = tl[tl["hablante"] == h]
                    if not d.empty:
                        fig.add_trace(go.Scatter(
                            x=d["inicio"], y=d["valencia"], mode="lines+markers",
                            name=h, line=dict(color=col, width=3)))
                fig.add_hline(y=0, line_dash="dot", line_color="#555")
                fig.update_layout(template="plotly_dark", height=300,
                                  title="Valencia (voz) por hablante",
                                  yaxis=dict(title="valencia", range=[-1, 1]),
                                  xaxis_title="segundos", legend=dict(orientation="h", y=1.25))
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("**Emoción de voz dominante por hablante:**")
            rp = st.columns(len(va["resumen_por_hablante"]) or 1)
            for i, (h, r) in enumerate(va["resumen_por_hablante"].items()):
                rp[i].metric(f"{h}", r["emocion_dominante"],
                             f"arousal {r['arousal_prom']:.2f} · val {r['valencia_prom']:+.2f}")
            # --- Transcripción alineada por hablante + fusión voz/texto ---
            if res_audio and res_audio.get("turnos"):
                modo = res_audio["modo_transcripcion"]
                etiqueta_modo = {"whisper": "Whisper (timestamps reales)",
                                 "alineado": "alineada al texto provisto",
                                 "sin_texto": "sin texto"}.get(modo, modo)
                st.markdown(f"##### Transcripción alineada por hablante · *{etiqueta_modo}*")
                if modo == "alineado":
                    st.caption("Sin `OPENAI_API_KEY`: se alineó el texto de la conversación de "
                               "arriba a los hablantes. Con Whisper configurado, se transcribe el "
                               "audio real con marcas de tiempo por segmento.")
                trn = pd.DataFrame(res_audio["turnos"])
                if not trn.empty:
                    trn_show = trn[["inicio", "fin", "hablante", "texto",
                                    "emocion_voz", "sent_texto", "sent_fusion"]].copy()
                    st.dataframe(
                        trn_show, use_container_width=True, hide_index=True,
                        column_config={
                            "inicio": st.column_config.NumberColumn("Ini (s)", format="%.1f"),
                            "fin": st.column_config.NumberColumn("Fin (s)", format="%.1f"),
                            "emocion_voz": "Emoción (voz)",
                            "sent_texto": st.column_config.NumberColumn("Sent. texto", format="%.2f"),
                            "sent_fusion": st.column_config.NumberColumn("Sent. voz+texto", format="%.2f"),
                        })
                if res_audio.get("copiloto"):
                    st.markdown("##### Asesoría del copiloto (sobre la transcripción real)")
                    for titulo, detalle in res_audio["copiloto"]["sugerencias"]:
                        st.markdown(f"<div class='guion-box'><b>{titulo}</b><br>{detalle}</div>",
                                    unsafe_allow_html=True)

            st.info("**Fusión voz + texto:** el motor combina la señal acústica con el "
                    "sentimiento del texto — la columna *Sent. voz+texto* muestra cómo la "
                    "**voz tensa del cliente** empuja la alerta más allá de las palabras. "
                    "En producción se conecta al audio del **softphone/PBX (Avaya, Genesys…)** "
                    "por dual-channel/SIPREC, no al micrófono de la PC.")

# ---- Tab 6: Gestores & Evolución ------------------------------------------
with tab6:
    st.subheader("Gestores & Evolución de la gestión")
    st.caption("Qué características suceden más por tramo/segmento, cómo evolucionan mes a mes, "
               "su impacto en la cobranza y si los gestores mejoran con las herramientas de MV Kobra AI.")
    st.warning("⚠ **Datos ilustrativos (demo).** El historial de gestiones es sintético y el "
               "\"efecto MV Kobra AI\" está inyectado por el generador para demostrar la **metodología "
               "de medición** (grupo con vs. sin herramienta, evolución por cohorte). Los uplifts "
               "que ves acá **no son resultados medidos**. Con el registro post-llamada, esta "
               "misma pestaña se alimenta de llamadas reales y los números pasan a ser evidencia.")

    # Filtros propios del historial
    fg = st.columns(4)
    with fg[0]:
        g_meses = sorted(gest["mes"].unique())
        rango_m = st.select_slider("Rango de meses", options=g_meses,
                                   value=(g_meses[0], g_meses[-1]))
    with fg[1]:
        g_seg = st.multiselect("Segmento ", sorted(gest["segmento"].unique()),
                               default=sorted(gest["segmento"].unique()))
    with fg[2]:
        g_can = st.multiselect("Canal", sorted(gest["canal"].unique()),
                               default=sorted(gest["canal"].unique()))
    with fg[3]:
        g_gestor = st.multiselect("Gestor", sorted(gest["gestor"].unique()),
                                  default=sorted(gest["gestor"].unique()))

    mask = (gest["mes"].between(rango_m[0], rango_m[1]) &
            gest["segmento"].isin(g_seg) & gest["canal"].isin(g_can) &
            gest["gestor"].isin(g_gestor))
    gf = gest[mask].copy()

    if gf.empty:
        st.warning("No hay gestiones para los filtros seleccionados.")
    else:
        # --- Impacto MV Kobra AI (KPIs) ---
        ik = analitica.impacto_kobra(gf)
        st.markdown("#### Impacto de las herramientas MV Kobra AI *(ilustrativo · datos sintéticos)*")
        ck = st.columns(4)
        ck[0].metric("Calidad de gestión", f"{ik['con_kobra']['calidad_prom']:.0f}",
                     f"+{ik['uplift_calidad']:.1f} vs sin MV Kobra AI")
        ck[1].metric("Tasa de conversión", f"{ik['con_kobra']['tasa_conversion']:.0%}",
                     f"+{ik['uplift_conversion']*100:.1f} pp")
        ck[2].metric("Tasa de recupero", f"{ik['con_kobra']['tasa_recupero']:.0%}",
                     f"+{ik['uplift_recupero']*100:.1f} pp")
        ck[3].metric("Sentimiento cliente", f"{ik['con_kobra']['sentimiento_prom']:+.2f}",
                     f"{(ik['con_kobra']['sentimiento_prom']-ik['sin_kobra']['sentimiento_prom']):+.2f}")

        # --- Evolución temporal ---
        st.markdown("#### Evolución mes a mes")
        ev = analitica.evolucion_mensual(gf)
        ev_kobra = analitica.evolucion_mensual(gf, por="usa_kobra")
        e1, e2 = st.columns(2)
        with e1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=ev["mes"], y=ev["calidad_prom"], mode="lines+markers",
                                     name="Calidad", line=dict(color=PRIMARY, width=3)))
            fig.add_trace(go.Scatter(x=ev["mes"], y=ev["tasa_conversion"]*100, mode="lines+markers",
                                     name="Conversión %", line=dict(color=ACCENT, width=3), yaxis="y2"))
            fig.update_layout(template="plotly_dark", height=340,
                              title="Calidad y conversión en el tiempo",
                              yaxis=dict(title="Calidad"),
                              yaxis2=dict(title="Conversión %", overlaying="y", side="right"),
                              legend=dict(orientation="h", y=1.15))
            st.plotly_chart(fig, use_container_width=True)
        with e2:
            fig = px.line(ev_kobra, x="mes", y="calidad_prom", color="usa_kobra",
                          markers=True, color_discrete_map={True: PRIMARY, False: "#FF7675"},
                          title="Calidad: con MV Kobra AI vs. sin MV Kobra AI",
                          labels={"usa_kobra": "Usa MV Kobra AI"})
            fig.update_layout(template="plotly_dark", height=340,
                              legend=dict(orientation="h", y=1.15))
            st.plotly_chart(fig, use_container_width=True)

        # --- Características por dimensión ---
        st.markdown("#### Características más frecuentes")
        dim = st.selectbox("Analizar por", ["tramo_mora", "segmento", "canal", "producto"])
        c1, c2 = st.columns([0.55, 0.45])
        with c1:
            car = analitica.caracteristicas_por(gf, dim)
            car_show = car[[dim, "gestiones", "calidad_prom", "tasa_conversion",
                            "tasa_recupero", "emocion_top"]].copy()
            car_show["tasa_conversion"] = (car_show["tasa_conversion"] * 100).round(0)
            car_show["tasa_recupero"] = (car_show["tasa_recupero"] * 100).round(0)
            st.dataframe(
                car_show, use_container_width=True, hide_index=True,
                column_config={
                    "tasa_conversion": st.column_config.NumberColumn("Conversión", format="%.0f%%"),
                    "tasa_recupero": st.column_config.NumberColumn("Recupero", format="%.0f%%"),
                    "calidad_prom": st.column_config.NumberColumn("Calidad", format="%.0f"),
                })
        with c2:
            mat = analitica.matriz_emociones(gf, dim if dim in
                                             ("tramo_mora", "segmento") else "tramo_mora")
            mcol = mat.columns[0]
            fig = px.imshow(mat.set_index(mcol).T, text_auto=".0f", aspect="auto",
                            color_continuous_scale="Teal",
                            title=f"Emociones del cliente por {mcol} (%)")
            fig.update_layout(template="plotly_dark", height=340, coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)

        # --- Impacto de la calidad en el recupero ---
        st.markdown("#### Impacto de la calidad de gestión en la cobranza")
        ic = analitica.impacto_calidad(gf)
        i1, i2 = st.columns([0.6, 0.4])
        with i1:
            fig = go.Figure()
            fig.add_bar(x=ic["rango_calidad"].astype(str), y=ic["tasa_conversion"]*100,
                        marker_color=PRIMARY, name="Conversión %")
            fig.add_trace(go.Scatter(x=ic["rango_calidad"].astype(str), y=ic["tasa_recupero"]*100,
                                     mode="lines+markers", name="Recupero %",
                                     line=dict(color=YELLOW, width=3)))
            fig.update_layout(template="plotly_dark", height=330,
                              title="A mayor calidad de gestión, mayor conversión y recupero",
                              xaxis_title="Rango de calidad", legend=dict(orientation="h", y=1.2))
            st.plotly_chart(fig, use_container_width=True)
        with i2:
            st.metric("Correlación calidad ↔ conversión",
                      f"{ic.attrs['correlacion_calidad_conversion']:.2f}")
            st.info("La calidad de gestión (medida por el Copiloto) se traduce en "
                    "más conversión y más recupero. MV Kobra AI la mejora sistemáticamente.")

        # --- Gestor IA vs. humanos ---
        comp = analitica.comparativa_ia(gf)
        if comp:
            st.markdown("#### Gestor IA vs. gestores humanos "
                        "*(ilustrativo · datos sintéticos)*")
            st.caption("El Gestor IA atiende/llama por voz o WhatsApp, negocia según "
                       "ProbPago, completa los campos ERP y registra cada gestión — "
                       "hasta 50 conversaciones simultáneas. Acá se mide contra los "
                       "humanos en los mismos meses.")
            ci_ = st.columns(4)
            ci_[0].metric("Gestiones / gestor / mes",
                          f"{comp['ia']['gestiones_por_gestor_mes']:,.0f}",
                          f"{comp['volumen_x']}x vs humano")
            ci_[1].metric("Conversión IA", f"{comp['ia']['tasa_conversion']:.0%}",
                          f"{(comp['ia']['tasa_conversion']-comp['humanos']['tasa_conversion'])*100:+.1f} pp vs humanos")
            ci_[2].metric("Calidad IA", f"{comp['ia']['calidad_prom']:.0f}",
                          f"{comp['ia']['calidad_prom']-comp['humanos']['calidad_prom']:+.1f} vs humanos")
            ci_[3].metric("Recupero IA (período)",
                          f"$U {comp['ia']['recupero_total']/1e6:,.1f}M")
            comp_df = pd.DataFrame({
                "Métrica": ["Conversión %", "Calidad", "Gestiones/gestor/mes"],
                "Gestor IA": [comp["ia"]["tasa_conversion"] * 100,
                              comp["ia"]["calidad_prom"],
                              comp["ia"]["gestiones_por_gestor_mes"]],
                "Humanos": [comp["humanos"]["tasa_conversion"] * 100,
                            comp["humanos"]["calidad_prom"],
                            comp["humanos"]["gestiones_por_gestor_mes"]],
            })
            fig = go.Figure()
            fig.add_bar(x=comp_df["Métrica"], y=comp_df["Gestor IA"],
                        name="Gestor IA", marker_color=ACCENT)
            fig.add_bar(x=comp_df["Métrica"], y=comp_df["Humanos"],
                        name="Humanos", marker_color=PRIMARY)
            fig.update_layout(template="plotly_dark", height=300, barmode="group",
                              title="Gestor IA vs. humanos (mismos meses)",
                              legend=dict(orientation="h", y=1.2))
            st.plotly_chart(fig, use_container_width=True)

        # --- Ranking y mejora por gestor ---
        st.markdown("#### Ranking de gestores y mejora en el tiempo")
        r1, r2 = st.columns(2)
        with r1:
            rk = analitica.ranking_gestores(gf)[
                ["gestor", "gestiones", "calidad_prom", "tasa_conversion",
                 "recupero", "usa_kobra"]].copy()
            rk["tasa_conversion"] = (rk["tasa_conversion"] * 100).round(0)
            st.dataframe(
                rk, use_container_width=True, hide_index=True, height=330,
                column_config={
                    "recupero": st.column_config.NumberColumn("Recupero (UYU)", format="%.0f"),
                    "tasa_conversion": st.column_config.NumberColumn("Conversión", format="%.0f%%"),
                    "calidad_prom": st.column_config.NumberColumn("Calidad", format="%.0f"),
                    "usa_kobra": st.column_config.CheckboxColumn("MV Kobra AI"),
                })
        with r2:
            mej = analitica.mejora_por_gestor(gf)
            if not mej.empty:
                fig = px.bar(mej, x="delta_calidad", y="gestor", orientation="h",
                             color="usa_kobra", color_discrete_map={True: PRIMARY, False: "#FF7675"},
                             title="Mejora de calidad (últimos 3m vs. primeros 3m)",
                             labels={"delta_calidad": "Δ calidad", "usa_kobra": "Usa MV Kobra AI"})
                fig.update_layout(template="plotly_dark", height=330,
                                  yaxis=dict(autorange="reversed"),
                                  legend=dict(orientation="h", y=1.15))
                st.plotly_chart(fig, use_container_width=True)

        # --- Export ---
        st.markdown("#### ⬇ Exportar analítica")
        xbuf2 = io.BytesIO()
        with pd.ExcelWriter(xbuf2, engine="xlsxwriter") as xl:
            analitica.ranking_gestores(gf).to_excel(xl, sheet_name="Ranking_gestores", index=False)
            analitica.mejora_por_gestor(gf).to_excel(xl, sheet_name="Mejora_gestores", index=False)
            analitica.evolucion_mensual(gf).to_excel(xl, sheet_name="Evolucion_mensual", index=False)
            analitica.caracteristicas_por(gf, "tramo_mora").to_excel(xl, sheet_name="Por_tramo", index=False)
            analitica.caracteristicas_por(gf, "segmento").to_excel(xl, sheet_name="Por_segmento", index=False)
        st.download_button("Descargar analítica (Excel)", xbuf2.getvalue(),
                           "kobra_analitica_gestion.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@st.cache_data(show_spinner="Calculando la agenda de seguimiento…")
def _agenda_hoy_cacheada(g):
    return kseg.agenda_hoy(g)


# ---- Tab Agenda: promesas vencidas + seguimiento ---------------------------
with tabAgenda:
    st.subheader("Agenda de seguimiento")
    st.caption("Detecta **promesas de pago y arreglos vencidos** sin que se haya registrado "
               "el pago correspondiente, y arma la lista de a quién recontactar hoy — "
               "respetando horario, feriados, topes de frecuencia y la lista de No Contactar "
               "(los mismos límites que ya aplica el Gestor IA en cada llamada/WhatsApp).")

    _agenda = _agenda_hoy_cacheada(gest)
    if _agenda.empty:
        st.success("✓ No hay promesas ni arreglos de pago vencidos sin seguimiento.")
    else:
        c = st.columns(4)
        c[0].metric("Promesas/arreglos vencidos", f"{len(_agenda):,}")
        c[1].metric("Contactables hoy", f"{int(_agenda['contactable'].sum()):,}")
        c[2].metric("Monto comprometido", f"$U {_agenda['monto_acordado'].sum():,.0f}")
        c[3].metric("Días de atraso (prom.)", f"{_agenda['dias_vencida'].mean():.0f}")

        solo_contactables = st.checkbox("Mostrar solo los contactables ahora mismo", value=False)
        vista = _agenda[_agenda["contactable"]] if solo_contactables else _agenda

        tabla = vista[["id_deudor", "dias_vencida", "monto_acordado", "cuotas", "canal",
                      "gestor", "resultado", "contactable", "motivo_bloqueo"]].copy()
        st.dataframe(tabla, use_container_width=True, height=420, hide_index=True,
                    column_config={
                        "id_deudor": "Deudor", "dias_vencida": "Días vencida",
                        "monto_acordado": st.column_config.NumberColumn("Monto acordado", format="$U %.0f"),
                        "contactable": "¿Contactable hoy?", "motivo_bloqueo": "Motivo si no",
                    })
        st.download_button("⬇ Descargar agenda (CSV)", vista.to_csv(index=False).encode("utf-8"),
                           file_name="agenda_seguimiento.csv", mime="text/csv")

        st.caption("El re-contacto se hace igual que cualquier otra gestión (Agente Negociador, "
                   "«Probar mi cartera» o una llamada real vía `/voz/llamar`) y vuelve a quedar "
                   "registrado acá una vez resuelto.")

# ---- Tab Integración ERP ---------------------------------------------------
with tabERP:
    st.subheader("Integración con tu ERP / base de datos")
    st.caption("Cada gestión —del **Gestor IA** o de un **humano**— queda tipificada "
               "(pago, arreglo de pago, informado, no contactado, fallecido…) con sus "
               "fechas, montos y notas. Esa **sábana de datos** se exporta o **sincroniza "
               "a cualquier ERP o base de datos** vía API o conexión SQL.")

    _sab = kerp.sabana(gest)
    c = st.columns(4)
    c[0].metric("Gestiones", f"{len(_sab):,}")
    c[1].metric("Por Gestor IA", f"{(_sab['tipo_gestor']=='IA').sum():,}")
    c[2].metric("Por humanos", f"{(_sab['tipo_gestor']=='Humano').sum():,}")
    c[3].metric("Tipificaciones", f"{_sab['resultado'].nunique()}")

    st.markdown("**Sábana de datos** (vista previa · columnas listas para el ERP)")
    st.dataframe(_sab.head(200), use_container_width=True, height=280)

    st.markdown("#### ⬇ Descargar la sábana")
    d = st.columns(3)
    d[0].download_button("CSV", kerp.a_csv(_sab), file_name="kobra_sabana_gestiones.csv",
                         mime="text/csv", use_container_width=True)
    d[1].download_button("Excel", kerp.a_excel(_sab),
                         file_name="kobra_sabana_gestiones.xlsx", use_container_width=True,
                         mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    d[2].download_button("JSON", kerp.a_json(_sab).encode("utf-8"),
                         file_name="kobra_sabana_gestiones.json", mime="application/json",
                         use_container_width=True)

    st.markdown("---")
    st.markdown("#### Enviar / sincronizar automáticamente")
    _cfg = kconfig.cargar()
    m1, m2 = st.columns(2)
    with m1:
        st.markdown("**API REST (webhook del ERP)**")
        api_url = st.text_input("URL del endpoint", value=_cfg.get("ERP_API_URL", ""),
                                placeholder="https://tu-erp.com/api/gestiones")
        api_key = st.text_input("API key (Bearer, opcional)", value="", type="password",
                                placeholder="dejá vacío para conservar la guardada")
        if st.button("Enviar sábana al ERP (API)", use_container_width=True):
            key = api_key.strip() or _cfg.get("ERP_API_KEY", "")
            if api_url.strip():
                kconfig.guardar({"ERP_API_URL": api_url.strip(),
                                 **({"ERP_API_KEY": api_key.strip()} if api_key.strip() else {})})
            with st.spinner("Enviando al ERP…"):
                res = kerp.enviar_api(_sab, api_url.strip(), key or None)
            (st.success if res["ok"] else st.error)(
                f"{'✓' if res['ok'] else '✗'} {res.get('detalle','')} "
                f"({res.get('enviados',0)} gestiones)")
    with m2:
        st.markdown("**Base de datos (SQLAlchemy)**")
        db_url = st.text_input("URL de conexión", value=_cfg.get("ERP_DB_URL", ""),
                               placeholder="postgresql://user:pass@host:5432/db")
        tabla = st.text_input("Tabla destino", value="kobra_gestiones")
        modo = st.radio("Modo", ["append (agregar)", "replace (reemplazar)"], horizontal=True)
        if st.button("Sincronizar a base de datos", use_container_width=True):
            if db_url.strip():
                kconfig.guardar({"ERP_DB_URL": db_url.strip()})
            with st.spinner("Escribiendo en la base de datos…"):
                res = kerp.sincronizar_db(_sab, db_url.strip(), tabla.strip() or "kobra_gestiones",
                                          "replace" if modo.startswith("replace") else "append")
            (st.success if res["ok"] else st.error)(
                f"{'✓' if res['ok'] else '✗'} {res.get('detalle','')}")

    st.info("Las conexiones (URL / key / DB) también se guardan en la pestaña **Configuración** "
            "y se cargan solas. Motores soportados: PostgreSQL, MySQL/MariaDB, SQL Server, "
            "Oracle, SQLite y cualquiera compatible con SQLAlchemy (instalá su driver).")

# ---- Tab NL2SQL: preguntá a tu base de datos en lenguaje natural -----------
with tabNL2SQL:
    st.subheader("Preguntá a tu base de datos")
    st.caption("Se conecta a la base del cliente (la misma URL de la pestaña Integración ERP, "
               "o una distinta), extrae el esquema completo **una sola vez** —tablas, columnas, "
               "PKs, FKs y relaciones inferidas— y responde preguntas en español devolviendo el "
               "SQL usado, validado contra ese esquema, más la tabla y un gráfico automático. "
               "**Solo lectura**: nunca ejecuta INSERT/UPDATE/DELETE/DROP, y a la IA solo le "
               "llega el esquema (nombres de tabla/columna), nunca los datos reales de las filas.")

    _cfg_nl = kconfig.cargar()
    nl_url = st.text_input("URL de conexión", value=_cfg_nl.get("CONSULTA_DB_URL",
                                                                _cfg_nl.get("ERP_DB_URL", "")),
                           placeholder="postgresql://user:pass@host:5432/db", key="nl_db_url")
    c_nl1, c_nl2 = st.columns([1, 3])
    conectar_click = c_nl1.button("Conectar / actualizar esquema", use_container_width=True)

    if conectar_click:
        if nl_url.strip():
            kconfig.guardar({"CONSULTA_DB_URL": nl_url.strip()})
            st.cache_resource.clear()
        else:
            st.error("Falta la URL de conexión.")

    @st.cache_resource(show_spinner="Conectando y extrayendo el esquema…")
    def _cargar_motor_consulta(url):
        return kconsulta.MotorConsultaBD(url)

    motor_nl = None
    if nl_url.strip():
        try:
            motor_nl = _cargar_motor_consulta(nl_url.strip())
        except Exception as e:
            st.error(f"✗ No se pudo conectar o leer el esquema: {e}")

    if motor_nl:
        n_tablas = len(motor_nl.catalogo["tablas"])
        n_vistas = len(motor_nl.catalogo.get("vistas", {}))
        n_fks = len(motor_nl.catalogo["fks"])
        c = st.columns(3)
        c[0].metric("Tablas", n_tablas)
        c[1].metric("Vistas", n_vistas)
        c[2].metric("Relaciones (FK)", n_fks)
        with st.expander("Ver esquema detectado"):
            for t, info in motor_nl.catalogo["tablas"].items():
                n = info.get("n_filas")
                st.markdown(f"**{t}** ({n:,} filas)" if n is not None else f"**{t}**")
                st.caption(", ".join(c["columna"] for c in info["columnas"]))

        k_tablas = st.slider("Tablas a recuperar (RAG)", 2, 8, 4,
                             help="Cuántas tablas del esquema se le pasan a Claude como contexto")
        pregunta_nl = st.text_input(
            "Tu pregunta:", placeholder="Ej: ¿cuánto cobramos en marzo 2026 por departamento?",
            key="nl_pregunta")
        if st.button("▶ Consultar", type="primary", key="nl_consultar") and pregunta_nl.strip():
            api_key_claude = kconfig.cargar().get("ANTHROPIC_API_KEY", "")
            if not api_key_claude:
                st.error("Falta configurar ANTHROPIC_API_KEY en la pestaña Configuración.")
            else:
                with st.spinner("Recuperando tablas relevantes y generando SQL…"):
                    r = motor_nl.responder(pregunta_nl.strip(), api_key=api_key_claude, k=k_tablas)

                st.markdown("##### Tablas recuperadas (RAG)")
                st.write(" · ".join(f"`{t}`" for t in r["tablas_recuperadas"]) or "—")

                if r["sql"]:
                    st.markdown("##### SQL generado")
                    st.code(r["sql"], language="sql")

                if r["valido"]:
                    st.success("✓ SQL validado contra el esquema (sin nombres inventados)")
                elif r["sql"]:
                    st.error("✗ La validación encontró problemas:")
                    for p in r["problemas"]:
                        st.write(f"  - {p}")
                if r["problemas"] and r["valido"]:
                    with st.expander("⚠ Advertencias menores"):
                        for p in r["problemas"]:
                            st.write(f"  - {p}")

                if r["error"]:
                    st.error(f"Error: {r['error']}")

                df_nl = motor_nl.resultado_a_dataframe(r)
                if df_nl is not None:
                    st.markdown("##### Resultado")
                    m = st.columns(3)
                    m[0].metric("Filas", f"{len(df_nl):,}")
                    m[1].metric("Columnas", len(df_nl.columns))
                    cols_num = df_nl.select_dtypes(include="number").columns.tolist()
                    if cols_num:
                        m[2].metric(f"Σ {cols_num[0]}", f"{df_nl[cols_num[0]].sum():,.0f}")

                    t_tabla, t_graf = st.tabs(["Tabla", "Gráfico"])
                    with t_tabla:
                        st.dataframe(df_nl, use_container_width=True, height=380)
                        st.download_button("⬇ Descargar CSV", df_nl.to_csv(index=False).encode("utf-8"),
                                           file_name="consulta_resultado.csv", mime="text/csv")
                    with t_graf:
                        cols_cat = [c for c in df_nl.columns if c not in cols_num]
                        fig_nl = None
                        try:
                            if not df_nl.empty and len(df_nl) <= 200:
                                if cols_cat and cols_num:
                                    d = df_nl.sort_values(cols_num[0], ascending=False).head(30)
                                    fig_nl = px.bar(d, x=cols_cat[0], y=cols_num[0],
                                                    title=f"{cols_num[0]} por {cols_cat[0]}")
                                elif len(cols_num) >= 2:
                                    fig_nl = px.scatter(df_nl, x=cols_num[0], y=cols_num[1])
                        except Exception:
                            fig_nl = None
                        if fig_nl:
                            st.plotly_chart(fig_nl, use_container_width=True)
                        else:
                            st.info("No se pudo armar un gráfico automático para esta forma de datos.")
    else:
        st.info("Pegá la URL de conexión de la base del cliente y hacé click en "
                "«Conectar / actualizar esquema» para empezar.")

# ---- Demo en vivo: el circuito completo delante del cliente ---------------
# Un caso de gestión que se recorre entero en una reunión: el agente llama,
# escribe, manda el link, entra la plata, baja el saldo y queda la promesa.
# El paso que convence es el del medio — el cliente ve el saldo bajar solo.
with tabDemoVivo:
    from kobra import demo_vivo as kdemo

    st.subheader("Demostración en vivo")
    st.caption("El circuito completo con un caso real, para mostrarle a un cliente que esto "
               "no es un video: el agente llama de verdad, escribe de verdad y el pago entra "
               "de verdad. Los datos de contacto se cargan una sola vez y **nunca** viajan al "
               "repositorio.")

    _d = kdemo.caso()
    if _d["sintetico"]:
        st.warning("⚠ Datos **sintéticos**: el circuito se recorre igual (link, cobro, saldo, "
                   "promesa), pero no va a sonar ningún teléfono. Cargá abajo el contacto real "
                   "para que suene.")

    # Los datos se cargan acá y no por consola: esto se usa delante de un
    # cliente, y salir a una terminal a correr `--configurar` en medio de una
    # presentación es exactamente lo que hay que evitar. El comando sigue
    # existiendo para quien prepare la máquina de antemano.
    with st.expander("A quién llama la demostración", expanded=_d["sintetico"]):
        st.caption("Se guarda en el almacén cifrado de esta máquina "
                   f"(backend: {kconfig.backend_activo()}), nunca en el repositorio. "
                   "Dejá un campo vacío para conservar lo que ya estaba.")
        _dv_vals, _dv_cols = {}, st.columns(3)
        for _i, (_clave, _desc) in enumerate(kdemo.CLAVES.items()):
            _actual = kconfig.leer_extra(_clave) or ""
            _dv_vals[_clave] = _dv_cols[_i % 3].text_input(
                _desc.split("(")[0].strip(), value=_actual, key=f"dv_{_clave}")
        if st.button("Guardar contacto", key="dv_guardar", use_container_width=True):
            _guardados = 0
            for _clave, _valor in _dv_vals.items():
                if _valor and _valor.strip():
                    kconfig.guardar_extra(_clave, _valor.strip())
                    _guardados += 1
            st.success(f"Guardado ({_guardados} campo/s)." if _guardados
                       else "No había nada nuevo para guardar.")
            st.rerun()

    _c1, _c2, _c3, _c4 = st.columns(4)
    _c1.metric("Deudor", _d["nombre"])
    _c2.metric("Deuda", f"$U {_d['monto_deuda']:.0f}")
    _c3.metric("Mora", f"{_d['dias_mora']} días")
    _c4.metric("ProbPago", f"{_d['probpago']:.0%}")
    st.caption(f"Alta {_d['fecha_alta']} · {_d['telefono']} · {_d['email']}")

    _tenant = krutas.DIR_DATOS
    _saldo = kdemo.saldo(_tenant)

    st.markdown("---")
    _p1, _p2 = st.columns(2)
    with _p1:
        st.markdown("**1 · El agente contacta**")
        _base = os.environ.get("PUBLIC_BASE_URL", "")
        if not _base:
            st.info("Falta `PUBLIC_BASE_URL` para la llamada (ver Configuración).")
        if st.button("Llamar ahora", disabled=not _base, use_container_width=True):
            _r = kdemo.llamar(base_url=_base)
            (st.success if _r["ok"] else st.error)(
                "Llamando…" if _r["ok"] else f"No se pudo llamar: {_r['detalle']}")
        if st.button("Escribir por WhatsApp", use_container_width=True):
            _r = kdemo.escribir_whatsapp()
            (st.success if _r["ok"] else st.error)(
                "WhatsApp enviado." if _r["ok"] else f"No se pudo enviar: {_r.get('detalle')}")

    with _p2:
        st.markdown("**2 · El link de pago**")
        _metodo = st.radio("Método", ["mercadopago", "transferencia"], horizontal=True,
                          format_func=lambda m: "MercadoPago" if m == "mercadopago" else "Transferencia",
                          key="demo_metodo")
        _monto = st.number_input("Monto a cobrar (UYU)", min_value=1.0, max_value=float(_saldo or 1),
                                value=float(min(kdemo.PAGO_DEMO, _saldo or kdemo.PAGO_DEMO)),
                                step=10.0, key="demo_monto", disabled=_saldo <= 0)
        if st.button("Generar link", disabled=_saldo <= 0, use_container_width=True):
            _pago = kdemo.link_de_pago(_tenant, monto=_monto, metodo=_metodo,
                                       base_url=os.environ.get("PUBLIC_BASE_URL", ""))
            st.session_state["demo_pago"] = _pago
            kauditoria.registrar("demo_vivo_link", {"referencia": _pago["referencia"],
                                                   "monto": _pago["monto"]}, rol=ROL_ACTIVO)

    _pago = st.session_state.get("demo_pago")
    if _pago:
        st.info(f"**{_pago['referencia']}** · $U {_pago['monto']:.0f} ({_pago['tipo']}) "
                f"→ {_pago['destino']}")
        if _pago["estado"] == "pendiente" and st.button("✓ Confirmar que entró el pago"):
            _conf = kdemo.acreditar(_tenant, _pago["referencia"],
                                    payment_id=st.session_state.get("demo_pid", "").strip())
            st.session_state["demo_pago"] = _conf
            kauditoria.registrar("demo_vivo_cobro", {"referencia": _conf["referencia"],
                                                    "estado": _conf["estado"]}, rol=ROL_ACTIVO)
            st.rerun()

    st.markdown("---")
    st.markdown(f"**3 · Queda un saldo de $U {_saldo:.0f} — se negocia la diferencia**")
    if _saldo > 0:
        _ops = kdemo.propuestas(_saldo)
        st.dataframe(pd.DataFrame(_ops), use_container_width=True, hide_index=True,
                    column_config={"opcion": "Opción",
                                   "monto": st.column_config.NumberColumn("Monto", format="$U %.0f"),
                                   "cuotas": "Cuotas",
                                   "descuento": st.column_config.NumberColumn("Desc.", format="%d%%"),
                                   "detalle": "Detalle"})
        _elegida = st.selectbox("Acuerdo cerrado", [o["opcion"] for o in _ops], key="demo_acuerdo")
        _op = next(o for o in _ops if o["opcion"] == _elegida)
        _fecha = st.date_input("Fecha de compromiso", key="demo_fecha")
        if st.button("Registrar la promesa", type="primary"):
            kdemo.registrar_acuerdo(monto_acordado=_op["monto"], cuotas=_op["cuotas"],
                                   descuento=_op["descuento"],
                                   fecha_compromiso=str(_fecha))
            kauditoria.registrar("demo_vivo_promesa", {"monto": _op["monto"],
                                                      "cuotas": _op["cuotas"]}, rol=ROL_ACTIVO)
            st.success(f"Promesa registrada: $U {_op['monto']:.0f} en {_op['cuotas']} cuota(s) "
                      f"para el {_fecha}. Ya entró al seguimiento — si la fecha pasa sin el pago, "
                      "aparece en **Agenda de seguimiento** como cualquier otro caso.")
    else:
        st.success("✓ Deuda cancelada. Para volver a mostrar el circuito, generá un caso nuevo.")


# ---- Tab 7: Configuración (API keys persistentes) — solo admin ------------
with tab7:
    if ROL_ACTIVO != "admin":
        st.warning("Esta sección es solo para el rol **Administrador**. "
                   "Pedile a un admin que gestione las API keys y las contraseñas.")
    else:
        st.subheader("⚙ Configuración de API keys")
        st.caption("Ingresá las keys una sola vez: quedan **guardadas** y se cargan solas en "
                   "cada arranque. Habilitan la transcripción real (Whisper) y la evaluación "
                   "con Claude. El resto de MV Kobra AI funciona sin keys.")

        with st.form("form_config"):
            nuevos = {}
            for clave, desc in kconfig.CLAVES.items():
                nuevos[clave] = st.text_input(
                    clave, value="", type="password",
                    placeholder=("sk-… " if clave == "OPENAI_API_KEY" else "sk-ant-…"),
                    help=desc + " · dejá vacío para conservar la guardada")
            b1, b2, _ = st.columns([0.25, 0.25, 0.5])
            guardar_btn = b1.form_submit_button("Guardar", type="primary")
            limpiar_btn = b2.form_submit_button("Borrar guardadas")

        # Se procesan antes de mostrar el estado, sin recargar (se queda en la pestaña)
        if guardar_btn:
            if any(v.strip() for v in nuevos.values()):
                claves_tocadas = sorted(k for k, v in nuevos.items() if v.strip())
                kconfig.guardar(nuevos)
                kauditoria.registrar("config_guardada", {"claves": claves_tocadas}, rol=ROL_ACTIVO)
                st.success("✓ Configuración guardada. Ya se usa en esta sesión y en próximos arranques.")
            else:
                st.info("Ingresá al menos una key para guardar.")
        if limpiar_btn:
            kconfig.limpiar()
            kauditoria.registrar("config_borrada", {}, rol=ROL_ACTIVO)
            st.warning("Configuración borrada.")

        # Estado actual (refleja lo recién guardado/borrado)
        est = kconfig.estado()
        guardadas = kconfig.cargar()
        cc = st.columns(2)
        for i, (clave, desc) in enumerate(kconfig.CLAVES.items()):
            with cc[i % len(cc)]:
                activo = est.get(clave)
                st.markdown(f"**{desc}**")
                st.markdown(("Configurada" if activo else "No configurada") +
                            (f" · `{kconfig.enmascarar(guardadas.get(clave,''))}`"
                             if guardadas.get(clave) else ""))

        st.markdown("---")
        _backend = kconfig.backend_activo()
        _backend_txt = {
            "keyring": "**Keyring del sistema operativo** (Credential Manager / Keychain / Secret Service) — el backend más seguro, se usa automáticamente cuando está disponible.",
            "cifrado": f"**Archivo cifrado** (`{kconfig.CONFIG_FILE_CIFRADO}`, Fernet/AES) — no hay keyring del SO disponible en este entorno; se cifra igual, con la clave en un archivo separado (permisos 600).",
            "plano": f"⚠ **Texto plano** (`{kconfig.CONFIG_FILE_PLANO}`, permisos 600) — instalá `keyring` o `cryptography` para que esto quede cifrado.",
        }[_backend]
        st.markdown(_backend_txt + " Fuera del repo en todos los casos. En producción podés "
                    "inyectarlas por variables de entorno / secretos de Docker; el entorno "
                    "tiene prioridad sobre lo guardado.")

        st.markdown("---")
        st.subheader("Proveedor y modelo de IA")
        st.caption("Con qué cuenta corporativa **propia** razona MV Kobra AI (Asistente, "
                   "Copiloto, Gestor IA y consultas a la base): Claude, ChatGPT/OpenAI, "
                   "Gemini o Grok. Eligiendo el **modelo** regulás el consumo de tokens — "
                   "un modelo chico y barato para el volumen diario, uno grande para lo que "
                   "lo amerite. Si tu empresa tiene \"Copilot corporativo\", casi seguro es "
                   "Azure OpenAI / ChatGPT Enterprise: entrá por la opción OpenAI con esa key.")

        _prov_activo = kllm.proveedor_activo()
        _labels_prov = {p: kllm.NOMBRES[p] for p in kllm.PROVEEDORES}
        _prov_sel = st.selectbox(
            "Proveedor de IA", list(kllm.PROVEEDORES),
            index=list(kllm.PROVEEDORES).index(_prov_activo),
            format_func=lambda p: _labels_prov[p] +
                ("" if kllm.disponible(proveedor=p) else " · ⚠ falta la key"),
            key="llm_proveedor_sel")

        _col_mod, _col_act = st.columns([0.72, 0.28])
        with _col_mod:
            _modelos = kllm.modelos_disponibles(_prov_sel)
            _mod_actual = kllm.modelo_de(_prov_sel)
            _mod_sel = st.selectbox(
                "Modelo (dentro de tu cuenta)", _modelos,
                index=_modelos.index(_mod_actual) if _mod_actual in _modelos else 0,
                key=f"llm_modelo_sel_{_prov_sel}")
        with _col_act:
            st.markdown("<div style='height:1.72em'></div>", unsafe_allow_html=True)
            if st.button("Actualizar modelos", use_container_width=True,
                         help="Consulta la API del proveedor por su catálogo vigente, para "
                              "que la lista tenga las últimas versiones publicadas."):
                _res_mod = kllm.actualizar_modelos(_prov_sel)
                if _res_mod["ok"]:
                    kauditoria.registrar("llm_modelos_actualizados",
                                        {"proveedor": _prov_sel,
                                         "cantidad": len(_res_mod["modelos"])}, rol=ROL_ACTIVO)
                    st.success("✓ " + _res_mod["detalle"])
                    st.rerun()
                else:
                    st.error(_res_mod["detalle"])
        _fecha_mod = kllm.fecha_actualizacion_modelos(_prov_sel)
        st.caption(("Catálogo actualizado por última vez: " + _fecha_mod.replace("T", " "))
                   if _fecha_mod else
                   "Catálogo nunca actualizado — se muestra el modelo de referencia; tocá "
                   "**Actualizar modelos** (con la key cargada) para traer los vigentes.")

        if st.button("Usar este proveedor y modelo", type="primary"):
            kllm.establecer_proveedor(_prov_sel)
            kllm.establecer_modelo(_prov_sel, _mod_sel)
            kauditoria.registrar("llm_proveedor_elegido",
                                {"proveedor": _prov_sel, "modelo": _mod_sel}, rol=ROL_ACTIVO)
            st.success(f"✓ Guardado: {_labels_prov[_prov_sel]} · `{_mod_sel}`. "
                      "Ya se usa en toda la plataforma.")
            if not kllm.disponible(proveedor=_prov_sel):
                st.warning(f"⚠ Falta cargar `{kllm.KEY_ENV[_prov_sel]}` arriba para que "
                          "este proveedor funcione — mientras tanto la IA degrada a plantillas.")

        st.markdown("---")
        st.subheader("Auto-configurar número Twilio")
        st.caption("Automatiza los pasos manuales de `docs/GUIA_LLAMADA_REAL_TWILIO.md` "
                   "(buscar número → Buy a number → apuntar el webhook de voz en la Console): "
                   "con `TWILIO_ACCOUNT_SID`/`TWILIO_AUTH_TOKEN` ya cargados arriba, buscá, "
                   "comprá y configurá el webhook de voz entrante en un solo paso, sin salir "
                   "de este dashboard. **Comprar un número tiene costo real** (verificá la "
                   "tarifa vigente de Twilio antes de confirmar).")
        _twilio_sid = kconfig.cargar().get("TWILIO_ACCOUNT_SID", "")
        _twilio_token = kconfig.cargar().get("TWILIO_AUTH_TOKEN", "")
        _public_base = os.environ.get("PUBLIC_BASE_URL", "")
        if not (_twilio_sid and _twilio_token):
            st.info("Cargá `TWILIO_ACCOUNT_SID` y `TWILIO_AUTH_TOKEN` arriba y guardá para "
                   "poder buscar/comprar números.")
        elif not _public_base:
            st.warning("⚠ Falta la variable de entorno `PUBLIC_BASE_URL` en el proceso donde "
                      "corre **este dashboard** (no alcanza con que la tenga `realtime/server.py`: "
                      "auto-configurar el webhook necesita saber la URL desde acá) — sin eso no "
                      "hay a qué URL apuntar el webhook de voz entrante.")
        else:
            _voice_url = _public_base.rstrip("/") + "/voz/entrante"
            _tab_comprar, _tab_ya_tengo = st.tabs(["Comprar número nuevo", "Ya tengo un número"])
            with _tab_comprar:
                _pais = st.text_input("País (código ISO, ej. UY, AR, US)", value="UY",
                                     key="twilio_pais_buscar")
                if st.button("Buscar números disponibles"):
                    _res_busqueda = ktwilio.buscar_numeros_disponibles(
                        _pais.strip().upper(), sid=_twilio_sid, token=_twilio_token)
                    st.session_state["twilio_numeros_disponibles"] = _res_busqueda
                _res_busqueda = st.session_state.get("twilio_numeros_disponibles")
                if _res_busqueda:
                    if not _res_busqueda["ok"]:
                        st.error(f"No se pudo buscar: {_res_busqueda['detalle']}")
                    elif not _res_busqueda["numeros"]:
                        st.info("No hay números disponibles para ese país en este momento.")
                    else:
                        _opciones_num = {
                            f"{n['numero']} · {n.get('localidad') or n.get('region') or ''}": n["numero"]
                            for n in _res_busqueda["numeros"]}
                        _elegido_label = st.selectbox("Número a comprar", list(_opciones_num.keys()))
                        _elegido_num = _opciones_num[_elegido_label]
                        st.caption(f"Webhook de voz que se va a configurar: `{_voice_url}`")
                        if st.button(f"Comprar {_elegido_num} y configurar webhook"):
                            _r_compra = ktwilio.comprar_numero(_elegido_num, _voice_url,
                                                              sid=_twilio_sid, token=_twilio_token)
                            if _r_compra["ok"]:
                                kconfig.guardar({"TWILIO_FROM": _r_compra["numero"]})
                                kauditoria.registrar("twilio_numero_comprado",
                                                    {"numero": _r_compra["numero"]}, rol=ROL_ACTIVO)
                                st.success(f"✓ Comprado y configurado: {_r_compra['numero']}. "
                                          "Guardado como `TWILIO_FROM`.")
                            else:
                                st.error(f"No se pudo comprar: {_r_compra['detalle']}")
            with _tab_ya_tengo:
                _num_existente = st.text_input("Número ya comprado (formato +598…)",
                                              value=kconfig.cargar().get("TWILIO_FROM", ""))
                st.caption(f"Webhook de voz que se va a configurar: `{_voice_url}`")
                if st.button("Configurar webhook para este número"):
                    _r_webhook = ktwilio.configurar_webhook_numero(
                        _num_existente.strip(), _voice_url, sid=_twilio_sid, token=_twilio_token)
                    if _r_webhook["ok"]:
                        kauditoria.registrar("twilio_webhook_configurado",
                                            {"numero": _num_existente.strip()}, rol=ROL_ACTIVO)
                        st.success("✓ Webhook de voz configurado.")
                    else:
                        st.error(f"No se pudo configurar: {_r_webhook['detalle']}")

        st.markdown("---")
        st.subheader("Voz de las llamadas (Twilio/Polly)")
        st.caption("Voz con la que habla el Gestor IA por teléfono cuando NO hay voz premium "
                   "configurada. Ninguna voz de Polly es rioplatense de verdad — estas son las "
                   "más naturales y latinas del catálogo incluido; para acento rioplatense real, "
                   "configurá la voz premium de abajo. Las voces *neural* tienen un costo chico "
                   "por carácter en Twilio (ver el pricing de `<Say>` de tu cuenta).")
        _VOCES_TWILIO = {
            "Lupe · neural, latina neutra (es-US) — recomendada": ("Polly.Lupe-Neural", "es-US"),
            "Pedro · neural, masculino latino (es-US)": ("Polly.Pedro-Neural", "es-US"),
            "Mia · neural, mexicana (es-MX)": ("Polly.Mia-Neural", "es-MX"),
            "Andrés · neural, mexicano (es-MX)": ("Polly.Andres-Neural", "es-MX"),
            "Voz estándar de Twilio (robótica, sin costo extra)": ("", "es-MX"),
        }
        _voz_actual = kconfig.leer_extra("TWILIO_TTS_VOICE", "Polly.Lupe-Neural")
        _idx_voz = next((i for i, (v, _l) in enumerate(_VOCES_TWILIO.values())
                        if v == _voz_actual), 0)
        _voz_elegida = st.selectbox("Voz del Gestor IA en llamadas",
                                    list(_VOCES_TWILIO.keys()), index=_idx_voz)
        if st.button("Guardar voz de Twilio"):
            _v, _l = _VOCES_TWILIO[_voz_elegida]
            kconfig.guardar_extra("TWILIO_TTS_VOICE", _v)
            kconfig.guardar_extra("TWILIO_TTS_LANG", _l)
            kauditoria.registrar("voz_twilio_configurada", {"voz": _v or "default"}, rol=ROL_ACTIVO)
            st.success("✓ Guardado. Se aplica en el próximo arranque de `realtime/server.py`.")

        st.markdown("---")
        st.subheader("Voz premium (ElevenLabs) — acento rioplatense real")
        st.caption("Opcional. Sin configurar, las llamadas usan la voz de Twilio/Polly de arriba. "
                   "Con `ELEVENLABS_API_KEY` cargada acá arriba, podés elegir una voz "
                   "clonada/premium — **tiene costo real por carácter** (ver `kobra/voz_tts.py`), "
                   "así que queda desactivado hasta que elijas una voz. Para que suene "
                   "**rioplatense de verdad**: en elevenlabs.io → *Voice Library*, buscá "
                   "«Argentine» o «Rioplatense», agregá la voz a tu cuenta y elegila acá. "
                   "En llamadas se usa el modelo *flash* (baja latencia, mitad de costo) para "
                   "que la conversación fluya sin pausas.")
        _eleven_key = kconfig.cargar().get("ELEVENLABS_API_KEY", "")
        if not _eleven_key:
            st.info("Cargá `ELEVENLABS_API_KEY` arriba y guardá para ver las voces disponibles.")
        else:
            _voces = voz_tts.voces_disponibles(_eleven_key)
            if not _voces:
                st.warning("No se pudo listar voces (key inválida o sin conexión).")
            else:
                _voice_actual = kconfig.leer_extra("ELEVENLABS_VOICE_ID", "")
                _opciones = {"— Desactivado (usar Twilio/Polly) —": ""}
                _opciones.update({f"{v['nombre']} ({v['voice_id'][:8]}…)": v["voice_id"] for v in _voces})
                _labels = list(_opciones.keys())
                _idx = next((i for i, v in enumerate(_opciones.values()) if v == _voice_actual), 0)
                _elegida = st.selectbox("Voz para las llamadas reales", _labels, index=_idx)
                if st.button("Guardar voz elegida"):
                    voice_id = _opciones[_elegida]
                    kconfig.guardar_extra("ELEVENLABS_VOICE_ID", voice_id)
                    kconfig.guardar_extra("TTS_PROVIDER", "elevenlabs" if voice_id else "twilio")
                    kauditoria.registrar("voz_premium_configurada",
                                         {"activada": bool(voice_id)}, rol=ROL_ACTIVO)
                    st.success("✓ Guardado. Se aplica en el próximo arranque de `realtime/server.py` "
                              "(o inmediatamente si ya está corriendo con auto-reload).")
                st.caption(f"Costo de referencia: ~US$ {voz_tts.COSTO_POR_1000_CHARS_USD:.2f} "
                          "cada 1.000 caracteres hablados (verificá contra tu plan real de "
                          "ElevenLabs antes de fijar el precio del plan que lo incluya).")

        st.markdown("---")
        st.subheader("Campaña automática de contacto")
        st.caption("Corre sola, sin que nadie abra el dashboard: llama, escribe por WhatsApp o "
                   "manda un email según el canal donde más se contactó a cada deudor "
                   "(historial real de gestiones), respetando siempre horario/feriados/topes/No "
                   "Contactar y priorizando por ProbPago. **Requiere que `realtime/server.py` "
                   "quede corriendo 24/7** (Docker/servidor real) — el scheduler vive ahí, no en "
                   "este dashboard Streamlit.")
        _campana_activa = bool(kconfig.leer_extra("CAMPANA_ACTIVA", False))
        _contactos_csv_actual = kconfig.leer_extra("CAMPANA_CONTACTOS_CSV", "")
        _max_corrida_actual = int(kconfig.leer_extra("CAMPANA_MAX_POR_CORRIDA", 50) or 50)
        with st.form("form_campana"):
            nueva_activa = st.checkbox("Campaña automática activa", value=_campana_activa)
            nuevo_csv = st.text_input(
                "Ruta al CSV de contactos reales (columnas: id_deudor,telefono,email)",
                value=_contactos_csv_actual,
                placeholder="/ruta/a/mi_cartera_contactos.csv")
            nuevo_max = st.number_input("Máximo de contactos por corrida del scheduler",
                                        min_value=1, max_value=1000, value=_max_corrida_actual)
            guardar_campana = st.form_submit_button("Guardar", type="primary")
        if guardar_campana:
            kconfig.guardar_extra("CAMPANA_ACTIVA", nueva_activa)
            kconfig.guardar_extra("CAMPANA_CONTACTOS_CSV", nuevo_csv.strip())
            kconfig.guardar_extra("CAMPANA_MAX_POR_CORRIDA", int(nuevo_max))
            kauditoria.registrar("campana_configurada", {"activa": nueva_activa}, rol=ROL_ACTIVO)
            st.success("✓ Guardado. El scheduler de `realtime/server.py` lo revisa en cada corrida "
                      f"(cada {os.environ.get('CAMPANA_INTERVALO_MIN', '60')} min).")
        if nueva_activa if guardar_campana else _campana_activa:
            faltan = []
            if not (nuevo_csv.strip() if guardar_campana else _contactos_csv_actual):
                faltan.append("la ruta al CSV de contactos")
            if not os.environ.get("PUBLIC_BASE_URL"):
                faltan.append("la variable de entorno PUBLIC_BASE_URL en el servidor de `realtime/server.py`")
            if faltan:
                st.warning("⚠ Con la campaña activa, todavía falta: " + "; ".join(faltan) + ".")

        st.markdown("**Plantillas de email por tramo de mora**")
        _tramo_elegido = st.selectbox("Tramo", ["1-30", "31-60", "61-90", "91-180", "180+"], key="tramo_plantilla")
        _plantillas = kcampana.obtener_plantillas_email()
        _plantilla_actual = _plantillas.get(_tramo_elegido, kcampana.PLANTILLA_EMAIL_DEFAULT["1-30"])
        with st.form("form_plantilla_email"):
            nuevo_asunto = st.text_input("Asunto (podés usar {empresa}, {monto}, {dias_mora})",
                                        value=_plantilla_actual["asunto"])
            nuevo_cuerpo = st.text_area("Cuerpo", value=_plantilla_actual["cuerpo"], height=160)
            guardar_plantilla = st.form_submit_button("Guardar plantilla de este tramo")
        if guardar_plantilla:
            kcampana.guardar_plantilla_email(_tramo_elegido, nuevo_asunto, nuevo_cuerpo)
            kauditoria.registrar("plantilla_email_guardada", {"tramo": _tramo_elegido}, rol=ROL_ACTIVO)
            st.success(f"✓ Plantilla de {_tramo_elegido} guardada.")
        with st.expander("Vista previa"):
            _asunto_prev, _cuerpo_prev = kcampana.renderizar_plantilla(
                {"asunto": nuevo_asunto if guardar_plantilla else _plantilla_actual["asunto"],
                 "cuerpo": nuevo_cuerpo if guardar_plantilla else _plantilla_actual["cuerpo"]},
                {"empresa": "Tu Empresa", "monto": 45000.0, "dias_mora": 62})
            st.markdown(f"**Asunto:** {_asunto_prev}")
            st.text(_cuerpo_prev)

        st.markdown("---")
        st.subheader("Acceso y roles")
        st.caption("**Administrador**: ve y edita todo, incluida esta pestaña. "
                   "**Gestor**: opera el resto del dashboard, sin acceso a Configuración. "
                   "Las contraseñas se guardan como hash (PBKDF2-SHA256), nunca en texto plano.")
        colA, colG = st.columns(2)
        with colA:
            st.markdown("**Contraseña de administrador**")
            with st.form("form_pass_admin"):
                np1 = st.text_input("Nueva contraseña", type="password", key="np_admin")
                np2 = st.text_input("Repetila", type="password", key="np_admin2")
                if st.form_submit_button("Actualizar admin"):
                    if len(np1) < 6:
                        st.error("Mínimo 6 caracteres.")
                    elif np1 != np2:
                        st.error("No coinciden.")
                    else:
                        kauth.establecer_password("admin", np1)
                        kauditoria.registrar("password_admin_cambiada", {}, rol=ROL_ACTIVO)
                        st.success("✓ Contraseña de administrador actualizada.")
        with colG:
            st.markdown("**Contraseña de gestor** " +
                       ("configurada" if kauth.tiene_password("gestor") else "sin configurar"))
            with st.form("form_pass_gestor"):
                ng1 = st.text_input("Nueva contraseña", type="password", key="ng_gestor")
                ng2 = st.text_input("Repetila", type="password", key="ng_gestor2")
                if st.form_submit_button("Crear/actualizar gestor"):
                    if len(ng1) < 6:
                        st.error("Mínimo 6 caracteres.")
                    elif ng1 != ng2:
                        st.error("No coinciden.")
                    else:
                        kauth.establecer_password("gestor", ng1)
                        kauditoria.registrar("password_gestor_cambiada", {}, rol=ROL_ACTIVO)
                        st.success("✓ Contraseña de gestor guardada. Compartísela solo con el equipo operativo.")

        st.markdown("---")
        st.subheader("SSO corporativo (OIDC)")
        st.caption("Opcional — para que el equipo entre con su cuenta de Microsoft Entra ID/Azure AD, "
                   "Okta, Google Workspace u otro proveedor OIDC, en vez de (o además de) la "
                   "contraseña local. El login local sigue funcionando igual aunque configures esto.")
        _sso_activo = ksso.configurado()
        st.markdown("SSO activo" if _sso_activo else "SSO no configurado")
        with st.form("form_sso"):
            sso_issuer = st.text_input("Issuer / Authority", value="",
                                       placeholder="https://login.microsoftonline.com/<tenant>/v2.0",
                                       help="URL base del proveedor OIDC (con discovery en /.well-known/openid-configuration)")
            sso_client_id = st.text_input("Client ID", value="", type="password")
            sso_client_secret = st.text_input("Client Secret", value="", type="password")
            sso_redirect = st.text_input("Redirect URI", value="",
                                         placeholder="http://localhost:8501 (o la URL pública del dashboard)",
                                         help="Tiene que coincidir exactamente con la registrada en el proveedor")
            sso_admins = st.text_input("Emails que entran como Administrador (separados por coma)", value="",
                                       placeholder="vos@empresa.com, otro-admin@empresa.com",
                                       help="Cualquier otro email autenticado por SSO entra como Gestor")
            b_sso1, b_sso2 = st.columns(2)
            guardar_sso = b_sso1.form_submit_button("Guardar SSO", type="primary")
            borrar_sso = b_sso2.form_submit_button("Desactivar SSO")
        if guardar_sso:
            faltantes = [n for n, v in [("Issuer", sso_issuer), ("Client ID", sso_client_id),
                                        ("Client Secret", sso_client_secret), ("Redirect URI", sso_redirect)]
                        if not v.strip()]
            if faltantes:
                st.error("Completá: " + ", ".join(faltantes))
            else:
                kconfig.guardar_extra("OIDC_ISSUER", sso_issuer.strip())
                kconfig.guardar_extra("OIDC_CLIENT_ID", sso_client_id.strip())
                kconfig.guardar_extra("OIDC_CLIENT_SECRET", sso_client_secret.strip())
                kconfig.guardar_extra("OIDC_REDIRECT_URI", sso_redirect.strip())
                kconfig.guardar_extra("OIDC_ADMINS", sso_admins.strip())
                kauditoria.registrar("sso_configurado", {"issuer": sso_issuer.strip()}, rol=ROL_ACTIVO)
                st.success("✓ SSO configurado. La próxima vez que alguien tenga que loguearse, va a ver el botón.")
        if borrar_sso:
            for k in ("OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_REDIRECT_URI", "OIDC_ADMINS"):
                kconfig.guardar_extra(k, "")
            kauditoria.registrar("sso_desactivado", {}, rol=ROL_ACTIVO)
            st.warning("SSO desactivado. El login local sigue funcionando.")

        st.markdown("---")
        st.subheader("Log de auditoría")
        _chk = kauditoria.verificar_integridad()
        if _chk["entradas"] == 0:
            st.caption("Todavía no hay entradas registradas.")
        else:
            if _chk["ok"]:
                st.success(f"✓ Cadena íntegra · {_chk['entradas']} entradas registradas "
                          f"(`{kauditoria.LOG_FILE}`).")
            else:
                st.error(f"⚠ El log de auditoría no pasa la verificación de integridad "
                         f"(entrada #{_chk['primer_error']}) — alguien pudo haberlo editado "
                         f"por fuera de la app.")
            _ult = kauditoria.leer(limite=25)[::-1]
            st.dataframe(
                pd.DataFrame([{"cuándo": e["ts"], "usuario": e["usuario"], "rol": e["rol"],
                              "acción": e["accion"], "detalle": json.dumps(e["detalle"], ensure_ascii=False)}
                             for e in _ult]),
                use_container_width=True, hide_index=True,
            )
            st.caption("Últimas 25 entradas (más reciente arriba). Cada línea encadena el hash "
                      "de la anterior — editar o borrar una rompe la verificación de arriba.")

        st.markdown("---")
        st.subheader("Backup y restauración")
        st.caption("Empaqueta cartera, gestiones, lista de no-contactar, log de auditoría, "
                   "config cifrada y la base de uso del backend de licencias en un solo ZIP. "
                   "Para automatizarlo: Programador de tareas (Windows) o cron ejecutando "
                   "`python -m kobra.backup crear`.")
        if st.button("Crear backup ahora"):
            r = kbackup.crear_backup()
            if r["ok"]:
                st.success(f"✓ Backup creado: `{r['ruta']}` ({r['archivos']} archivos, "
                          f"{r['bytes']/1024:.0f} KB).")
            else:
                st.warning(r.get("detalle", "No se pudo crear el backup."))
        _backups = kbackup.listar_backups()
        if _backups:
            st.dataframe(
                pd.DataFrame([{"archivo": b["nombre"], "tamaño (KB)": round(b["bytes"]/1024),
                              "creado": b["modificado"]} for b in _backups]),
                use_container_width=True, hide_index=True,
            )
            st.caption(f"Guardados en `{kbackup.BACKUP_DIR_DEFAULT}` (configurable con "
                      "la variable de entorno `KOBRA_BACKUP_DIR` — usá una carpeta ya "
                      "sincronizada a la nube si querés backup fuera de esta máquina).")
        else:
            st.caption("Todavía no hay backups creados en este equipo.")

# ---- Tab 8: Probar mi cartera ----------------------------------------------
with tab8:
    st.subheader("Probá MV Kobra AI con tu propia cartera")
    st.caption("Cargá tus contactos y el **Gestor IA** negocia cada caso: ProbPago + "
               "el porqué, estrategia, chequeo de cumplimiento y la conversación completa. "
               "Después descargás los resultados.")
    st.info("**Privacidad**: lo que cargues acá se procesa en tu sesión/máquina y no se "
            "sube a ningún lado. El producto vendible sigue siendo 100 % sintético. Para "
            "**llamar de verdad** a un tercero necesitás su consentimiento y telefonía "
            "(ver la guía de Twilio).")

    modo = st.radio("¿Cómo cargás los contactos?",
                    ["✍ Escribir en una tabla", "Subir archivo (CSV/Excel)",
                     "Traer de mi base de datos"],
                    horizontal=True, key="modo_cartera")

    contactos = []
    if modo.startswith("✍"):
        ejemplo = pd.DataFrame({
            "nombre": ["Contacto 1", "Contacto 2", "Contacto 3"],
            "telefono": ["099000001", "099000002", "099000003"],
            "deuda": [10000.0, 6000.0, 15000.0],
            "dias_mora": [25, 75, 160],
        })
        st.caption("Editá las filas (podés agregar/quitar). Columnas: **nombre, telefono, "
                   "deuda** y opcional **dias_mora**.")
        edit = st.data_editor(ejemplo, num_rows="dynamic", use_container_width=True,
                              key="editor_cartera",
                              column_config={
                                  "telefono": st.column_config.TextColumn("telefono"),
                                  "deuda": st.column_config.NumberColumn("deuda", min_value=0),
                                  "dias_mora": st.column_config.NumberColumn("dias_mora", min_value=0),
                              })
        from kobra import cartera_manual as _cm
        contactos = _cm.desde_dataframe(edit)
    elif modo.startswith(""):
        up = st.file_uploader("Subí un CSV o Excel con columnas: nombre, telefono, deuda "
                              "[, dias_mora]", type=["csv", "xlsx"])
        plantilla = "nombre,telefono,deuda,dias_mora\nWendy,099000001,10000,25\n"
        st.download_button("⬇ Descargar plantilla CSV", plantilla,
                           file_name="plantilla_cartera.csv", mime="text/csv")
        if up is not None:
            from kobra import cartera_manual as _cm
            raw = (pd.read_csv(up, dtype=str) if up.name.lower().endswith(".csv")
                   else pd.read_excel(up, dtype=str))
            contactos = _cm.desde_dataframe(raw.fillna(""))
            st.dataframe(raw, use_container_width=True, hide_index=True)
    else:
        st.caption("Conectá tu base (PostgreSQL, MySQL, SQL Server, SQLite… vía SQLAlchemy) "
                   "y traé la cartera con una consulta de **solo lectura**. La consulta debe "
                   "devolver al menos la columna **deuda** (o `monto_deuda`/`monto`) y, "
                   "opcionalmente, `nombre`, `telefono`, `id_deudor`, `dias_mora`, etc.")
        _db_url_guardada = kconfig.cargar().get("ERP_DB_URL", "")
        _db_url = st.text_input("URL de conexión",
                                value=_db_url_guardada, type="password",
                                placeholder="postgresql+psycopg2://usuario:clave@host/base",
                                help="Si ya cargaste ERP_DB_URL en Configuración, aparece "
                                     "precargada. No se loguea ni se guarda desde acá.")
        _db_sql = st.text_area("Consulta SQL (solo SELECT/WITH)",
                               value="SELECT nombre, telefono, deuda, dias_mora FROM cartera",
                               height=90, key="sql_cartera_db")
        if st.button("Traer cartera de la base", disabled=not (_db_url and _db_sql.strip())):
            from kobra import cartera_manual as _cm
            try:
                with st.spinner("Consultando tu base…"):
                    st.session_state["contactos_db"] = _cm.desde_base_de_datos(_db_url, _db_sql)
            except Exception as _db_e:
                st.session_state.pop("contactos_db", None)
                st.error(f"No se pudo traer la cartera: {str(_db_e)[:300]}")
        contactos = st.session_state.get("contactos_db", [])
        if contactos:
            st.success(f"✓ {len(contactos)} contacto(s) traídos de tu base — listos para negociar.")
            st.dataframe(pd.DataFrame(contactos), use_container_width=True, hide_index=True)

    usar_claude = st.checkbox(
        "Usar Claude para redactar más natural (necesita ANTHROPIC_API_KEY)", value=False,
        help="Sin key usa plantillas locales — negocia igual.")

    if st.button("Negociar con el Gestor IA", type="primary",
                 disabled=not contactos):
        from realtime.mi_cartera import procesar, resultados_a_dataframe
        model_p, base_p = cargar_modelo_prueba()
        with st.spinner(f"El Gestor IA está negociando {len(contactos)} caso(s)…"):
            resultados = procesar(contactos, model_p, base_p, usar_claude=usar_claude)

        prom = sum(1 for r in resultados if r["resultado"] == "Promesa")
        st.success(f"✓ {len(resultados)} negociación(es) · {prom} con promesa de pago.")

        for r in resultados:
            icono = "●" if r["resultado"] == "Promesa" else "●"
            with st.expander(
                    f"{icono} {r['nombre']}  ·  ☎ {r['telefono'] or '—'}  ·  "
                    f"deuda $U {r['monto_deuda']:,.0f}  ·  ProbPago {r['probpago']:.0%}  "
                    f"→  {r['resultado']}"):
                m = st.columns(3)
                m[0].metric("ProbPago", f"{r['probpago']:.0%}", r["propension"])
                m[1].metric("Estrategia", r["estrategia"])
                m[2].metric("Resultado", r["resultado"],
                            (f"$U {r['monto_acordado']:,.0f} / {r['cuotas_acordadas']} cuota(s)"
                             if r["resultado"] == "Promesa" else "—"))
                st.markdown(f"**¿Por qué esta ProbPago?** {r['motivo_probpago']}")
                estado = ("✓ permitido" if r["cumplimiento_ok"]
                          else f"✗ bloqueado ({r['cumplimiento_codigo']})")
                st.markdown(f"**Cumplimiento:** {estado} — {r['cumplimiento_motivo']}")
                st.markdown("**Conversación:**")
                chat = "\n".join(
                    f"{'Gestor IA' if q == 'gestor' else 'Cliente'}: {t}"
                    for q, t in r["transcript"])
                st.markdown(f"<div class='guion-box' style='white-space:pre-wrap'>{chat}</div>",
                            unsafe_allow_html=True)

        tabla = resultados_a_dataframe(resultados)
        d1, d2 = st.columns(2)
        d1.download_button("⬇ Descargar resultados (CSV)",
                           tabla.to_csv(index=False).encode("utf-8"),
                           file_name="kobra_resultados_prueba.csv", mime="text/csv")
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as xl:
            tabla.to_excel(xl, sheet_name="Resultados", index=False)
        d2.download_button("⬇ Descargar resultados (Excel)", buf.getvalue(),
                           file_name="kobra_resultados_prueba.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---- Tab 9: Caso de negocio (ROI) ------------------------------------------
with tab9:
    st.subheader("Caso de negocio (estimador de ROI)")
    st.caption("Dimensioná el valor de MV Kobra AI sobre TU cartera bajo distintos supuestos "
               "de mejora. Sirve para justificar un piloto pago.")
    st.warning("⚠ El *uplift* (cuánto sube el recupero) es un **supuesto que cargás vos, "
               "no un resultado medido**. Esto proyecta *cuánto valdría*, no afirma cuánto "
               "sube MV Kobra AI. El número real se mide en un piloto con grupo de control.")

    cA, cB, cC = st.columns(3)
    cartera = cA.number_input("Cartera gestionable (UYU)", min_value=0.0,
                              value=100_000_000.0, step=1_000_000.0, format="%.0f")
    tasa_base = cB.number_input("Tasa de recupero actual (%)", min_value=0.0,
                                max_value=100.0, value=30.0, step=1.0) / 100
    meses = cC.number_input("Horizonte (meses)", min_value=1, value=12, step=1)
    cD, cE, cF = st.columns(3)
    costo_mes = cD.number_input("Costo mensual de MV Kobra AI (UYU)", min_value=0.0,
                                value=100_000.0, step=10_000.0, format="%.0f")
    costo_setup = cE.number_input("Setup / implementación (UYU)", min_value=0.0,
                                  value=300_000.0, step=50_000.0, format="%.0f")
    up_base = cF.number_input("Uplift escenario base (pp)", min_value=0.0,
                              max_value=100.0, value=5.0, step=1.0)

    escenarios = {"conservador": max(up_base - 3, 0) / 100,
                  "base": up_base / 100,
                  "optimista": (up_base + 3) / 100}
    r = kroi.estimar(cartera, tasa_base, escenarios=escenarios, meses=int(meses),
                     costo_mensual_uyu=costo_mes, costo_implementacion_uyu=costo_setup)

    cols = st.columns(3)
    for i, (nombre, e) in enumerate(r["escenarios"].items()):
        with cols[i]:
            st.metric(f"{nombre.capitalize()} · +{e['uplift_pp']:.0f} pp",
                      f"$U {e['recupero_adicional_uyu']:,.0f}",
                      (f"ROI {e['roi']:.1f}x · payback {e['payback_meses']:.1f} m"
                       if e["roi"] is not None else "—"))
    tabla_roi = pd.DataFrame(r["escenarios"]).T
    st.dataframe(tabla_roi, use_container_width=True)
    st.caption(r["NOTA"])
    st.download_button("⬇ Descargar caso de negocio (CSV)",
                       tabla_roi.to_csv().encode("utf-8"),
                       file_name="kobra_caso_negocio.csv", mime="text/csv")

st.markdown("---")
# "Un producto de MV" con el logo
_MV_PATH = os.path.join(ROOT, "assets", "brand", "mv_icon_64.png")
if os.path.exists(_MV_PATH):
    import base64 as _b64mv
    with open(_MV_PATH, "rb") as _f:
        _mv64 = _b64mv.b64encode(_f.read()).decode()
    st.markdown(
        f"<div style='display:flex;align-items:center;justify-content:center;gap:12px;"
        f"margin:4px 0 10px;color:#9aa4b2;font-size:.95rem'>"
        f"<span>Un producto de</span>"
        f"<img src='data:image/png;base64,{_mv64}' style='height:34px;border-radius:8px;"
        f"vertical-align:middle'>"
        f"<b style='color:#dfe6f0;letter-spacing:.5px'>MV</b></div>",
        unsafe_allow_html=True)
st.caption("MV Kobra AI · Plataforma de Cobranzas Inteligentes · Demo con datos sintéticos (Uruguay). "
           "Sin nombres de clientes. Reemplazable por la cartera real de cualquier empresa. "
           "Un producto de MV.")
