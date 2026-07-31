"""
MV Kobra AI · Publicar la edición Owner como release descargable
================================================================
Arma el ZIP de la edición Owner y lo sube como release de GitHub, en un solo
comando y **sin depender de GitHub Actions** — que es el punto: el workflow
`release_owner.yml` hace lo mismo, pero no sirve de nada mientras la cuenta no
tenga minutos de Actions disponibles. Esto corre desde cualquier máquina con
Python y un token.

    python packaging/publicar_owner.py --token ghp_xxx
    python packaging/publicar_owner.py --dry-run          # sin publicar nada

El token sale de https://github.com/settings/tokens (fine-grained), con acceso
**solo** a este repositorio y permiso de escritura en *Contents*. También se
toma de la variable de entorno `GITHUB_TOKEN` o `RELEASES_TOKEN`.

DÓNDE SE PUBLICA Y POR QUÉ
--------------------------
Solo en `vieraschiavi/Kobra`, que es **privado**. La edición Owner arranca sin
licencia, sin trial y sin vencimiento: publicarla en el repo público de
descargas (`mv-kobra-ai-releases`) equivaldría a regalar el producto completo a
cualquiera que la baje. El script rechaza cualquier repo cuyo nombre sugiera
que es el público, y verifica contra la API que el repo sea privado antes de
subir nada.

La release se marca `make_latest=false`: el enlace
`/releases/latest/download/MVKobraAI_Setup.exe` de la landing tiene que seguir
apuntando al instalador de clientes.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_DEFAULT = "vieraschiavi/Kobra"
API = "https://api.github.com"

# Nombres de repos donde esta edición NUNCA puede publicarse.
REPOS_PROHIBIDOS = ("releases", "public", "descargas", "downloads")


def _cargar_empaquetador():
    spec = importlib.util.spec_from_file_location(
        "build_release", os.path.join(ROOT, "packaging", "build_release.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Verificación del paquete (el mismo gate que corre el workflow)
# ---------------------------------------------------------------------------
PIEZAS = (
    "INSTALAR.bat", "INICIAR_OWNER.bat",
    "kobra_software/kobra_launcher.py",
    "kobra_software/packaging/instalar_windows.ps1",
    "kobra_software/packaging/desinstalar_windows.ps1",
    "kobra_software/electron/build/icon.ico",
    "kobra_software/edicion.json",
)
BOM = b"\xef\xbb\xbf"


def verificar(zip_path: str) -> dict:
    """Un ZIP mal armado que igual se publica es peor que no publicar nada: se
    descarga, no arranca, y el error aparece recién en la PC del que lo bajó."""
    with zipfile.ZipFile(zip_path) as z:
        nombres = z.namelist()
        faltan = [p for p in PIEZAS if p not in nombres]
        if faltan:
            raise SystemExit(f"[ERROR] Al paquete le faltan piezas: {faltan}")
        con_bom = [n for n in nombres
                   if n.lower().endswith((".bat", ".cmd")) and z.read(n).startswith(BOM)]
        if con_bom:
            raise SystemExit(
                f"[ERROR] .bat con BOM (cmd.exe falla al abrirlos): {con_bom}")
        ed = json.loads(z.read("kobra_software/edicion.json"))
    if not ed.get("owner"):
        raise SystemExit(f"[ERROR] edicion.json no es owner: {ed}")
    if ed.get("dias") or ed.get("plan"):
        raise SystemExit(f"[ERROR] la edición owner no puede llevar límite: {ed}")
    return {"archivos": len(nombres), "edicion": ed}


# ---------------------------------------------------------------------------
# API de GitHub (urllib: sin dependencias nuevas para una tarea de una vez)
# ---------------------------------------------------------------------------
def _pedir(url: str, token: str, datos=None, metodo=None,
           binario: bytes | None = None, content_type: str | None = None):
    cuerpo = binario if binario is not None else (
        json.dumps(datos).encode() if datos is not None else None)
    req = urllib.request.Request(url, data=cuerpo, method=metodo)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("Content-Type", content_type or "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detalle = e.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"[ERROR] GitHub respondió {e.code} en {url}\n{detalle}")


def _validar_destino(repo: str, token: str) -> None:
    nombre = repo.split("/")[-1].lower()
    if any(p in nombre for p in REPOS_PROHIBIDOS):
        raise SystemExit(
            f"[ERROR] '{repo}' parece el repositorio PÚBLICO de descargas.\n"
            "        La edición Owner arranca sin licencia: publicarla ahí es\n"
            "        regalar el producto completo. Usá el repo privado.")
    info = _pedir(f"{API}/repos/{repo}", token)
    if not info.get("private"):
        raise SystemExit(
            f"[ERROR] '{repo}' es PÚBLICO. La edición Owner no se publica en\n"
            "        repositorios públicos — cualquiera podría descargarla y\n"
            "        usar el producto sin licencia.")


def publicar(zip_path: str, tag: str, nombre: str, cuerpo: str,
             repo: str, token: str) -> str:
    _validar_destino(repo, token)

    existente = None
    try:
        existente = _pedir(f"{API}/repos/{repo}/releases/tags/{tag}", token)
    except SystemExit:
        pass   # 404: no existe todavía, es lo normal

    if existente:
        release = existente
        print(f"[i] La release {tag} ya existía: se le reemplaza el archivo.")
        for a in release.get("assets", []):
            if a["name"] == os.path.basename(zip_path):
                _pedir(f"{API}/repos/{repo}/releases/assets/{a['id']}", token,
                       metodo="DELETE")
    else:
        release = _pedir(f"{API}/repos/{repo}/releases", token, datos={
            "tag_name": tag, "name": nombre, "body": cuerpo,
            "draft": False, "prerelease": False,
            # Nunca `latest`: ese enlace es del instalador de clientes.
            "make_latest": "false",
        })

    subida = release["upload_url"].split("{")[0]
    with open(zip_path, "rb") as f:
        datos = f.read()
    asset = _pedir(f"{subida}?name={os.path.basename(zip_path)}", token,
                   binario=datos, content_type="application/zip")
    return asset["browser_download_url"]


CUERPO = """**Edición Owner — copia del dueño.** Sin licencia, sin trial y sin
vencimiento. Acceso completo a todas las empresas y pantallas.

