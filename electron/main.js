// © 2026 Martín Viera. Todos los derechos reservados.

/*
 * MV Kobra AI · App de escritorio (Electron)
 * ===========================================
 * Proceso principal: arranca el motor (backend FastAPI + React compilado,
 * empaquetado con PyInstaller en resources/backend/) en un puerto libre de
 * 127.0.0.1 y abre la ventana de la app apuntando ahí. La MISMA interfaz
 * React que corre en la nube, como programa de escritorio profesional.
 *
 * En desarrollo (sin empaquetar) levanta el backend desde el código fuente
 * con Python: `npm start` dentro de electron/.
 */
const { app, BrowserWindow, Menu, dialog, shell } = require("electron");
const { spawn, execFile } = require("child_process");
const http = require("http");
const net = require("net");
const path = require("path");
const fs = require("fs");

// La compositación por GPU de Chromium se pelea con OBS Virtual Camera, la
// captura de pantalla de OBS, el escritorio remoto (RDP) y algunos drivers
// viejos: la ventana queda TODA GRIS/negra. Desactivar la aceleración por
// hardware lo evita en todas esas situaciones. Es un dashboard React (nada de
// 3D/video pesado), asi que la compositación por CPU se ve igual de fluida —
// mismo motivo por el que Slack/Discord ofrecen esta opción. Se puede volver a
// activar la GPU con KOBRA_GPU=1 para quien la necesite.
if (process.env.KOBRA_GPU !== "1") {
  app.disableHardwareAcceleration();
  app.commandLine.appendSwitch("disable-gpu-compositing");
}

let ventana = null;
let backend = null;
let cerrando = false;

// ---------------------------------------------------------------------------
// Utilidades
// ---------------------------------------------------------------------------
function puertoLibre() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.unref();
    srv.on("error", reject);
    srv.listen(0, "127.0.0.1", () => {
      const puerto = srv.address().port;
      srv.close(() => resolve(puerto));
    });
  });
}

function esperarBackend(url, timeoutMs) {
  // Espera a que el server responda. El primer arranque instalado puede
  // tardar (siembra la demo y carga el modelo), por eso el timeout generoso.
  const inicio = Date.now();
  return new Promise((resolve, reject) => {
    const intentar = () => {
      const req = http.get(url, (res) => {
        res.resume();
        resolve();
      });
      req.on("error", () => {
        if (cerrando) return reject(new Error("cerrando"));
        if (Date.now() - inicio > timeoutMs) {
          return reject(new Error("El motor de MV Kobra AI no respondió a tiempo."));
        }
        setTimeout(intentar, 500);
      });
      req.setTimeout(2000, () => req.destroy(new Error("timeout")));
    };
    intentar();
  });
}

function rutaBackend() {
  // Instalado: el motor PyInstaller viaja en resources/backend/.
  const empaquetado = path.join(process.resourcesPath, "backend",
    process.platform === "win32" ? "MVKobraAI.exe" : "MVKobraAI");
  if (app.isPackaged) return { cmd: empaquetado, args: [] };
  if (fs.existsSync(empaquetado)) return { cmd: empaquetado, args: [] };
  // Desarrollo: backend desde el código fuente con Python.
  const repo = path.dirname(__dirname);
  const py = process.platform === "win32" ? "python" : "python3";
  return { cmd: py, args: [path.join(repo, "packaging", "kobra_launcher.py")], cwd: repo };
}

