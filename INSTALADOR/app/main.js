// MV Kobra AI · Escritorio (Electron) — proceso principal
//
// Arranca el servidor local (pyapi/server.py, o el .exe compilado con
// PyInstaller en la build empaquetada), abre la ventana y resuelve el modo
// de licencia: "owner" nunca pide clave, "cliente" arranca en demo y se
// activa con la licencia que emite el backend de venta al pagar.

const { app, BrowserWindow, ipcMain, shell } = require("electron");
const path = require("path");
const { spawn } = require("child_process");
const http = require("http");
const license = require("./license");

const API_PORT = 8420;
const API_HEALTH_URL = `http://127.0.0.1:${API_PORT}/health`;
const IS_PACKAGED = app.isPackaged;

let mainWindow = null;
let apiProcess = null;

function edicion() {
  // Baked en build time por scripts/build-cliente.* / build-owner.* dentro
  // de build-config.json (ver electron-builder.yml -> extraResources).
  try {
    const cfg = require(
      IS_PACKAGED
        ? path.join(process.resourcesPath, "build-config.json")
        : path.join(__dirname, "build-config.dev.json")
    );
    return cfg.edition === "owner" ? "owner" : "cliente";
  } catch {
    return "cliente";
  }
}

function startApiServer() {
  return new Promise((resolve, reject) => {
    if (IS_PACKAGED) {
      // Build empaquetada: el .exe standalone generado con PyInstaller
      // (ver scripts/build-*.sh), sin depender de un Python instalado.
      const exe = path.join(process.resourcesPath, "kobra-api", "kobra-api.exe");
      apiProcess = spawn(exe, [], { env: { ...process.env, KOBRA_LOCAL_API_PORT: API_PORT } });
    } else {
      // Desarrollo: usa el venv local del repo.
      const py = process.env.KOBRA_DEV_PYTHON || "python3";
      apiProcess = spawn(py, [path.join(__dirname, "pyapi", "server.py")], {
        env: { ...process.env, KOBRA_LOCAL_API_PORT: API_PORT },
      });
    }

    apiProcess.stdout.on("data", (d) => process.stdout.write(`[api] ${d}`));
    apiProcess.stderr.on("data", (d) => process.stderr.write(`[api] ${d}`));
    apiProcess.on("error", reject);

    const tryHealth = (attempt) => {
      http
        .get(API_HEALTH_URL, () => resolve())
        .on("error", () => {
          if (attempt > 40) return reject(new Error("API local no respondió a tiempo"));
          setTimeout(() => tryHealth(attempt + 1), 250);
        });
    };
    tryHealth(0);
  });
}

async function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 1024,
    minHeight: 680,
    backgroundColor: "#081527",
    icon: path.join(__dirname, "build", "icon.png"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.setMenuBarVisibility(false);
  await mainWindow.loadFile(path.join(__dirname, "renderer", "index.html"));
}

ipcMain.handle("kobra:edicion", () => edicion());
ipcMain.handle("kobra:api-port", () => API_PORT);
ipcMain.handle("kobra:licencia-estado", () => license.leerLicencia(app));
ipcMain.handle("kobra:licencia-guardar", (_evt, claims) => license.guardarLicencia(app, claims));
ipcMain.handle("kobra:abrir-externo", (_evt, url) => shell.openExternal(url));

app.whenReady().then(async () => {
  try {
    await startApiServer();
  } catch (err) {
    console.error("No se pudo levantar la API local:", err);
  }
  await createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (apiProcess) apiProcess.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (apiProcess) apiProcess.kill();
});
