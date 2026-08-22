// © 2026 Martín Viera. Todos los derechos reservados.

// Portal de cobros (lado EMPRESA): configurar los métodos de pago y la
// integración ERP/CRM, generar el acceso de cada deudor (link + QR +
// usuario/código) y ver los pagos que van entrando por el portal.
import qrcode from "qrcode-generator";
import React, { useEffect, useState } from "react";
import { api, fmtMonto } from "../api.js";
import { t } from "../i18n/index.js";
import { IcoCopiar, IcoEnlace, IcoQr } from "../icons.jsx";

function Copiar({ texto }) {
  const [ok, setOk] = useState(false);
  // El contenido es un icono mientras no se copió: sin `aria-label` el botón
  // no tiene nombre accesible y un lector de pantalla lo anuncia como "botón"
  // a secas.
  return (
    <button type="button" className="btn ghost mini" title={t("portal_admin.copiar")}
            aria-label={t("portal_admin.copiar")}
            onClick={async () => {
              try { await navigator.clipboard.writeText(texto); } catch { /* http plano */ }
              setOk(true); setTimeout(() => setOk(false), 1200);
            }}>
      {ok ? t("portal_admin.copiado") : <IcoCopiar size={14} />}
    </button>
  );
}

function Qr({ texto }) {
  // qrcode-generator: sin red, sin canvas — SVG embebido, imprimible.
  // Es HTML propio y estatico en la práctica: `createSvgTag` produce solo
  // <svg><path .../></svg> a partir de la matriz del QR (bits, no texto), así
  // que ningún dato de usuario llega como marcado — el link se codifica como
  // módulos del QR, jamás se interpola en el SVG.
  const qr = qrcode(0, "M");
  qr.addData(texto);
  qr.make();
  const svg = qr.createSvgTag({ cellSize: 4, margin: 2, scalable: true });
  return <div className="qr-caja" title={texto}
              dangerouslySetInnerHTML={{ __html: svg }} />;
}

function ConfigPortal() {
  const [cfg, setCfg] = useState(null);
  const [nota, setNota] = useState("");
  useEffect(() => { api("/api/portal/config").then(setCfg).catch(() => {}); }, []);
  if (!cfg) return null;

  const set = (seccion, clave) => (e) => setCfg({
    ...cfg, [seccion]: { ...cfg[seccion],
      [clave]: e.target.type === "checkbox" ? e.target.checked : e.target.value },
  });

  const guardar = async () => {
    setNota("");
    try {
      const r = await api("/api/portal/config", { metodo: "POST", cuerpo: {
        transferencia: cfg.transferencia, mercadopago: cfg.mercadopago, erp: cfg.erp,
      } });
      setCfg(r);
      setNota(t("portal_admin.config.guardado"));
    } catch (e) { setNota(e.message); }
  };

  return (
    <div className="card" style={{ marginTop: 18 }}>
      <h3>{t("portal_admin.config.titulo")}</h3>
      <p className="page-sub" style={{ marginBottom: 14 }}>{t("portal_admin.config.subtitulo")}</p>

      <div className="portal-cfg-grid">
        <fieldset>
          <legend>
            <label>
              <input type="checkbox" checked={cfg.transferencia.habilitado}
                     onChange={set("transferencia", "habilitado")} />
              {t("portal_admin.config.transferencia")}
            </label>
          </legend>
          <input placeholder={t("portal_admin.config.banco")} aria-label={t("portal_admin.config.banco")} value={cfg.transferencia.banco}
                 onChange={set("transferencia", "banco")} />
          <input placeholder={t("portal_admin.config.titular")} aria-label={t("portal_admin.config.titular")} value={cfg.transferencia.titular}
                 onChange={set("transferencia", "titular")} />
          <input placeholder={t("portal_admin.config.cuenta")} aria-label={t("portal_admin.config.cuenta")} value={cfg.transferencia.cuenta}
                 onChange={set("transferencia", "cuenta")} />
          <input placeholder={t("portal_admin.config.nota")} aria-label={t("portal_admin.config.nota")} value={cfg.transferencia.nota}
                 onChange={set("transferencia", "nota")} />
        </fieldset>

        <fieldset>
          <legend>
            <label>
              <input type="checkbox" checked={cfg.mercadopago.habilitado}
                     onChange={set("mercadopago", "habilitado")} />
              {t("portal_admin.config.mercadopago")}
            </label>
          </legend>
          <input placeholder={t("portal_admin.config.mp_link")} aria-label={t("portal_admin.config.mp_link")} value={cfg.mercadopago.link_base}
                 onChange={set("mercadopago", "link_base")} />
          <p className="portal-ayuda">{t("portal_admin.config.mp_ayuda")}</p>
        </fieldset>

        <fieldset>
          <legend>{t("portal_admin.config.erp")}</legend>
          <input placeholder={t("portal_admin.config.webhook")} aria-label={t("portal_admin.config.webhook")} value={cfg.erp.webhook_url}
                 onChange={set("erp", "webhook_url")} />
          <input placeholder={t("portal_admin.config.api_key")} aria-label={t("portal_admin.config.api_key")} value={cfg.erp.api_key}
                 onChange={set("erp", "api_key")} />
          <p className="portal-ayuda">{t("portal_admin.config.erp_ayuda")}</p>
          <div className="portal-apikey">
            <code>{cfg.erp_api_key_efectiva}</code>
            <Copiar texto={cfg.erp_api_key_efectiva} />
          </div>
          <pre className="portal-curl">{
`curl -H "X-API-Key: ${cfg.erp_api_key_efectiva}" \\
  ${window.location.origin}/api/erp/imputaciones`}</pre>
        </fieldset>
      </div>

      <div className="toolbar" style={{ marginTop: 12 }}>
        <button className="btn" onClick={guardar}>{t("portal_admin.config.guardar")}</button>
        {nota && <span style={{ color: "var(--muted)", fontSize: 13 }}>{nota}</span>}
      </div>
    </div>
  );
}

