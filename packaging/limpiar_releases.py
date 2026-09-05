# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Limpia las releases viejas de GitHub
===================================================
Deja **una descarga por edición** y borra el resto:

    release vX.Y.Z (la última)  ->  MVKobraAI_Setup.exe        (clientes)
    release owner-vX.Y.Z        ->  MVKobraAI_Setup_OWNER.exe  (dueño)

Por qué existe este script
--------------------------
El repo acumuló 20 releases y ~20 GB. La mayor parte era duplicación: cada
release Owner subía un ZIP de 535 MB con los DOS instaladores adentro —los
mismos que ya viajaban sueltos al lado—, más una copia del instalador de
CLIENTES que ya vive en su propia release. `.github/workflows/release_owner.yml`
dejó de generar todo eso, pero lo ya publicado hay que borrarlo a mano.

Borrar 19 releases de a una desde la web es media hora de clics y un error de
distracción borra la equivocada. Acá va la lista explícita, con guardas.

Guardas
-------
* **Simula por defecto.** Sin `--ejecutar` no borra nada: imprime qué haría.
* **Nunca toca el repo público de descargas.** `mv-kobra-ai-releases` es de
  donde bajan los clientes que pagaron; borrar ahí es romperles la descarga.
* **Nunca borra la release de la versión actual**, ni la más nueva de cada
  familia (cliente / owner), aunque estén en la lista por error.
* **No borra tags.** La API de GitHub borra la release y deja el tag, así que
  se conserva qué commit fue cada versión.

Uso:
    export GH_TOKEN=...            # PAT con `contents: write` sobre el repo
    python packaging/limpiar_releases.py                 # simula
    python packaging/limpiar_releases.py --ejecutar      # borra de verdad
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

REPO = "vieraschiavi/Kobra"

# El repo PÚBLICO de descargas. Nunca se limpia desde acá: de ahí baja el
# cliente que pagó, y una release borrada es un link roto en su mail.
REPO_PROHIBIDO = "mv-kobra-ai-releases"

# Las releases a borrar, listadas uñas afuera en vez de calculadas con un
# `< version`: una regla de versiones que se equivoca borra en silencio la
# release que sostiene la descarga de un cliente. Esta lista se lee de un
# vistazo y se revisa antes de correr nada.
A_BORRAR = [
    "v1.3.0", "v1.3.1", "v1.3.3", "v1.3.4", "v1.3.5",
    "v1.3.6", "v1.3.7", "v1.3.8", "v1.3.9", "v1.4.0",
    "owner-v1.3.0", "owner-v1.3.1", "owner-v1.3.4", "owner-v1.3.5",
    "owner-v1.3.6", "owner-v1.3.7", "owner-v1.3.8", "owner-v1.3.9",
    # Vencida, no solo pesada: se publicó el 12-ago y el sello firmado
    # (`token_owner`) entró el 21-ago, así que su `Owner.bat` escribe el sello
    # viejo SIN firma y el programa lo ignora. Su .exe, además, es anterior a
    # tres semanas de arreglos. Se regenera con `release_owner.yml`.
    "owner-v1.4.0",
]

# Assets que sobran en las releases que SÍ se conservan.
ASSETS_A_BORRAR = {
    # ZIP con Python adentro: el .exe de la misma release ya trae el trial.
    # Quedó de una versión anterior del workflow, que ya no lo genera.
    "v1.5.0": ["MVKobraAI_Demo_v1.5.0.zip"],
}


def _api(ruta: str, token: str, metodo: str = "GET"):
    req = urllib.request.Request(
        f"https://api.github.com{ruta}", method=metodo,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "kobra-limpiar-releases"})
    try:
        with urllib.request.urlopen(req) as r:
            cuerpo = r.read()
            return json.loads(cuerpo) if cuerpo else None
    except urllib.error.HTTPError as e:
        raise SystemExit(f"[ERROR] {metodo} {ruta} -> {e.code} {e.reason}\n"
                         f"  {e.read().decode('utf-8', 'replace')[:300]}") from e


