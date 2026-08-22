// © 2026 Martín Viera. Todos los derechos reservados.

// Demostración en vivo: el circuito entero delante de un cliente, operado
// desde esta pantalla. Nadie tiene que abrir una consola en el medio de una
// reunión — ese era el punto: si para mostrar el producto hay que tipear un
// comando, la demo ya perdió.
//
// El orden de la pantalla es el orden de la reunión: quién es el deudor, qué
// se le va a decir, contactarlo, cobrarle, y negociar lo que queda.
import React, { useEffect, useState } from "react";
import qrcode from "qrcode-generator";
import { api } from "../api.js";
import { t } from "../i18n/index.js";

// QR del link de pago, para que el cliente lo escanee con su propio celular
// en la mesa — que es la parte que convence. Mismo enfoque que PortalCobros:
// SVG generado sin red y sin canvas, con el texto solo en `title` (los
// módulos del QR son bits, jamás se interpola texto en el SVG).
function QR({ texto, lado = 148 }) {
  if (!texto) return null;
  const qr = qrcode(0, "M");
  qr.addData(texto);
  qr.make();
  const n = qr.getModuleCount();
  let d = "";
  for (let f = 0; f < n; f++)
    for (let c = 0; c < n; c++)
      if (qr.isDark(f, c)) d += `M${c} ${f}h1v1h-1z`;
  return (
    <div className="qr-caja" title={texto} style={{ width: lado, height: lado }}>
      <svg viewBox={`0 0 ${n} ${n}`} shapeRendering="crispEdges" role="img"
           aria-label={t("demo.qr_alt")}>
        <path d={d} fill="#0a1020" />
      </svg>
    </div>
  );
}

