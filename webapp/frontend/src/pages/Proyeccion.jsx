// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useEffect, useState } from "react";
import {
  CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { api, getIdioma } from "../api.js";
import { t } from "../i18n/index.js";

// Cuánto se va a cobrar — y si se le puede creer.
//
// Esta pantalla tiene una obligación rara para un tablero: a veces tiene que
// decir que NO proyecta. Una serie sin señal admite igual que se le dibuje una
// línea prolija, y esa línea se lee como un compromiso: alguien arma la meta
// del mes con ella. Por eso el veredicto va arriba del gráfico y no en una
// nota al pie, y la línea proyectada cambia de aspecto —punteada y gris—
// cuando es un promedio en vez de una predicción.

const COL_REAL = "#2f74c0";
const COL_PRED = "#00c896";
const COL_PROM = "#93a5c0";

const LOCALE = { es: "es-UY", pt: "pt-BR", en: "en-US" };
const money = (n) =>
  "$ " + Math.round(n || 0).toLocaleString(LOCALE[getIdioma()] || LOCALE.es);

function Veredicto({ v, modelo }) {
  const sirve = v.sirve;
  const hold = v.holdout && v.holdout[v.ganador];
  return (
    <div className="card" style={{
      marginBottom: 16,
      borderLeft: `4px solid ${sirve ? COL_PRED : COL_PROM}`,
    }}>
      <div style={{ fontSize: "1.05rem", fontWeight: 600, marginBottom: 4 }}>
        {t(sirve ? "proyeccion.titular_sirve" : "proyeccion.titular_promedio")}
      </div>
      <p style={{ margin: "0 0 10px", fontSize: 13, color: "var(--muted)" }}>
        {t(`proyeccion.veredicto_${v.codigo}`, {
          modelo: t(`proyeccion.modelo_${v.ganador}`),
          trivial: t(`proyeccion.modelo_${v.mejor_trivial}`),
          mejora: v.mejora_vs_trivial == null
            ? "—" : `${Math.round(v.mejora_vs_trivial * 100)}%`,
        })}
      </p>
      {/* Los números del backtest, sin adornos: es lo que respalda —o no— la
          línea de arriba. El MASE del holdout es el único honesto. */}
      <div style={{ display: "flex", gap: 18, flexWrap: "wrap", fontSize: 12.5 }}>
        <span>{t("proyeccion.modelo_usado")}: <b>{t(`proyeccion.modelo_${modelo}`)}</b></span>
        {hold && <span>{t("proyeccion.mase_holdout")}: <b className="tnum">{hold.mase.toFixed(2)}</b></span>}
        {hold && <span>{t("proyeccion.error_medio")}: <b className="tnum">{money(hold.mae)}</b></span>}
        <span>{t("proyeccion.ventanas")}: <b className="tnum">{hold ? hold.ventanas : 0}</b></span>
      </div>
    </div>
  );
}

export default function Proyeccion() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState("");
  const [dias, setDias] = useState(14);

  useEffect(() => {
    setDatos(null);
    setError("");
    api(`/api/proyeccion-cobranza?dias=${dias}`)
      .then(setDatos)
      .catch((e) => setError(e.message));
  }, [dias]);

  const v = datos && datos.veredicto;
  const sirve = !!(v && v.sirve);

  // Una sola serie con dos claves: recharts corta la línea donde falta el
  // valor, así que la historia y la proyección se dibujan como dos trazos
  // continuos que se tocan en el último día real.
  const serie = datos ? [
    ...datos.historia.map((p) => ({ fecha: p.fecha, real: p.valor })),
    ...datos.proyeccion.map((p, i) => ({
      fecha: p.fecha, pred: p.valor,
      ...(i === 0 ? { real: datos.historia[datos.historia.length - 1].valor } : {}),
    })),
  ] : [];
  const corte = datos && datos.historia.length
    ? datos.historia[datos.historia.length - 1].fecha : null;

  // Escala robusta. Un solo día grande —un pago de $7,1M contra una media de
  // $825.000— estira el eje diez veces y aplasta la serie entera contra el
  // piso: el gráfico queda técnicamente correcto y visualmente vacío.
  //
  // Se recorta la escala al percentil 98 y se DICE cuántos días quedaron
  // arriba, con su valor. Recortar en silencio sería peor que el problema:
  // en cobranza el día excepcional suele ser el más importante del mes.
  // El corte sale del percentil 90 y no de uno más alto: con tres días
  // grandes seguidos, un percentil 98 lo define el propio pico y el recorte
  // no se activa nunca — que es exactamente lo que pasaba acá.
  const escala = (() => {
    if (!datos || !datos.historia.length) return { max: "auto", fuera: [] };
    const vals = [...datos.historia.map((p) => p.valor),
                  ...datos.proyeccion.map((p) => p.valor)].sort((a, b) => a - b);
    const tope = Math.round(vals[Math.floor(vals.length * 0.9)] * 1.6);
    const fuera = datos.historia.filter((p) => p.valor > tope);
    return fuera.length ? { max: tope, fuera } : { max: "auto", fuera: [] };
  })();

  return (
    <>
      <h1 className="page-title">{t("proyeccion.titulo")}</h1>
      <p className="page-sub">{t("proyeccion.subtitulo")}</p>

      <div className="toolbar" style={{ gap: 8 }}>
        {[7, 14, 28].map((d) => (
          <button key={d} className={"btn" + (d === dias ? "" : " ghost")}
                  onClick={() => setDias(d)}>
            {t("proyeccion.dias", { n: d })}
          </button>
        ))}
      </div>

      {error && <div className="empty">{error}</div>}
      {!datos && !error && <div className="empty">{t("proyeccion.cargando")}</div>}

      {datos && v && (
        <>
          {v.suficiente
            ? <Veredicto v={v} modelo={datos.modelo} />
            : <div className="card" style={{ marginBottom: 16 }}>
                {t("proyeccion.sin_historia", { n: v.n, minimo: v.minimo })}
              </div>}

          <div className="card">
            <ResponsiveContainer width="100%" height={360}>
              <LineChart data={serie} margin={{ left: 10, right: 20, top: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,.06)" />
                <XAxis dataKey="fecha" tick={{ fill: "#93a5c0", fontSize: 10.5 }}
                       minTickGap={40} />
                <YAxis tick={{ fill: "#93a5c0", fontSize: 10.5 }}
                       domain={[0, escala.max]} allowDataOverflow
                       tickFormatter={(n) => Math.round(n / 1000) + "k"} />
                <Tooltip contentStyle={{ background: "#0b1220", border: "1px solid #2f74c0" }}
                         formatter={(val, key) => [money(val),
                           t(key === "real" ? "proyeccion.serie_real"
                                            : "proyeccion.serie_pred")]} />
                {corte && <ReferenceLine x={corte} stroke={COL_PROM}
                                         strokeDasharray="4 4"
                                         label={{ value: t("proyeccion.hoy"),
                                                  fill: "#93a5c0", fontSize: 11 }} />}
                <Line type="monotone" dataKey="real" stroke={COL_REAL} dot={false}
                      strokeWidth={1.8} connectNulls={false} />
                {/* Punteada y gris cuando es un promedio: la forma de la línea
                    tiene que decir lo mismo que el texto. */}
                <Line type="monotone" dataKey="pred"
                      stroke={sirve ? COL_PRED : COL_PROM} dot={false}
                      strokeWidth={2}
                      strokeDasharray={sirve ? "0" : "5 4"}
                      connectNulls={false} />
              </LineChart>
            </ResponsiveContainer>
            {escala.fuera.length > 0 && (
              <p style={{ color: "var(--muted)", fontSize: 12, margin: "8px 0 0" }}>
                {t("proyeccion.fuera_de_escala", {
                  n: escala.fuera.length,
                  detalle: escala.fuera
                    .sort((a, b) => b.valor - a.valor).slice(0, 3)
                    .map((p) => `${p.fecha} ${money(p.valor)}`).join(" · "),
                })}
              </p>
            )}
            <p style={{ color: "var(--muted)", fontSize: 12, margin: "8px 0 0" }}>
              {t("proyeccion.promedio_historico")}: <b className="tnum">{money(datos.promedio_historico)}</b>
              {" · "}{t("proyeccion.nota_metodo")}
            </p>
          </div>
        </>
      )}
    </>
  );
}
