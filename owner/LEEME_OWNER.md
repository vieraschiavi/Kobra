# 🔑 MV Kobra AI · Versión OWNER (solo para el dueño del producto)

Esta carpeta **no se distribuye nunca**: no entra en el instalador de clientes
(`packaging/kobra.spec` no la empaqueta), no entra en los ZIP de release
(`packaging/build_release.py` no la copia) y está excluida del deploy web
(`.vercelignore`). Es tu copia personal, sin las restricciones comerciales
de la copia de un cliente.

## Qué hace el modo owner

- **Sin licencia, sin trial, sin vencimiento**: arranca directo, sin pedir
  activación ni contraseña — entra como Administrador automáticamente.
- **Acceso completo**: todas las empresas (tenants), todas las pantallas,
  todas las funciones de admin.
- Lo activa la variable de entorno `KOBRA_OWNER=1` sobre el modo standalone.
  El server escucha **solo en 127.0.0.1** (tu propia máquina) — el endpoint
  de entrada directa devuelve 404 en cualquier otro modo, así que la copia
  de un cliente no lo tiene aunque conozca la URL.

> Nota honesta: lo que este modo NO desactiva es el motor de cumplimiento
> (horarios de contacto, feriados, pedidos de no-contactar). Eso no es una
> "restricción de empresa": es lo que hace legal usar el producto con
> deudores reales (Ley 18.331 y equivalentes), y es un argumento de venta.
> Sacarlo te expondría a vos, no a nadie más.

## Cómo usarla

### A) Con el programa instalado (MVKobraAI_Setup.exe) → doble clic en `MVKobraAI_Owner.bat`
Busca el programa instalado (Program Files o instalación por usuario) y lo
arranca en modo owner. El instalador es el MISMO que el de clientes — lo que
cambia es cómo lo arrancás: con el acceso directo normal pide licencia
(modo cliente); con este .bat entra directo (modo owner).

### B) Desde el código fuente (este repo) → doble clic en `MVKobraAI_Owner_desde_codigo.bat`
Requiere Python 3.11+ con `pip install -r requirements.txt` y el frontend
compilado una vez (`cd webapp/frontend && npm ci && npm run build`).

### C) Linux/Mac desde el código → `./mvkobraai_owner.sh`

En los tres casos se abre el navegador solo en `http://localhost:<puerto>`.