export default function DemoVivo() {
  const [est, setEst] = useState(null);
  const [error, setError] = useState("");
  const [nota, setNota] = useState("");
  const [ocupado, setOcupado] = useState("");
  const [pago, setPago] = useState(null);
  const [paymentId, setPaymentId] = useState("");
  const [contacto, setContacto] = useState({});
  const [monto, setMonto] = useState(100);
  const [acuerdo, setAcuerdo] = useState(null);
  const [fecha, setFecha] = useState("");

  const cargar = () =>
    api("/api/demo/estado").then((d) => {
      setEst(d);
      setMonto(Math.min(d.pago_demo, d.saldo || d.pago_demo));
    }).catch((e) => setError(e.message));
  useEffect(() => { cargar(); }, []);

  if (error) return <div className="empty">{error}</div>;
  if (!est) return <div className="empty">…</div>;

  const correr = async (etiqueta, fn) => {
    setOcupado(etiqueta); setNota(""); setError("");
    try { await fn(); } catch (e) { setError(e.message); }
    finally { setOcupado(""); }
  };

  const guardarContacto = () => correr("contacto", async () => {
    await api("/api/demo/contacto", { metodo: "POST", cuerpo: { valores: contacto } });
    setNota(t("demo.contacto_guardado"));
    setContacto({});
    cargar();
  });

  const contactar = () => correr("contactar", async () => {
    const r = await api("/api/demo/contactar", { metodo: "POST", cuerpo: {} });
    setNota(r.pasos.map((p) => `${p.ok ? "✓" : "✗"} ${p.titulo}${p.detalle ? ": " + p.detalle : ""}`)
      .join(" · "));
  });

  const cobrar = (metodo) => correr("cobrar", async () => {
    const r = await api("/api/demo/cobrar", { metodo: "POST", cuerpo: { monto, metodo } });
    setPago(r);
  });

  const acreditar = () => correr("acreditar", async () => {
    const r = await api("/api/demo/acreditar",
      { metodo: "POST", cuerpo: { referencia: pago.referencia, payment_id: paymentId } });
    setPago({ ...pago, ...r });
    setNota(r.estado === "aprobado"
      ? t("demo.cobro_aprobado")
      : t("demo.cobro_informado") + (r.verificacion?.detalle ? ` (${r.verificacion.detalle})` : ""));
    cargar();
  });

  const registrarPromesa = () => correr("promesa", async () => {
    const op = acuerdo || est.propuestas[0];
    await api("/api/demo/promesa", { metodo: "POST", cuerpo: {
      monto_acordado: op.monto, cuotas: op.cuotas,
      descuento: op.descuento / 100, fecha_compromiso: fecha } });
    setNota(t("demo.promesa_ok"));
    cargar();
  });

  const c = est.caso;
  const moneda = (v) => `${c.moneda === "UYU" ? "$U" : "$"} ${Number(v).toFixed(0)}`;

  return (
    <>
      <h1 className="page-title">{t("demo.titulo")}</h1>
      <p className="page-sub">{t("demo.subtitulo")}</p>

      {/* Qué falta para que suene el teléfono */}
      {!est.contacto_ok && (
        <div className="card" style={{ maxWidth: 720, marginBottom: 18,
             borderColor: "rgba(242,180,65,.4)", background: "rgba(242,180,65,.07)" }}>
          <h3 style={{ marginTop: 0, color: "var(--amber)" }}>{t("demo.falta_titulo")}</h3>
          <p style={{ color: "var(--muted)", fontSize: 13.5 }}>
            {t("demo.falta_sub")}
          </p>
          <div style={{ display: "grid", gap: 10, marginTop: 10,
                        gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))" }}>
            {Object.entries(est.claves).map(([clave, desc]) => (
              <label key={clave} style={{ fontSize: 12.5, color: "var(--muted)" }}>
                {desc}
                <input type="text" style={{ width: "100%", marginTop: 4 }}
                       value={contacto[clave] ?? ""}
                       onChange={(e) => setContacto({ ...contacto, [clave]: e.target.value })} />
              </label>
            ))}
          </div>
          <div className="toolbar" style={{ marginTop: 10 }}>
            <button className="btn" disabled={ocupado === "contacto"} onClick={guardarContacto}>
              {t("demo.guardar_contacto")}
            </button>
          </div>
          <p style={{ color: "var(--faint)", fontSize: 12, marginTop: 8 }}>
            {t("demo.donde_se_guarda")}
          </p>
        </div>
      )}

      {/* El caso */}
      <div className="kpi-grid">
        <div className="card kpi"><div className="label">{t("demo.kpi_deudor")}</div>
          <div className="value" style={{ fontSize: 18 }}>{c.nombre}</div></div>
        <div className="card kpi"><div className="label">{t("demo.kpi_deuda")}</div>
          <div className="value tnum">{moneda(c.monto_deuda)}</div></div>
        <div className="card kpi"><div className="label">{t("demo.kpi_mora")}</div>
          <div className="value tnum">{c.dias_mora}</div>
          <div className="delta">{c.tramo_mora}</div></div>
        <div className="card kpi"><div className="label">{t("demo.kpi_saldo")}</div>
          <div className="value tnum">{moneda(est.saldo)}</div></div>
      </div>
      <p style={{ color: "var(--muted)", fontSize: 13, marginTop: 10 }}>
        {c.telefono || t("demo.sin_telefono")} · {c.email || t("demo.sin_email")} ·
        {" "}{t("demo.vence")} {c.fecha_alta}
      </p>

      {/* El guion */}
      <div className="card" style={{ marginTop: 18 }}>
        <h3 style={{ marginTop: 0 }}>{t("demo.guion_titulo")}</h3>
        <ol style={{ margin: 0, paddingLeft: 20, display: "flex",
                     flexDirection: "column", gap: 10 }}>
          {est.guion.map((p) => (
            <li key={p.orden} style={{ fontSize: 13.5, color: "var(--muted)" }}>
              <b style={{ color: "var(--ink)" }}>{p.titulo}</b>
              <span className="pill media" style={{ marginLeft: 8 }}>{p.canal}</span>
              <div>{p.detalle}</div>
            </li>
          ))}
        </ol>
      </div>

      {/* Contactar y cobrar */}
      <div className="charts-grid">
        <div className="card">
          <h3 style={{ marginTop: 0 }}>{t("demo.contactar_titulo")}</h3>
          <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("demo.contactar_sub")}</p>
          {!est.base_url && (
            <p style={{ color: "var(--amber)", fontSize: 12.5 }}>{t("demo.falta_base_url")}</p>
          )}
          <button className="btn" onClick={contactar}
                  disabled={!est.contacto_ok || !est.base_url || ocupado === "contactar"}>
            {ocupado === "contactar" ? t("demo.contactando") : t("demo.contactar_boton")}
          </button>
        </div>

        <div className="card">
          <h3 style={{ marginTop: 0 }}>{t("demo.cobrar_titulo")}</h3>
          <div className="toolbar">
            <input type="number" min="1" max={est.saldo} value={monto} style={{ width: 120 }}
                   aria-label={t("demo.cobrar_titulo")}
                   onChange={(e) => setMonto(Number(e.target.value))} />
            <button className="btn" onClick={() => cobrar("mercadopago")}
                    disabled={est.saldo <= 0 || ocupado === "cobrar"}>
              {t("demo.cobrar_mp")}
            </button>
            <button className="btn ghost" onClick={() => cobrar("transferencia")}
                    disabled={est.saldo <= 0 || ocupado === "cobrar"}>
              {t("demo.cobrar_transferencia")}
            </button>
          </div>
        </div>
      </div>

      {/* El link generado, con QR para escanear */}
      {pago && (
        <div className="card" style={{ marginTop: 18 }}>
          <h3 style={{ marginTop: 0 }}>
            {pago.referencia} · {moneda(pago.monto)}
            <span className={"pill " + (pago.estado === "aprobado" ? "alta"
                             : pago.estado === "informado" ? "media" : "baja")}
                  style={{ marginLeft: 10 }}>{pago.estado}</span>
          </h3>

          {pago.url_pago && (
            <div className="portal-acceso">
              <div className="portal-acceso-datos">
                <p style={{ color: "var(--muted)", fontSize: 13 }}>{t("demo.escanear")}</p>
                <a className="btn" href={pago.url_pago} target="_blank" rel="noreferrer">
                  {t("demo.abrir_checkout")}
                </a>
                <p className="portal-link-texto" style={{ marginTop: 10, wordBreak: "break-all" }}>
                  {pago.url_pago}
                </p>
              </div>
              <QR texto={pago.url_pago} />
            </div>
          )}

          {pago.transferencia && (
            <div className="tablewrap" style={{ marginTop: 10 }}>
              <table><tbody>
                {Object.entries(pago.transferencia).map(([k, v]) => (
                  <tr key={k} className="norow"><td>{k}</td><td>{String(v)}</td></tr>
                ))}
              </tbody></table>
            </div>
          )}

          {/* Tarjetas ficticias: solo aparecen con credenciales de prueba */}
          {pago.datos_prueba && (
            <div style={{ marginTop: 14, padding: "12px 14px", borderRadius: 10,
                          background: "rgba(0,200,150,.10)",
                          border: "1px solid rgba(0,200,150,.3)" }}>
              <b style={{ fontSize: 13.5 }}>{t("demo.modo_prueba")}</b>
              <ul style={{ margin: "8px 0 0", paddingLeft: 18, fontSize: 13,
                           color: "var(--muted)" }}>
                {pago.datos_prueba.tarjetas.map((tj) => (
                  <li key={tj.numero}>
                    <b style={{ color: "var(--ink)" }}>{tj.marca}</b>{" "}
                    <span className="portal-link-texto">{tj.numero}</span> · CVV {tj.cvv} ·{" "}
                    {tj.vence}
                  </li>
                ))}
                <li>{t("demo.titular", { apro: pago.datos_prueba.titular.aprobar,
                                          othe: pago.datos_prueba.titular.rechazar })}</li>
                <li>{pago.datos_prueba.documento.tipo} {pago.datos_prueba.documento.numero}</li>
              </ul>
              <p style={{ color: "var(--faint)", fontSize: 11.5, marginTop: 8 }}>
                {pago.datos_prueba.aviso}
              </p>
            </div>
          )}

          {pago.estado === "pendiente" && (
            <div className="toolbar" style={{ marginTop: 14 }}>
              <input type="text" placeholder={t("demo.ph_payment_id")} value={paymentId}
                     aria-label={t("demo.ph_payment_id")}
                     style={{ minWidth: 220 }}
                     onChange={(e) => setPaymentId(e.target.value)} />
              <button className="btn" onClick={acreditar} disabled={ocupado === "acreditar"}>
                {t("demo.acreditar")}
              </button>
              <span style={{ color: "var(--faint)", fontSize: 12 }}>{t("demo.payment_id_ayuda")}</span>
            </div>
          )}
        </div>
      )}

      {/* La diferencia */}
      {est.saldo > 0 && est.propuestas.length > 0 && (
        <div className="card" style={{ marginTop: 18 }}>
          <h3 style={{ marginTop: 0 }}>
            {t("demo.diferencia_titulo", { saldo: moneda(est.saldo) })}
          </h3>
          <div className="tablewrap">
            <table>
              <thead><tr>
                <th>{t("demo.col_opcion")}</th><th>{t("demo.col_monto")}</th>
                <th>{t("demo.col_cuotas")}</th><th>{t("demo.col_desc")}</th>
                <th>{t("demo.col_detalle")}</th><th></th>
              </tr></thead>
              <tbody>
                {est.propuestas.map((o) => (
                  <tr key={o.opcion} className="norow"
                      style={{ background: acuerdo?.opcion === o.opcion
                               ? "rgba(124,194,66,.10)" : undefined }}>
                    <td>{o.opcion}</td>
                    <td className="tnum">{moneda(o.monto)}</td>
                    <td className="tnum">{o.cuotas}</td>
                    <td className="tnum">{o.descuento}%</td>
                    <td style={{ whiteSpace: "normal" }}>{o.detalle}</td>
                    <td>
                      <button className={"btn mini" + (acuerdo?.opcion === o.opcion ? "" : " ghost")}
                              onClick={() => setAcuerdo(o)}>
                        {t("demo.elegir")}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="toolbar" style={{ marginTop: 12 }}>
            <input type="date" value={fecha} aria-label={t("demo.registrar_promesa")}
                   onChange={(e) => setFecha(e.target.value)} />
            <button className="btn" onClick={registrarPromesa}
                    disabled={!acuerdo || !fecha || ocupado === "promesa"}>
              {t("demo.registrar_promesa")}
            </button>
          </div>
        </div>
      )}

      {est.saldo <= 0 && (
        <div className="card" style={{ marginTop: 18 }}>
          <h3 style={{ marginTop: 0, color: "var(--green-deep)" }}>{t("demo.cancelada")}</h3>
        </div>
      )}

      {nota && <p style={{ color: "var(--muted)", fontSize: 13.5, marginTop: 14 }}>{nota}</p>}
    </>
  );
}