// Dónde guarda sus datos el programa (cartera, gestiones, configuración).
//
// Por defecto `kobra/rutas.py` los pone en %LOCALAPPDATA% — o sea en C:, aunque
// el usuario haya elegido instalar en otro disco. Quien instala en D: porque su
// C: está justo de espacio no espera que igual se le llene con los datos.
//
// Regla: si la instalación NO está en el mismo disco que %LOCALAPPDATA%, los
// datos van al lado del programa. Se respeta siempre una ruta explícita en
// KOBRA_DATA_DIR, y NUNCA se mueve una instalación que ya tenga datos donde
// estaban — mover datos por su cuenta sería peor que el problema.
function dirDatosElegido() {
  if (process.env.KOBRA_DATA_DIR) return process.env.KOBRA_DATA_DIR;
  if (process.platform !== "win32" || !app.isPackaged) return null;

  const localAppData = process.env.LOCALAPPDATA;
  if (!localAppData) return null;
  const estandar = path.join(localAppData, "MV Kobra AI");
  if (fs.existsSync(estandar)) return null;   // instalación previa: no tocar

  const instalacion = path.dirname(process.resourcesPath);
  const discoInstalacion = path.parse(instalacion).root.toUpperCase();
  const discoEstandar = path.parse(estandar).root.toUpperCase();
  if (discoInstalacion === discoEstandar) return null;   // ya está en C:, sin cambios

  const propio = path.join(instalacion, "datos");
  try {
    fs.mkdirSync(propio, { recursive: true });
    return propio;
  } catch {
    return null;   // sin permiso: que decida rutas.py, no romper el arranque
  }
}

function arrancarBackend(puerto) {
  const { cmd, args, cwd } = rutaBackend();
  const datos = dirDatosElegido();
  backend = spawn(cmd, args, {
    cwd: cwd || path.dirname(cmd),
    env: {
      ...process.env,
      KOBRA_APP_PORT: String(puerto),
      // Electron ES la ventana: que el launcher no abra otro navegador.
      KOBRA_SIN_NAVEGADOR: "1",
      ...(datos ? { KOBRA_DATA_DIR: datos } : {}),
    },
    windowsHide: true,       // sin ventana de consola detrás de la app
    stdio: "ignore",
  });
  backend.on("exit", (code) => {
    backend = null;
    if (!cerrando && ventana && !ventana.isDestroyed() && code !== 0 && code !== null) {
      dialog.showErrorBox(
        "MV Kobra AI",
        "El motor del programa se cerró inesperadamente.\n" +
        "Volvé a abrir MV Kobra AI; si persiste, reinstalá el programa.");
      app.quit();
    }
  });
}

function matarBackend() {
  if (!backend) return;
  const pid = backend.pid;
  backend = null;
  try {
    if (process.platform === "win32") {
      // Mata el árbol entero (uvicorn puede tener hijos).
      execFile("taskkill", ["/pid", String(pid), "/T", "/F"]);
    } else {
      process.kill(pid, "SIGTERM");
    }
  } catch {
    /* ya estaba muerto */
  }
}

// ---------------------------------------------------------------------------
// Ventana
// ---------------------------------------------------------------------------
async function crearVentana() {
  const puerto = await puertoLibre();

  ventana = new BrowserWindow({
    width: 1360,
    height: 860,
    minWidth: 1024,
    minHeight: 680,
    show: true,
    title: "MV Kobra AI",
    backgroundColor: "#0b1220",
    autoHideMenuBar: true,
    icon: path.join(__dirname, "build", "icon.ico"),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  Menu.setApplicationMenu(null);

  // Links externos (landing, MercadoPago, docs) → navegador del sistema.
  ventana.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("http://127.0.0.1") || url.startsWith("http://localhost")) {
      return { action: "allow" };
    }
    shell.openExternal(url);
    return { action: "deny" };
  });

  // Pantalla de carga con marca mientras el motor levanta.
  await ventana.loadFile(path.join(__dirname, "splash.html"));

  arrancarBackend(puerto);
  const url = `http://127.0.0.1:${puerto}`;
  try {
    await esperarBackend(url, 120_000);
  } catch (e) {
    if (!cerrando) {
      dialog.showErrorBox("MV Kobra AI", String(e.message || e));
      app.quit();
    }
    return;
  }
  if (ventana && !ventana.isDestroyed()) await ventana.loadURL(url);
}

// Una sola instancia: si el usuario hace doble clic dos veces, se enfoca la
// ventana existente en vez de arrancar otro motor.
const unico = app.requestSingleInstanceLock();
if (!unico) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (ventana) {
      if (ventana.isMinimized()) ventana.restore();
      ventana.focus();
    }
  });

  app.whenReady().then(crearVentana);

  app.on("window-all-closed", () => {
    cerrando = true;
    matarBackend();
    app.quit();
  });
  app.on("before-quit", () => {
    cerrando = true;
    matarBackend();
  });
}
