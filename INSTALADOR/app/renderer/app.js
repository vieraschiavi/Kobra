let API_BASE = "";
let LICENCIA = { ok: false, modo: "demo" };

const fmtUYU = (n) =>
  new Intl.NumberFormat("es-UY", { style: "currency", currency: "UYU", maximumFractionDigits: 0 }).format(n);
const fmtPct = (n) => `${(n * 100).toFixed(1)}%`;

function limiteFilas() {
  return LICENCIA.ok ? 1000 : 5; // demo: solo primeras 5 filas por tabla
}

async function api(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API ${path} -> ${res.status}`);
  return res.json();
}

function setActiveView(view) {
  document.querySelectorAll(".nav-item").forEach((el) => el.classList.toggle("active", el.dataset.view === view));
  document.querySelectorAll(".view").forEach((el) => el.classList.toggle("active", el.id === `view-${view}`));
}

function demoBanner() {
  if (LICENCIA.ok) return "";
  return `<div class="demo-banner">
    <span>🔒 Modo demo: mostrando una muestra limitada de la cartera. Activá tu licencia en <b>Configuración</b> para ver todo.</span>
  </div>`;
}

async function renderVision() {
  const el = document.getElementById("vision-content");
  try {
    const data = await api("/api/vision");
    const filas = data.top_oportunidades.slice(0, limiteFilas());
    el.innerHTML = `
      ${demoBanner()}
      <div class="kpi-row">
        <div class="kpi"><div class="n">${data.kpis.deudores.toLocaleString("es-UY")}</div><div class="l">Deudores en cartera</div></div>
        <div class="kpi"><div class="n">${fmtUYU(data.kpis.cartera_total_uyu)}</div><div class="l">Cartera total</div></div>
        <div class="kpi"><div class="n">${fmtUYU(data.kpis.recupero_esperado_uyu)}</div><div class="l">Recupero esperado</div></div>
        <div class="kpi"><div class="n">${fmtPct(data.kpis.probpago_prom)}</div><div class="l">ProbPago promedio</div></div>
      </div>
      <div class="panel-card">
        <h3>Modelo ProbPago — AUC ${data.metrics.auc_roc} · Lift decil 10: ${data.metrics.lift_decil10}x</h3>
        <table>
          <thead><tr><th>Deudor</th><th>Monto</th><th>ProbPago</th><th>Estrategia</th><th>Valor esperado</th></tr></thead>
          <tbody>
            ${filas
              .map(
                (r) => `<tr>
                  <td>${r.id_deudor}</td><td>${fmtUYU(r.monto_deuda)}</td>
                  <td>${fmtPct(r.probpago)}</td><td><span class="pill">${r.estrategia}</span></td>
                  <td>${fmtUYU(r.valor_esperado_recupero)}</td>
                </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>`;
  } catch (e) {
    el.innerHTML = `<div class="msg err">No se pudo cargar: ${e.message}</div>`;
  }
}

async function renderNegociador() {
  const el = document.getElementById("negociador-content");
  try {
    const data = await api("/api/negociador");
    const acciones = data.top_acciones.slice(0, limiteFilas());
    el.innerHTML = `
      ${demoBanner()}
      <div class="panel-card">
        <h3>Resumen por estrategia</h3>
        <table>
          <thead><tr><th>Estrategia</th><th>Deudores</th><th>Cartera</th><th>Recupero esperado</th><th>ProbPago prom.</th></tr></thead>
          <tbody>
            ${data.resumen_estrategias
              .map(
                (r) => `<tr>
                  <td>${r.estrategia}</td><td>${r.deudores}</td><td>${fmtUYU(r.cartera_uyu)}</td>
                  <td>${fmtUYU(r.recupero_esperado_uyu)}</td><td>${fmtPct(r.probpago_prom)}</td>
                </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
      <div class="panel-card">
        <h3>Próximas acciones (por prioridad)</h3>
        <table>
          <thead><tr><th>#</th><th>Deudor</th><th>Estrategia</th><th>Canal</th><th>Cuotas</th></tr></thead>
          <tbody>
            ${acciones
              .map(
                (r) => `<tr>
                  <td>${r.prioridad}</td><td>${r.id_deudor}</td><td>${r.estrategia}</td>
                  <td>${r.canal_recomendado}</td><td>${r.plan_cuotas}</td>
                </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>`;
  } catch (e) {
    el.innerHTML = `<div class="msg err">No se pudo cargar: ${e.message}</div>`;
  }
}

function renderConfig() {
  const el = document.getElementById("config-content");
  if (LICENCIA.modo === "owner") {
    el.innerHTML = `<div class="panel-card"><h3>Edición Owner</h3>
      <p>Esta instalación tiene acceso completo, sin licencia — es la build privada del dueño del producto.</p>
      <span class="pill">Plan Enterprise · todas las features</span></div>`;
    return;
  }
  if (LICENCIA.ok) {
    const c = LICENCIA.claims;
    const venc = new Date(c.exp * 1000).toLocaleDateString("es-UY");
    el.innerHTML = `<div class="panel-card"><h3>Licencia activa</h3>
      <p>Plan <b>${c.plan}</b> · vence el ${venc} · cupo mensual: ${c.cupo_mensual ?? "ilimitado"}</p>
      <span class="pill">${c.features.join(" · ")}</span></div>`;
    return;
  }
  el.innerHTML = `<div class="panel-card">
    <h3>Modo demo</h3>
    <p>Estás viendo una muestra limitada de la cartera. Cuando compres un plan, pegá acá la
    licencia que te llega por email para desbloquear la versión completa.</p>
    <div class="license-form">
      <input id="license-input" placeholder="Pegá tu licencia (token)" />
      <button class="btn btn-amber" id="license-activate">Activar licencia</button>
      <div id="license-msg" class="msg"></div>
    </div>
  </div>`;

  document.getElementById("license-activate").addEventListener("click", async () => {
    const msg = document.getElementById("license-msg");
    const token = document.getElementById("license-input").value.trim();
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/api/licencia/activar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Licencia inválida");
      await window.kobra.licenciaGuardar({ token, claims: data.claims });
      msg.className = "msg ok";
      msg.textContent = "Licencia activada. Reiniciando vista…";
      await bootLicencia();
      renderConfig();
      renderVision();
      renderNegociador();
    } catch (e) {
      msg.className = "msg err";
      msg.textContent = e.message;
    }
  });
}

function updateBadge() {
  const b = document.getElementById("edicion-badge");
  if (LICENCIA.modo === "owner") {
    b.className = "badge full";
    b.innerHTML = `<span class="dot"></span> Edición Owner`;
  } else if (LICENCIA.ok) {
    b.className = "badge full";
    b.innerHTML = `<span class="dot"></span> Licencia ${LICENCIA.claims.plan}`;
  } else {
    b.className = "badge demo";
    b.innerHTML = `<span class="dot"></span> Modo demo`;
  }
}

async function bootLicencia() {
  LICENCIA = await window.kobra.licenciaEstado();
  updateBadge();
}

async function main() {
  const port = await window.kobra.apiPort();
  API_BASE = `http://127.0.0.1:${port}`;
  await bootLicencia();

  document.querySelectorAll(".nav-item").forEach((el) => {
    el.addEventListener("click", () => setActiveView(el.dataset.view));
  });

  renderVision();
  renderNegociador();
  renderConfig();
}

main();