def releases(repo: str, token: str) -> list[dict]:
    todas, pagina = [], 1
    while True:
        lote = _api(f"/repos/{repo}/releases?per_page=100&page={pagina}", token)
        if not lote:
            return todas
        todas += lote
        pagina += 1


def _mas_nueva_por_familia(todas: list[dict]) -> set[str]:
    """El tag más reciente de cada familia (cliente y owner).

    Se mira `published_at` y no el número de versión: comparar versiones a
    mano ordena mal en cuanto aparece un `v1.10.0`, y equivocarse acá borra
    la release que sostiene la descarga.
    """
    familias: dict[str, dict] = {}
    for r in todas:
        fam = "owner" if r["tag_name"].startswith("owner-") else "cliente"
        if fam not in familias or r["published_at"] > familias[fam]["published_at"]:
            familias[fam] = r
    return {r["tag_name"] for r in familias.values()}


def plan(todas: list[dict], version_actual: str) -> tuple[list[dict], list[str]]:
    """Qué se borra y qué se protege, sin tocar nada todavía."""
    protegidas = _mas_nueva_por_familia(todas) | {f"v{version_actual}"}
    borrar, avisos = [], []
    por_tag = {r["tag_name"]: r for r in todas}

    for tag in A_BORRAR:
        r = por_tag.get(tag)
        if r is None:
            avisos.append(f"{tag}: ya no existe (nada que hacer)")
            continue
        if tag in protegidas:
            avisos.append(f"{tag}: PROTEGIDA (es la más nueva de su familia "
                          f"o la versión actual) — no se borra")
            continue
        borrar.append(r)
    return borrar, avisos


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Limpia releases viejas de GitHub.")
    p.add_argument("--repo", default=REPO)
    p.add_argument("--ejecutar", action="store_true",
                   help="borrar de verdad (sin esto solo simula)")
    args = p.parse_args(argv)

    if REPO_PROHIBIDO in args.repo:
        raise SystemExit(
            f"[ERROR] {args.repo} es el repo PÚBLICO de descargas.\n"
            "  De ahí baja el cliente que pagó: borrar una release ahí le deja\n"
            "  el link del mail en 404. Este script no lo toca.")

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit(
            "[ERROR] falta el token. Es un PAT con permiso `contents: write`\n"
            "  sobre el repo:  export GH_TOKEN=...")

    from kobra import __version__ as version_actual
    todas = releases(args.repo, token)
    borrar, avisos = plan(todas, version_actual)

    print(f"Repo: {args.repo}  ·  {len(todas)} releases  ·  "
          f"versión actual v{version_actual}")
    for a in avisos:
        print(f"  · {a}")
    print()

    if not args.ejecutar:
        print("SIMULACIÓN — no se borra nada. Agregá --ejecutar para hacerlo.\n")

    for r in borrar:
        peso = sum(a["size"] for a in r.get("assets", [])) / 1e6
        print(f"  {'BORRAR' if args.ejecutar else 'borraría'}  "
              f"{r['tag_name']:<16} ({peso:,.0f} MB en assets)")
        if args.ejecutar:
            _api(f"/repos/{args.repo}/releases/{r['id']}", token, "DELETE")

    for tag, nombres in ASSETS_A_BORRAR.items():
        r = next((x for x in todas if x["tag_name"] == tag), None)
        if r is None:
            continue
        for a in r.get("assets", []):
            if a["name"] in nombres:
                print(f"  {'BORRAR' if args.ejecutar else 'borraría'}  "
                      f"asset {tag}/{a['name']} ({a['size']/1e6:,.1f} MB)")
                if args.ejecutar:
                    _api(f"/repos/{args.repo}/releases/assets/{a['id']}",
                         token, "DELETE")

    liberado = sum(sum(a["size"] for a in r.get("assets", [])) for r in borrar)
    print(f"\n{len(borrar)} releases · ~{liberado/1e9:,.1f} GB")
    print("Los tags de git quedan: la API borra la release, no el tag.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
