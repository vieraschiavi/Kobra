const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("kobra", {
  edicion: () => ipcRenderer.invoke("kobra:edicion"),
  apiPort: () => ipcRenderer.invoke("kobra:api-port"),
  licenciaEstado: () => ipcRenderer.invoke("kobra:licencia-estado"),
  licenciaGuardar: (payload) => ipcRenderer.invoke("kobra:licencia-guardar", payload),
  abrirExterno: (url) => ipcRenderer.invoke("kobra:abrir-externo", url),
});
