# MV Kobra AI · Instalador de escritorio (Electron, sin Streamlit)

App de escritorio real (ventana nativa Electron, no un navegador apuntando
a Streamlit) para MV Kobra AI. Reutiliza el motor Python existente
(`kobra/`, `backend_venta/`) a través de una API local liviana — el panel
Streamlit (`app/app.py`, en la raíz del repo) sigue existiendo para la
versión web/servidor, pero **el instalador de esta carpeta no lo usa**.

Cubre 3 pestañas del panel original como v1 (Visión general, Agente
Negociador, Configuración/licencia) — no reemplaza todavía las 13 pestañas
completas del Streamlit. Es la base real y funcionando para sumar el
resto (Cartera & Export, Modelo ProbPago, Copiloto en Vivo, Gestores,
Agenda, ERP, etc.) siguiendo el mismo patrón: un endpoint nuevo en
`app/pyapi/server.py` + una vista nueva en `app/renderer/`.

## Cómo está armado

```
INSTALADOR/
  app/
    main.js            proceso principal de Electron: levanta la API local y la ventana
    preload.js          puente seguro entre main y el renderer (contextIsolation)
    license.js           lee/guarda la licencia local; decide demo/cliente/owner
    renderer/            UI (HTML/CSS/JS), mismo sistema de diseño navy/ámbar de MV
    pyapi/
      server.py           API FastAPI que envuelve kobra/probpago.py y kobra/negociador.py
      kobra_api.spec       PyInstaller: compila server.py a un .exe standalone (sin Streamlit)
    electron-builder.yml  config del instalador Windows (NSIS)
    scripts/prep-edition.js   genera resources/build-config.json (cliente|owner)
  scripts/
    build_installer.py     orquesta pyinstaller + electron-builder
    BUILD_CLIENTE.bat       doble clic → instalador público
    BUILD_OWNER.bat          doble clic → instalador privado del dueño
```

## Las dos versiones

| | Cliente | Owner |
|---|---|---|
| Quién lo descarga | Cualquier visitante de la landing / release público | Solo vos, desde un release privado o carpeta interna del repo |
| Arranque | Modo demo: cartera limitada a 5 filas por vista | Acceso completo desde el primer arranque |
| Desbloqueo | Pega la licencia (JWT) que ya emite `backend_venta/licencias.py` al confirmarse el pago en Mercado Pago | No aplica — nunca pide clave |
| Cómo se genera | `BUILD_CLIENTE.bat` | `BUILD_OWNER.bat` |

Las dos build salen del **mismo código fuente** — lo único que cambia es
`resources/build-config.json` (`{"edition":"cliente"}` o `{"edition":"owner"}`),
horneado en la build antes de empaquetar. No hay ningún secreto
compartido embebido en el `.exe` del cliente: la validación de licencia la
hace la misma API local corriendo `backend_venta/licencias.licencia_activa()`.

## Instalador Windows: qué incluye

`electron-builder` con target NSIS genera un `.exe` que instala:

- Ícono en el Escritorio (`build/icon.ico`, la marca MV existente).
- Entrada en el Menú Inicio.
- Desinstalador registrado en "Agregar o quitar programas" de Windows.
- Carpeta de instalación elegible por el usuario (no exige admin/UAC).

## Cómo generar el `.exe` (tiene que correr en Windows)

PyInstaller no cruza de plataforma — un `.exe` de Windows se compila en
Windows. Este sandbox de desarrollo es Linux, así que **el `.exe` final no
se compiló acá**; sí se verificó que toda la app funciona de punta a
punta (ver "Qué se verificó" abajo). Para producir el instalador real:

1. En una máquina Windows (o un runner de CI Windows) con **Python 3.11+**
   y **Node.js 18+** instalados:
   ```powershell
   cd INSTALADOR
   pip install -r app\pyapi\requirements.txt pyinstaller
   ```
2. Doble clic en `scripts\BUILD_CLIENTE.bat` (o `BUILD_OWNER.bat`).
3. El instalador queda en `INSTALADOR\app\dist\MV-Kobra-AI-<edicion>-Setup-<version>.exe`.

`BUILD_OWNER.bat` es para tu uso personal — no lo subas a un release
público ni a una carpeta accesible por clientes.

## Qué se verificó en este sandbox (Linux, sin GUI)

- La API local (`pyapi/server.py`) corre contra el motor real de Kobra:
  `/api/vision` y `/api/negociador` devuelven KPIs y recomendaciones
  calculados de verdad (no datos de prueba hardcodeados).
- La app Electron completa arranca bajo Xvfb (pantalla virtual), levanta
  la API como proceso hijo, y las 3 vistas renderizan con datos reales.
- Flujo de licencia probado de punta a punta: modo demo (5 filas + aviso)
  → pegar una licencia real emitida por `backend_venta/licencias.py` →
  pasa a modo completo (10+ filas, badge "Licencia pro", sin aviso) → la
  licencia persiste en el perfil de usuario entre reinicios.
- Modo "owner" probado por separado: arranca directo en acceso completo,
  badge "Edición Owner", sin ningún prompt de licencia.

Lo que **no** se verificó acá (requiere Windows): la compilación real del
`.exe` con PyInstaller + NSIS, el icono de escritorio, el menú de
programa y el desinstalador — esos tres últimos son comportamiento
estándar de NSIS/`electron-builder`, no código nuevo de esta app, pero
igual conviene probar el instalador una vez generado antes de distribuirlo.