### Cómo usarla en Windows
1. Descargá y descomprimí el ZIP.
2. `INSTALAR.bat` → deja el programa instalado con icono propio, acceso en el
   Escritorio, entrada en el Menú Inicio y desinstalador en «Agregar o quitar
   programas». No pide permisos de administrador.
3. También podés abrirlo sin instalar, con `INICIAR_OWNER.bat`.

Al desinstalar, tus datos **no** se borran salvo que lo pidas.

### No redistribuir
Esta edición no valida licencia: quien la tenga usa el producto completo sin
límite. Por eso se publica solo en este repositorio privado.

> El motor de cumplimiento (horarios de contacto, feriados, pedidos de
> no-contactar) sigue activo también acá. No es una restricción comercial: es
> lo que hace legal usar el producto con deudores reales (Ley 18.331).
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[2])
    ap.add_argument("--token", default=os.getenv("GITHUB_TOKEN") or os.getenv("RELEASES_TOKEN"),
                    help="token de GitHub con permiso de escritura en Contents")
    ap.add_argument("--repo", default=REPO_DEFAULT, help="owner/repo destino (privado)")
    ap.add_argument("--tag", default=None, help="tag de la release (default: owner-vVERSION)")
    ap.add_argument("--dry-run", action="store_true",
                    help="armar y verificar el paquete, sin publicar")
    args = ap.parse_args()

    br = _cargar_empaquetador()
    tag = args.tag or f"owner-v{br.VERSION}"

    print("[1/3] Armando la edición Owner...")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = br.build_edicion(tmp, "Owner")
    print(f"      {os.path.basename(zip_path)}  "
          f"({os.path.getsize(zip_path) // 1024} KB)")

    print("[2/3] Verificando el paquete...")
    r = verificar(zip_path)
    print(f"      OK: {r['archivos']} archivos · edicion={r['edicion']}")

    if args.dry_run:
        print("[3/3] --dry-run: no se publica nada.")
        print(f"      El paquete quedó en: {zip_path}")
        return 0

    if not args.token:
        raise SystemExit(
            "[ERROR] Falta el token. Pasalo con --token o poné GITHUB_TOKEN.\n"
            "        Se saca de https://github.com/settings/tokens\n"
            "        (fine-grained, solo este repo, permiso Contents: write).")

    print(f"[3/3] Publicando en {args.repo} como {tag}...")
    url = publicar(zip_path, tag, f"MV Kobra AI · Owner v{br.VERSION}",
                   CUERPO, args.repo, args.token)
    print(f"\n  Listo. Descarga directa:\n    {url}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
