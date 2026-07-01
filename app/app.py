"""
Kobra · Dashboard Gerencial de Cobranzas Inteligente
====================================================
App Streamlit end-to-end: ProbPago + Agente IA Negociador sobre una cartera
de cobranzas. Filtros, KPIs, gráficos, tablas y exportación a Excel/CSV.

Ejecutar:
    streamlit run app/app.py
"""
import io
import os
import sys

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRATCH = os.path.join(ROOT, ".uploads")
sys.path.insert(0, ROOT)

from kobra.probpago import ProbPagoModel      # noqa: E402
from kobra import negociador                  # noqa: E402
from kobra import copiloto                    # noqa: E402
from kobra import analitica                   # noqa: E402
from kobra import config as kconfig           # noqa: E402

kconfig.aplicar()   # carga API keys guardadas al entorno

# ----------------------------------------------------------------------------
# Config & estilo
# ----------------------------------------------------------------------------
st.set_page_config(page_title="Kobra · Cobranzas Inteligente",
                   page_icon="🐍", layout="wide", initial_sidebar_state="expanded")

PRIMARY = "#00C896"       # verde Kobra
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
</style>
""", unsafe_allow_html=True)


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
    model = ProbPagoModel().fit(df)
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

# ----------------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------------
c1, c2 = st.columns([0.7, 0.3])
with c1:
    st.markdown(f"# 🐍 Kobra <span class='kobra-badge'>Cobranzas Inteligente</span>",
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
st.sidebar.header("🎛️ Filtros")
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
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
    ["📊 Visión general", "🤖 Agente Negociador", "📋 Cartera & Export",
     "🧠 Modelo ProbPago", "🎧 Copiloto en Vivo", "📇 Gestores & Evolución",
     "⚙️ Configuración"])

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
    st.subheader("🤖 Estrategias recomendadas por el Agente IA")
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

    st.markdown("### 🎯 Simulador de negociación por deudor")
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
    st.markdown(f"<div class='guion-box'>💬 <b>Guion sugerido</b><br>{r['guion']}</div>",
                unsafe_allow_html=True)

# ---- Tab 3: Cartera & Export -----------------------------------------------
with tab3:
    st.subheader("📋 Cartera priorizada")
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

    st.markdown("#### ⬇️ Exportar para reporting")
    exp = f.sort_values("prioridad")[cols_show + ["guion"]]
    csv_bytes = exp.to_csv(index=False).encode("utf-8-sig")
    xbuf = io.BytesIO()
    with pd.ExcelWriter(xbuf, engine="xlsxwriter") as xl:
        exp.to_excel(xl, sheet_name="Cartera_priorizada", index=False)
        negociador.resumen_estrategias(f).to_excel(
            xl, sheet_name="Resumen_estrategias", index=False)
    e1, e2, e3 = st.columns([0.2, 0.2, 0.6])
    e1.download_button("📄 Descargar CSV", csv_bytes, "kobra_cartera.csv",
                       "text/csv", use_container_width=True)
    e2.download_button("📊 Descargar Excel", xbuf.getvalue(), "kobra_cartera.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True)
    e3.caption(f"{len(exp):,} registros filtrados · incluye estrategia y guion por deudor.")

# ---- Tab 4: Modelo ---------------------------------------------------------
with tab4:
    st.subheader("🧠 Cómo funciona ProbPago")
    mc = st.columns(4)
    mc[0].metric("AUC-ROC", metrics["auc_roc"])
    mc[1].metric("AUC-PR", metrics["auc_pr"])
    mc[2].metric("Lift decil 10", f"{metrics['lift_decil10']}x")
    mc[3].metric("Tasa pago base", f"{metrics['tasa_pago_base']:.1%}")
    st.caption(f"Entrenado con {metrics['n_train']:,} casos · validado con "
               f"{metrics['n_test']:,} · Gradient Boosting (esta vista). "
               "`kobra.train` compara además LogReg/RF/GBM/HistGB con CV y calibración.")
    st.warning("⚠️ **Métricas sobre datos sintéticos (demo).** La etiqueta de pago se genera "
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
    st.subheader("🎧 Copiloto de Negociación en Vivo")
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
                texto_conv, canal=canal, probpago=probpago_ref, estrategia=estrategia_ref)
            cop = res["copiloto"]
            meta = res["meta"]

            mc = st.columns(5)
            mc[0].metric("Calidad de gestión", f"{res['calidad']['score_total']:.0f}/100")
            clima_emoji = {"positivo": "🟢", "neutro": "🟡", "negativo": "🔴"}[cop["clima_etiqueta"]]
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
                st.markdown("##### 📈 Sentimiento turno a turno")
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
                st.markdown("##### 🧭 Sugerencias para el gestor")
                for titulo, detalle in cop["sugerencias"]:
                    st.markdown(
                        f"<div class='guion-box'><b>{titulo}</b><br>{detalle}</div>",
                        unsafe_allow_html=True)
                st.markdown("##### 💬 Próxima frase sugerida")
                st.markdown(f"<div class='guion-box'>{cop['proxima_frase']}</div>",
                            unsafe_allow_html=True)

            with st.expander("🔎 Detalle de criterios de calidad"):
                crit = pd.DataFrame([
                    {"Criterio": c["nombre"], "Peso %": c["peso"],
                     "Score": c["score"], "Cumple": "✅" if c["cumple"] else "⚠️"}
                    for c in res["calidad"]["criterios"].values()])
                st.dataframe(crit, use_container_width=True, hide_index=True)

            if os.getenv("ANTHROPIC_API_KEY"):
                with st.spinner("Enriqueciendo con Claude…"):
                    extra = copiloto.evaluar_con_claude(texto_conv)
                if extra:
                    st.success("Evaluación cualitativa (Claude)")
                    st.json(extra)
            else:
                st.caption("💡 Configurá `ANTHROPIC_API_KEY` (evaluación Claude) u "
                           "`OPENAI_API_KEY` (transcripción Whisper) para enriquecer el análisis. "
                           "El copiloto funciona sin claves.")

    # --- Análisis de VOZ: diarización + emoción acústica ---
    st.markdown("---")
    st.markdown("### 🎙️ Analizar grabación de la llamada (voz)")
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
            res_audio = kvoz.copiloto_desde_audio(
                audio_path, transcript_turnos=tt, probpago=probpago_ref,
                estrategia=estrategia_ref)
            va = res_audio["voz"]
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
                rp[i].metric(f"🗣️ {h}", r["emocion_dominante"],
                             f"arousal {r['arousal_prom']:.2f} · val {r['valencia_prom']:+.2f}")
            # --- Transcripción alineada por hablante + fusión voz/texto ---
            if res_audio and res_audio.get("turnos"):
                modo = res_audio["modo_transcripcion"]
                etiqueta_modo = {"whisper": "Whisper (timestamps reales)",
                                 "alineado": "alineada al texto provisto",
                                 "sin_texto": "sin texto"}.get(modo, modo)
                st.markdown(f"##### 📝 Transcripción alineada por hablante · *{etiqueta_modo}*")
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
                    st.markdown("##### 🧭 Asesoría del copiloto (sobre la transcripción real)")
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
    st.subheader("📇 Gestores & Evolución de la gestión")
    st.caption("Qué características suceden más por tramo/segmento, cómo evolucionan mes a mes, "
               "su impacto en la cobranza y si los gestores mejoran con las herramientas de Kobra.")
    st.warning("⚠️ **Datos ilustrativos (demo).** El historial de gestiones es sintético y el "
               "\"efecto Kobra\" está inyectado por el generador para demostrar la **metodología "
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
        # --- Impacto Kobra (KPIs) ---
        ik = analitica.impacto_kobra(gf)
        st.markdown("#### 🚀 Impacto de las herramientas Kobra *(ilustrativo · datos sintéticos)*")
        ck = st.columns(4)
        ck[0].metric("Calidad de gestión", f"{ik['con_kobra']['calidad_prom']:.0f}",
                     f"+{ik['uplift_calidad']:.1f} vs sin Kobra")
        ck[1].metric("Tasa de conversión", f"{ik['con_kobra']['tasa_conversion']:.0%}",
                     f"+{ik['uplift_conversion']*100:.1f} pp")
        ck[2].metric("Tasa de recupero", f"{ik['con_kobra']['tasa_recupero']:.0%}",
                     f"+{ik['uplift_recupero']*100:.1f} pp")
        ck[3].metric("Sentimiento cliente", f"{ik['con_kobra']['sentimiento_prom']:+.2f}",
                     f"{(ik['con_kobra']['sentimiento_prom']-ik['sin_kobra']['sentimiento_prom']):+.2f}")

        # --- Evolución temporal ---
        st.markdown("#### 📈 Evolución mes a mes")
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
                          title="Calidad: con Kobra vs. sin Kobra",
                          labels={"usa_kobra": "Usa Kobra"})
            fig.update_layout(template="plotly_dark", height=340,
                              legend=dict(orientation="h", y=1.15))
            st.plotly_chart(fig, use_container_width=True)

        # --- Características por dimensión ---
        st.markdown("#### 🔍 Características más frecuentes")
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
        st.markdown("#### 💥 Impacto de la calidad de gestión en la cobranza")
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
                    "más conversión y más recupero. Kobra la mejora sistemáticamente.")

        # --- Ranking y mejora por gestor ---
        st.markdown("#### 🏆 Ranking de gestores y mejora en el tiempo")
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
                    "usa_kobra": st.column_config.CheckboxColumn("Kobra"),
                })
        with r2:
            mej = analitica.mejora_por_gestor(gf)
            if not mej.empty:
                fig = px.bar(mej, x="delta_calidad", y="gestor", orientation="h",
                             color="usa_kobra", color_discrete_map={True: PRIMARY, False: "#FF7675"},
                             title="Mejora de calidad (últimos 3m vs. primeros 3m)",
                             labels={"delta_calidad": "Δ calidad", "usa_kobra": "Usa Kobra"})
                fig.update_layout(template="plotly_dark", height=330,
                                  yaxis=dict(autorange="reversed"),
                                  legend=dict(orientation="h", y=1.15))
                st.plotly_chart(fig, use_container_width=True)

        # --- Export ---
        st.markdown("#### ⬇️ Exportar analítica")
        xbuf2 = io.BytesIO()
        with pd.ExcelWriter(xbuf2, engine="xlsxwriter") as xl:
            analitica.ranking_gestores(gf).to_excel(xl, sheet_name="Ranking_gestores", index=False)
            analitica.mejora_por_gestor(gf).to_excel(xl, sheet_name="Mejora_gestores", index=False)
            analitica.evolucion_mensual(gf).to_excel(xl, sheet_name="Evolucion_mensual", index=False)
            analitica.caracteristicas_por(gf, "tramo_mora").to_excel(xl, sheet_name="Por_tramo", index=False)
            analitica.caracteristicas_por(gf, "segmento").to_excel(xl, sheet_name="Por_segmento", index=False)
        st.download_button("📊 Descargar analítica (Excel)", xbuf2.getvalue(),
                           "kobra_analitica_gestion.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ---- Tab 7: Configuración (API keys persistentes) -------------------------
with tab7:
    st.subheader("⚙️ Configuración de API keys")
    st.caption("Ingresá las keys una sola vez: quedan **guardadas** y se cargan solas en "
               "cada arranque. Habilitan la transcripción real (Whisper) y la evaluación "
               "con Claude. El resto de Kobra funciona sin keys.")

    with st.form("form_config"):
        nuevos = {}
        for clave, desc in kconfig.CLAVES.items():
            nuevos[clave] = st.text_input(
                clave, value="", type="password",
                placeholder=("sk-… " if clave == "OPENAI_API_KEY" else "sk-ant-…"),
                help=desc + " · dejá vacío para conservar la guardada")
        b1, b2, _ = st.columns([0.25, 0.25, 0.5])
        guardar_btn = b1.form_submit_button("💾 Guardar", type="primary")
        limpiar_btn = b2.form_submit_button("🗑️ Borrar guardadas")

    # Se procesan antes de mostrar el estado, sin recargar (se queda en la pestaña)
    if guardar_btn:
        if any(v.strip() for v in nuevos.values()):
            kconfig.guardar(nuevos)
            st.success("✅ Configuración guardada. Ya se usa en esta sesión y en próximos arranques.")
        else:
            st.info("Ingresá al menos una key para guardar.")
    if limpiar_btn:
        kconfig.limpiar()
        st.warning("🗑️ Configuración borrada.")

    # Estado actual (refleja lo recién guardado/borrado)
    est = kconfig.estado()
    guardadas = kconfig.cargar()
    cc = st.columns(2)
    for i, (clave, desc) in enumerate(kconfig.CLAVES.items()):
        with cc[i]:
            activo = est.get(clave)
            st.markdown(f"**{desc}**")
            st.markdown(("🟢 Configurada" if activo else "⚪ No configurada") +
                        (f" · `{kconfig.enmascarar(guardadas.get(clave,''))}`"
                         if guardadas.get(clave) else ""))

    st.markdown("---")
    st.markdown(f"📁 Se guardan en `{kconfig.CONFIG_FILE}` (fuera del repo, permisos 600). "
                "En producción podés inyectarlas por variables de entorno / secretos de "
                "Docker; el entorno tiene prioridad sobre el archivo.")

st.markdown("---")
st.caption("Kobra · Plataforma de Cobranzas Inteligente · Demo con datos sintéticos (Uruguay). "
           "Sin nombres de clientes. Reemplazable por la cartera real de cualquier empresa.")
