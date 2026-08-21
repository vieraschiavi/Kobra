// © 2026 Martín Viera. Todos los derechos reservados.

// Portal público de pagos: la página que ve el DEUDOR al entrar por el link,
// el QR o con usuario+código. No requiere sesión de la plataforma — el acceso
// es el token firmado del link (o el que devuelve el login del deudor).
// Diseño sobrio y profesional: es la cara de la EMPRESA cliente, no de Kobra.
import React, { useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { t } from "../i18n/index.js";
import { IcoBanco, IcoCandado, IcoCheck, IcoPago } from "../icons.jsx";

async function apiPublica(ruta, cuerpo) {
  const r = await fetch(ruta, cuerpo === undefined ? {} : {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(cuerpo),
  });
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(datos.detail || `Error ${r.status}`);
  return datos;
}

const fmt = (n, moneda) =>
  (moneda?.simbolo || "$") + " " +
  Math.round(n || 0).toLocaleString(moneda?.locale || "es-UY");

function LoginDeudor({ onToken }) {
  const [usuario, setUsuario] = useState("");
  const [codigo, setCodigo] = useState("");
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(false);

  const entrar = async (e) => {
    e.preventDefault();
    setError(""); setCargando(true);
    try {
      const r = await apiPublica("/api/portal/public/login",
                                 { usuario, codigo });
      onToken(r.token);
    } catch (err) {
      setError(err.message);
    } finally {
      setCargando(false);
    }
  };

  return (
    <form className="portal-card portal-login" onSubmit={entrar}>
      <div className="portal-icono"><IcoCandado size={22} /></div>
      <h2>{t("portal.login.titulo")}</h2>
      <p className="portal-muted">{t("portal.login.subtitulo")}</p>
      <label>{t("portal.login.usuario")}
        <input value={usuario} onChange={(e) => setUsuario(e.target.value)}
               placeholder={t("portal.login.usuario_ph")} autoFocus />
      </label>
      <label>{t("portal.login.codigo")}
        <input value={codigo} onChange={(e) => setCodigo(e.target.value)}
               placeholder="000000" inputMode="numeric" maxLength={6} />
      </label>
      {error && <div className="portal-error">{error}</div>}
      <button className="btn portal-btn" disabled={cargando || !usuario || codigo.length < 6}>
        {cargando ? t("common.cargando") : t("portal.login.entrar")}
      </button>
    </form>
  );
}

function Metodo({ activo, onClick, icono, titulo, detalle, deshabilitado }) {
  if (deshabilitado) return null;
  return (
    <button type="button" onClick={onClick}
            className={"portal-metodo" + (activo ? " on" : "")}>
      <span className="portal-metodo-ico">{icono}</span>
      <span>
        <b>{titulo}</b>
        <small>{detalle}</small>
      </span>
    </button>
  );
}

export default function PortalPago() {
  const loc = useLocation();
  const tokenUrl = useMemo(
    () => new URLSearchParams(loc.search).get("t") || "", [loc.search]);
  const [token, setToken] = useState(tokenUrl);
  const [estado, setEstado] = useState(null);
  const [error, setError] = useState("");

  // Flujo de pago
  const [tipo, setTipo] = useState("total");           // total | parcial
  const [monto, setMonto] = useState("");
  const [metodo, setMetodo] = useState("");
  const [pago, setPago] = useState(null);              // respuesta de /pagar
  const [confirmado, setConfirmado] = useState(null);  // respuesta de /confirmar
  const [procesando, setProcesando] = useState(false);

  const cargar = (tk) =>
    apiPublica(`/api/portal/public/estado?t=${encodeURIComponent(tk)}`)
      .then((e) => { setEstado(e); setError(""); })
      .catch((e) => { setEstado(null); setError(e.message); });

  useEffect(() => { if (token) cargar(token); }, [token]);

  const moneda = estado?.moneda;
  const saldo = estado?.saldo ?? 0;
  const montoAPagar = tipo === "total" ? saldo : parseFloat(monto) || 0;
  const puedePagar = metodo && montoAPagar > 0 && montoAPagar <= saldo + 0.01;

  const pagar = async () => {
    setProcesando(true); setError("");
    try {
      const r = await apiPublica("/api/portal/public/pagar",
                                 { t: token, monto: montoAPagar, metodo });
      setPago(r);
      if (r.url_pago) window.open(r.url_pago, "_blank", "noopener");
    } catch (e) {
      setError(e.message);
    } finally {
      setProcesando(false);
    }
  };

  // MercadoPago devuelve al deudor con el id del pago en la URL. Sin
  // mandarlo, el backend no tiene contra qué verificar y toda la
  // comprobación server-side (kobra/mercadopago.py::verificar_pago) quedaba
  // sin ejecutarse nunca desde la UI: alcanzaba con apretar "ya pagué" para
  // que el saldo bajara y se disparara el webhook al ERP.
  //
  // El nombre del parámetro cambia según cómo vuelva: `payment_id` en el
  // retorno del checkout, `collection_id` en algunas integraciones.
  const idDePagoEnLaUrl = () => {
    try {
      const cruda = window.location.hash.includes("?")
        ? window.location.hash.split("?")[1]
        : window.location.search;
      const q = new URLSearchParams(cruda);
      const id = q.get("payment_id") || q.get("collection_id") || "";
      return /^\d+$/.test(id) ? id : "";
    } catch {
      return "";
    }
  };

  const confirmar = async () => {
    setProcesando(true); setError("");
    try {
      const cuerpo = { t: token, referencia: pago.referencia };
      const pid = idDePagoEnLaUrl();
      if (pid) cuerpo.payment_id = pid;
      const r = await apiPublica("/api/portal/public/confirmar", cuerpo);
      setConfirmado(r);
      cargar(token);
    } catch (e) {
      setError(e.message);
    } finally {
      setProcesando(false);
    }
  };

  const otroPago = () => {
    setPago(null); setConfirmado(null); setMetodo(""); setTipo("total"); setMonto("");
  };

  return (
    <div className="portal-fondo">
      <header className="portal-header">
        <span className="portal-marca">
          <img src="/mv_icon.png" alt="" />
          {t("portal.header.titulo")}
        </span>
        <span className="portal-seguro"><IcoCandado size={13} /> {t("portal.header.seguro")}</span>
      </header>

      <main className="portal-main">
        {!token && <LoginDeudor onToken={setToken} />}
        {token && !estado && !error && (
          <div className="portal-card">{t("common.cargando")}</div>
        )}
        {token && error && !estado && (
          <div className="portal-card">
            <div className="portal-error">{error}</div>
            <button className="btn ghost" style={{ marginTop: 12 }}
                    onClick={() => { setToken(""); setError(""); }}>
              {t("portal.entrar_con_codigo")}
            </button>
          </div>
        )}

        {estado && confirmado && (
          <div className="portal-card portal-exito">
            <div className="portal-icono ok"><IcoCheck size={26} /></div>
            <h2>{t("portal.exito.titulo")}</h2>
            <p>{t("portal.exito.detalle", {
              monto: fmt(confirmado.monto, moneda),
              referencia: confirmado.referencia,
            })}</p>
            <p className="portal-muted">
              {confirmado.estado === "aprobado"
                ? t("portal.exito.aprobado")
                : t("portal.exito.informado")}
            </p>
            {estado.saldo > 0 ? (
              <>
                <p className="portal-saldo-restante">
                  {t("portal.exito.saldo_restante", { saldo: fmt(estado.saldo, moneda) })}
                </p>
                <button className="btn portal-btn" onClick={otroPago}>
                  {t("portal.exito.otro_pago")}
                </button>
              </>
            ) : (
              <p className="portal-saldo-cero">{t("portal.exito.deuda_saldada")}</p>
            )}
          </div>
        )}

        {estado && !confirmado && pago && (
          <div className="portal-card">
            <h2>{pago.metodo === "transferencia"
              ? t("portal.pagoref.titulo_transferencia")
              : t("portal.pagoref.titulo_mp")}</h2>
            <div className="portal-ref">
              <span>{t("portal.pagoref.referencia")}</span>
              <b className="tnum">{pago.referencia}</b>
            </div>
            <div className="portal-ref">
              <span>{t("portal.pagoref.monto")}</span>
              <b className="tnum">{fmt(pago.monto, moneda)}</b>
            </div>
            {pago.transferencia && (
              <div className="portal-datos-banco">
                {[["banco", pago.transferencia.banco],
                  ["titular", pago.transferencia.titular],
                  ["cuenta", pago.transferencia.cuenta],
                  ["nota", pago.transferencia.nota]]
                  .filter(([, v]) => v)
                  .map(([k, v]) => (
                    <div className="portal-ref" key={k}>
                      <span>{t(`portal.pagoref.${k}`)}</span><b>{v}</b>
                    </div>
                  ))}
                <p className="portal-muted">{t("portal.pagoref.instruccion_transferencia")}</p>
              </div>
            )}
            {pago.url_pago && (
              <p className="portal-muted">
                {t("portal.pagoref.instruccion_mp")}{" "}
                <a className="portal-link" href={pago.url_pago} target="_blank"
                   rel="noreferrer">{t("portal.pagoref.abrir_mp")}</a>
              </p>
            )}
            {error && <div className="portal-error">{error}</div>}
            <div className="portal-acciones">
              <button className="btn ghost" onClick={otroPago} disabled={procesando}>
                {t("portal.pagoref.volver")}
              </button>
              <button className="btn portal-btn" onClick={confirmar} disabled={procesando}>
                {pago.metodo === "transferencia"
                  ? t("portal.pagoref.ya_transferi")
                  : t("portal.pagoref.ya_pague")}
              </button>
            </div>
          </div>
        )}

        {estado && !pago && !confirmado && (
          <>
            <div className="portal-card portal-resumen">
              <div>
                <span className="portal-muted">{t("portal.resumen.titular", { id: estado.id_deudor })}</span>
                <h1 className="tnum">{fmt(saldo, moneda)}</h1>
                <span className="portal-muted">{t("portal.resumen.saldo_pendiente")}</span>
              </div>
            </div>

            <div className="portal-card">
              <h3>{t("portal.facturas.titulo")}</h3>
              <table className="portal-tabla">
                <thead><tr>
                  <th>{t("portal.facturas.col_numero")}</th>
                  <th>{t("portal.facturas.col_concepto")}</th>
                  <th>{t("portal.facturas.col_vencimiento")}</th>
                  <th className="tnum">{t("portal.facturas.col_monto")}</th>
                </tr></thead>
                <tbody>
                  {estado.facturas.map((f) => (
                    <tr key={f.numero}>
                      <td className="tnum">{f.numero}</td>
                      <td>{f.concepto}</td>
                      <td className="tnum">{f.vencimiento}</td>
                      <td className="tnum">{fmt(f.monto, moneda)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {saldo > 0 && (
              <div className="portal-card">
                <h3>{t("portal.pagar.titulo")}</h3>
                <div className="portal-tipo">
                  <label className={tipo === "total" ? "on" : ""}>
                    <input type="radio" checked={tipo === "total"}
                           onChange={() => setTipo("total")} />
                    {t("portal.pagar.total", { monto: fmt(saldo, moneda) })}
                  </label>
                  <label className={tipo === "parcial" ? "on" : ""}>
                    <input type="radio" checked={tipo === "parcial"}
                           onChange={() => setTipo("parcial")} />
                    {t("portal.pagar.parcial")}
                  </label>
                  {tipo === "parcial" && (
                    <input type="number" className="portal-monto" min="1"
                           max={saldo} value={monto} placeholder={t("portal.pagar.monto_ph")}
                           onChange={(e) => setMonto(e.target.value)} />
                  )}
                </div>

                <div className="portal-metodos">
                  <Metodo activo={metodo === "transferencia"}
                          onClick={() => setMetodo("transferencia")}
                          deshabilitado={!estado.metodos.transferencia}
                          icono={<IcoBanco size={20} />}
                          titulo={t("portal.pagar.transferencia")}
                          detalle={t("portal.pagar.transferencia_det")} />
                  <Metodo activo={metodo === "mercadopago"}
                          onClick={() => setMetodo("mercadopago")}
                          deshabilitado={!estado.metodos.mercadopago}
                          icono={<IcoPago size={20} />}
                          titulo={t("portal.pagar.mercadopago")}
                          detalle={t("portal.pagar.mercadopago_det")} />
                </div>

                {error && <div className="portal-error">{error}</div>}
                <button className="btn portal-btn" disabled={!puedePagar || procesando}
                        onClick={pagar}>
                  {procesando ? t("common.cargando")
                    : t("portal.pagar.boton", { monto: fmt(montoAPagar, moneda) })}
                </button>
              </div>
            )}

            {estado.pagos.length > 0 && (
              <div className="portal-card">
                <h3>{t("portal.historial.titulo")}</h3>
                <table className="portal-tabla">
                  <tbody>
                    {estado.pagos.map((p) => (
                      <tr key={p.referencia}>
                        <td className="tnum">{p.referencia}</td>
                        <td className="tnum">{fmt(p.monto, moneda)}</td>
                        <td>{t(`portal.historial.estado_${p.estado}`) }</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </main>

      <footer className="portal-footer">{t("portal.footer")}</footer>
    </div>
  );
}
