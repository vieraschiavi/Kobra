// © 2026 Martín Viera. Todos los derechos reservados.

import React, { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { t } from "../i18n/index.js";
import ModuloNoIncluido, { esFaltaDePlan } from "../components/ModuloNoIncluido.jsx";

const VERDE = "#00c896";
const ROJO = "#ff7675";

const num = (n) => Math.round(n || 0).toLocaleString("es-UY");
const money = (n) => "$ " + num(n);

// Una variación puede ser null, y eso NO es cero: es "no hay contra qué
// comparar". El backend ya se cuida de no mandar un cero tranquilizador
// (`_variacion` devuelve None); la pantalla tiene que respetarlo igual, o el
// cuidado se pierde en el último paso.
function Delta({ pct }) {
  if (pct === null || pct === undefined) {
    return <span style={{ color: "var(--muted)" }}>—</span>;
  }
  const signo = pct >= 0 ? "+" : "";
  return (
    <span style={{ color: pct >= 0 ? VERDE : ROJO }}>
      {signo}{pct.toFixed(pct > -10 && pct < 10 ? 1 : 0)}%
    </span>
  );
}

function Aviso({ texto }) {
  if (!texto) return null;
  return (
    <div className="card" style={{
      marginTop: 12, borderLeft: "3px solid var(--muted)",
      color: "var(--muted)", fontSize: 13,
    }}>
      {texto}
    </div>
  );
}

// Las cuatro filas de la comparación. `clave` es la del objeto de métricas que
// devuelve el backend; `money` dice si se muestra con signo de pesos.
const FILAS = [
  { clave: "unidades", etiqueta: "fila_unidades", money: false },
  { clave: "precio_promedio", etiqueta: "fila_precio", money: true },
  { clave: "margen", etiqueta: "fila_margen", money: true },
  { clave: "clientes", etiqueta: "fila_clientes", money: false },
];

/**
 * Las dos comparaciones, en la MISMA tabla y una al lado de la otra.
 *
 * Es la decisión de diseño de la pantalla: contra un día normal la campaña
 * puede verse bien y contra su propia edición anterior estar vendiendo la
 * mitad. Puestas en pestañas separadas, nadie compara las dos columnas; puestas
 * al lado, el contraste es lo primero que se ve.
 */
function Comparacion({ detalle }) {
  const normal = detalle.contra_normal;
  const anterior = detalle.contra_anterior;
  const actual = normal.hay_base ? normal.campania : anterior.actual;

  return (
    <div className="card" style={{ marginTop: 12 }}>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>{t("campanas.col_metrica")}</th>
              <th style={{ textAlign: "right" }}>{t("campanas.col_campania")}</th>
              <th style={{ textAlign: "right" }}>{t("campanas.col_vs_normal")}</th>
              <th style={{ textAlign: "right" }}>{t("campanas.col_vs_anterior")}</th>
            </tr>
          </thead>
          <tbody>
            {FILAS.map((f) => (
              <tr key={f.clave}>
                <td>{t(`campanas.${f.etiqueta}`)}</td>
                <td className="tnum" style={{ textAlign: "right" }}>
                  {f.money ? money(actual[f.clave]) : num(actual[f.clave])}
                </td>
                <td className="tnum" style={{ textAlign: "right" }}>
                  {normal.hay_base
                    ? <Delta pct={normal.variacion[f.clave]} />
                    : <span style={{ color: "var(--muted)" }}>—</span>}
                </td>
                <td className="tnum" style={{ textAlign: "right" }}>
                  {anterior.hay_anterior
                    ? <Delta pct={anterior.variacion[f.clave]} />
                    : <span style={{ color: "var(--muted)" }}>—</span>}
                </td>
              </tr>
            ))}
            <tr>
              <td>{t("campanas.fila_descuento")}</td>
              <td className="tnum" style={{ textAlign: "right" }}>
                {actual.descuento_pct === null || actual.descuento_pct === undefined
                  ? <span style={{ color: "var(--muted)" }}>—</span>
                  : `${actual.descuento_pct.toFixed(1)}%`}
              </td>
              <td colSpan={2} style={{ color: "var(--muted)", fontSize: 12.5 }}>
                {t("campanas.descuento_nota")}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      {!normal.hay_base && <Aviso texto={normal.motivo} />}
      {!anterior.hay_anterior && <Aviso texto={anterior.motivo} />}
    </div>
  );
}

function Segmentos({ filas, aviso }) {
  if (!filas.length) return <div className="empty">{t("campanas.sin_clientes")}</div>;
  return (
    <>
      <Aviso texto={aviso} />
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th style={{ textAlign: "left" }}>{t("campanas.col_segmento")}</th>
              <th style={{ textAlign: "right" }}>{t("campanas.col_clientes")}</th>
              <th style={{ textAlign: "right" }}>{t("campanas.col_monto")}</th>
              <th style={{ textAlign: "right" }}>{t("campanas.col_peso")}</th>
              <th style={{ textAlign: "right" }}>{t("campanas.col_recencia")}</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((f) => (
              <tr key={f.segmento}>
                <td>{f.segmento_nombre}</td>
                <td className="tnum" style={{ textAlign: "right" }}>{num(f.clientes)}</td>
                <td className="tnum" style={{ textAlign: "right" }}>{money(f.monto)}</td>
                <td className="tnum" style={{ textAlign: "right" }}>{f.monto_pct.toFixed(1)}%</td>
                <td className="tnum" style={{ textAlign: "right" }}>{num(f.recencia_mediana)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Cohortes({ filas }) {
  if (!filas.length) return <div className="empty">{t("campanas.sin_cohortes")}</div>;
  // Las columnas de mes salen del propio dato: cuántos meses de historia haya.
  const meses = Object.keys(filas[0])
    .filter((k) => k.startsWith("mes_"))
    .sort((a, b) => Number(a.slice(4)) - Number(b.slice(4)));
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>{t("campanas.col_cohorte")}</th>
            <th style={{ textAlign: "right" }}>{t("campanas.col_clientes")}</th>
            {meses.map((m) => (
              <th key={m} style={{ textAlign: "right" }}>{m.slice(4)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filas.map((f) => (
            <tr key={f.cohorte}>
              <td>{f.cohorte}</td>
              <td className="tnum" style={{ textAlign: "right" }}>{num(f.clientes)}</td>
              {meses.map((m) => (
                <td key={m} className="tnum" style={{
                  textAlign: "right",
                  // Un hueco no es un 0% de retención: es un mes que todavía no
                  // pasó para esa cohorte. Va vacío.
                  color: f[m] === null || f[m] === undefined ? "var(--muted)" : undefined,
                }}>
                  {f[m] === null || f[m] === undefined ? "" : `${f[m].toFixed(0)}%`}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Stock({ filas }) {
  if (!filas || !filas.length) return <div className="empty">{t("campanas.sin_stock")}</div>;
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>{t("campanas.col_sku")}</th>
            <th style={{ textAlign: "left" }}>{t("campanas.col_producto")}</th>
            <th style={{ textAlign: "right" }}>{t("campanas.col_vendidas")}</th>
            <th style={{ textAlign: "right" }}>{t("campanas.col_stock")}</th>
            <th style={{ textAlign: "right" }}>{t("campanas.col_cobertura")}</th>
          </tr>
        </thead>
        <tbody>
          {filas.map((f) => (
            <tr key={f.sku}>
              <td>{f.sku}</td>
              <td>{f.nombre ?? "—"}</td>
              <td className="tnum" style={{ textAlign: "right" }}>{num(f.unidades)}</td>
              <td className="tnum" style={{ textAlign: "right" }}>
                {f.stock === null || f.stock === undefined ? "—" : num(f.stock)}
              </td>
              <td className="tnum" style={{
                textAlign: "right",
                // Menos de 7 días al ritmo de la campaña: se queda sin stock
                // antes de que termine la promoción.
                color: f.cobertura_dias !== null && f.cobertura_dias < 7 ? ROJO : undefined,
              }}>
                {f.cobertura_dias === null || f.cobertura_dias === undefined
                  ? "—" : num(f.cobertura_dias)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function Campanas() {
  const [datos, setDatos] = useState(null);
  const [error, setError] = useState(null);
  const [sinPlan, setSinPlan] = useState(null);
  const [faltanDatos, setFaltanDatos] = useState(false);
  const [campania, setCampania] = useState(null);
  const [tab, setTab] = useState("segmentos");

  const cargar = useCallback(() => {
    setError(null); setFaltanDatos(false);
    const q = campania ? `?campania=${encodeURIComponent(campania)}` : "";
    api(`/api/campanas/resumen${q}`)
      .then(setDatos)
      .catch((e) => {
        const msg = String(e.message || e);
        if (esFaltaDePlan(e)) setSinPlan(msg);
        // Sin tablas cargadas todavía no es un error: es el primer día de uso,
        // y se sube desde la pantalla de logística porque son las MISMAS.
        else if (msg.includes("cargaste") || msg.includes("Subila")) setFaltanDatos(true);
        else setError(msg);
      });
  }, [campania]);

  useEffect(cargar, [cargar]);

  if (sinPlan) {
    return <ModuloNoIncluido modulo="logistica" detalle={sinPlan}
                             ventas={["venta_1", "venta_2", "venta_3", "venta_4"]} />;
  }
  if (faltanDatos) return <div className="empty">{t("campanas.faltan_datos")}</div>;
  if (error) return <div className="empty">{error}</div>;
  if (!datos) return <div className="empty">{t("common.cargando")}</div>;

  const detalle = datos.detalle;
  const nombres = [...new Set((datos.ediciones || []).map((e) => e.campania))];

  return (
    <>
      <h2 className="page-title">{t("campanas.titulo")}</h2>
      <p className="page-sub">{t("campanas.subtitulo")}</p>

      {nombres.length > 1 && (
        <div className="toolbar">
          {nombres.map((n) => (
            <button key={n} className={`btn ${detalle && detalle.campania === n ? "" : "ghost"}`}
                    onClick={() => setCampania(n)}>{n}</button>
          ))}
        </div>
      )}

      {detalle ? (
        <>
          <p className="page-sub" style={{ marginTop: 12 }}>
            <strong>{detalle.campania}</strong> · {detalle.desde} → {detalle.hasta}
          </p>
          <Comparacion detalle={detalle} />
        </>
      ) : (
        <Aviso texto={t("campanas.sin_campanias")} />
      )}

      <Aviso texto={datos.aviso_descuento} />

      <div className="toolbar" style={{ marginTop: 16 }}>
        {["segmentos", "cohortes", "stock"].map((k) => (
          <button key={k} className={`btn ${tab === k ? "" : "ghost"}`}
                  onClick={() => setTab(k)}>{t(`campanas.tab_${k}`)}</button>
        ))}
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        {tab === "segmentos" && (
          <Segmentos filas={datos.segmentos || []} aviso={datos.aviso_rfm} />
        )}
        {tab === "cohortes" && <Cohortes filas={datos.cohortes || []} />}
        {tab === "stock" && <Stock filas={detalle && detalle.stock} />}
      </div>
    </>
  );
}