function AccesoDeudor() {
  const [id, setId] = useState("");
  const [acceso, setAcceso] = useState(null);
  const [error, setError] = useState("");

  const generar = async (e) => {
    e.preventDefault();
    setError(""); setAcceso(null);
    try {
      setAcceso(await api(`/api/portal/acceso/${encodeURIComponent(id.trim().toUpperCase())}`));
    } catch (err) { setError(err.message); }
  };
  const link = acceso ? window.location.origin + acceso.ruta : "";

  return (
    <div className="card" style={{ marginTop: 18 }}>
      <h3>{t("portal_admin.acceso.titulo")}</h3>
      <p className="page-sub" style={{ marginBottom: 14 }}>{t("portal_admin.acceso.subtitulo")}</p>
      <form className="toolbar" onSubmit={generar}>
        <input value={id} onChange={(e) => setId(e.target.value)}
               aria-label={t("portal_admin.acceso.id_ph")}
               placeholder={t("portal_admin.acceso.id_ph")} style={{ width: 180 }} />
        <button className="btn" disabled={!id.trim()}>{t("portal_admin.acceso.generar")}</button>
        {error && <span style={{ color: "var(--red)", fontSize: 13 }}>{error}</span>}
      </form>

      {acceso && (
        <div className="portal-acceso">
          <Qr texto={link} />
          <div className="portal-acceso-datos">
            <div className="portal-ref">
              <span><IcoEnlace size={14} /> {t("portal_admin.acceso.link")}</span>
              <b className="portal-link-texto">{link}</b>
              <Copiar texto={link} />
            </div>
            <div className="portal-ref">
              <span>{t("portal_admin.acceso.usuario")}</span>
              <b className="tnum">{acceso.usuario}</b>
              <Copiar texto={acceso.usuario} />
            </div>
            <div className="portal-ref">
              <span>{t("portal_admin.acceso.codigo")}</span>
              <b className="tnum">{acceso.codigo}</b>
              <Copiar texto={acceso.codigo} />
            </div>
            <p className="portal-ayuda"><IcoQr size={13} /> {t("portal_admin.acceso.ayuda_qr")}</p>
          </div>
        </div>
      )}
    </div>
  );
}

const ESTADO_PILL = { aprobado: "alta", informado: "media", pendiente: "baja" };

function PagosRecibidos() {
  const [datos, setDatos] = useState(null);
  useEffect(() => { api("/api/portal/pagos").then(setDatos).catch(() => {}); }, []);
  if (!datos) return null;
  return (
    <div className="card" style={{ marginTop: 18 }}>
      <h3>{t("portal_admin.pagos.titulo", { total: datos.total })}</h3>
      {datos.total === 0
        ? <p className="page-sub">{t("portal_admin.pagos.vacio")}</p>
        : (
          <div className="tablewrap" style={{ marginTop: 8 }}>
            <table>
              <thead><tr>
                <th>{t("portal_admin.pagos.col_ref")}</th>
                <th>{t("portal_admin.pagos.col_deudor")}</th>
                <th>{t("portal_admin.pagos.col_monto")}</th>
                <th>{t("portal_admin.pagos.col_metodo")}</th>
                <th>{t("portal_admin.pagos.col_tipo")}</th>
                <th>{t("portal_admin.pagos.col_estado")}</th>
                <th>{t("portal_admin.pagos.col_fecha")}</th>
              </tr></thead>
              <tbody>
                {datos.pagos.map((p) => (
                  <tr key={p.referencia} className="norow">
                    <td className="tnum">{p.referencia}</td>
                    <td>{p.id_deudor}</td>
                    <td className="tnum">{fmtMonto(p.monto)}</td>
                    <td>{t(`portal_admin.pagos.metodo_${p.metodo}`)}</td>
                    <td>{t(`portal_admin.pagos.tipo_${p.tipo}`)}</td>
                    <td><span className={"pill " + (ESTADO_PILL[p.estado] || "")}>
                      {t(`portal.historial.estado_${p.estado}`)}</span></td>
                    <td className="tnum">{(p.creado || "").slice(0, 16).replace("T", " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </div>
  );
}

export default function PortalCobros() {
  return (
    <>
      <h1 className="page-title">{t("portal_admin.titulo")}</h1>
      <p className="page-sub">{t("portal_admin.subtitulo")}</p>
      <ConfigPortal />
      <AccesoDeudor />
      <PagosRecibidos />
    </>
  );
}
