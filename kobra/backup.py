"""
MV Kobra AI · Backup y restauración de datos locales
=================================================
El dashboard corre local — no hay backup automático "de nuestro lado"
porque los datos viven en la máquina/servidor del cliente (ver
`docs/WHITEPAPER_SEGURIDAD.md`). Este módulo es la pieza de código real que
hace ese backup posible: empaqueta todo lo que importa (cartera, gestiones,
lista de no-contactar, log de auditoría, config cifrada, base de uso del
backend de licencias) en un único ZIP con fecha, en el destino que elijas —
una carpeta local, o una carpeta ya sincronizada a la nube (Dropbox, OneDrive,
Google Drive) si el cliente prefiere no configurar credenciales de un bucket.

Uso:
    python -m kobra.backup crear [--destino DIR]
    python -m kobra.backup listar [--destino DIR]
    python -m kobra.backup restaurar ARCHIVO.zip [--destino DIR]

Programarlo (backup automático periódico) es un paso de infraestructura, no
de código: en Windows, Programador de tareas ejecutando
`python -m kobra.backup crear`; en Linux/macOS, un cron job. Ver
`docs/WHITEPAPER_SEGURIDAD.md` sección 9.
"""
from __future__ import annotations

import json
import os
import shutil
import zipfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKUP_DIR_DEFAULT = os.environ.get("KOBRA_BACKUP_DIR", os.path.join(ROOT, "backups"))

# Rutas relativas a ROOT (o absolutas, para las que viven en KOBRA_CONFIG_DIR)
_ARCHIVOS_NEGOCIO = [
    "data/kobra_cartera.csv",
    "data/kobra_gestiones.csv",
    "data/no_contactar.csv",
    "data/auditoria.log",
    "outputs/kobra_scored.csv",
    "outputs/model_selection.json",
]


def _archivos_config():
    """Archivos de config/secretos cifrados — viven fuera del repo, en
    KOBRA_CONFIG_DIR. Se incluyen tal cual (ya están cifrados/protegidos por
    permisos del SO; el backup no descifra nada)."""
    from kobra import config as kconfig
    candidatos = [kconfig.CONFIG_FILE_CIFRADO, kconfig.CLAVE_CIFRADO_FILE, kconfig.CONFIG_FILE_PLANO]
    return [p for p in candidatos if os.path.exists(p)]


def _archivos_backend_venta():
    try:
        from backend_venta.uso import DB_PATH
        return [DB_PATH] if os.path.exists(DB_PATH) else []
    except Exception:
        return []


def _archivos_a_incluir() -> list[str]:
    incluidos = [os.path.join(ROOT, rel) for rel in _ARCHIVOS_NEGOCIO if os.path.exists(os.path.join(ROOT, rel))]
    incluidos += _archivos_config()
    incluidos += _archivos_backend_venta()
    return incluidos


def crear_backup(destino: str | None = None) -> dict:
    """
    Crea `kobra_backup_YYYYmmdd_HHMMSS.zip` en `destino` (default
    `BACKUP_DIR_DEFAULT`) con todos los archivos de negocio/config/uso que
    existan en este momento. Devuelve {"ok", "ruta", "archivos", "bytes"}.
    """
    destino = destino or BACKUP_DIR_DEFAULT
    os.makedirs(destino, exist_ok=True)
    archivos = _archivos_a_incluir()
    if not archivos:
        return {"ok": False, "ruta": None, "archivos": 0, "bytes": 0,
                "detalle": "No hay archivos de datos todavía (¿instalación nueva?)."}

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ruta_zip = os.path.join(destino, f"kobra_backup_{ts}.zip")
    manifiesto = {"creado": datetime.now(timezone.utc).isoformat(), "archivos": []}

    with zipfile.ZipFile(ruta_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for ruta in archivos:
            # arcname relativo, sin exponer la estructura absoluta de disco del cliente
            arcname = os.path.basename(os.path.dirname(ruta)) + "/" + os.path.basename(ruta)
            z.write(ruta, arcname)
            manifiesto["archivos"].append({"arcname": arcname, "bytes": os.path.getsize(ruta)})
        z.writestr("manifiesto.json", json.dumps(manifiesto, ensure_ascii=False, indent=2))

    from kobra import auditoria as kauditoria
    kauditoria.registrar("backup_creado", {"ruta": ruta_zip, "archivos": len(archivos)})

    return {"ok": True, "ruta": ruta_zip, "archivos": len(archivos),
            "bytes": os.path.getsize(ruta_zip)}


def listar_backups(destino: str | None = None) -> list[dict]:
    destino = destino or BACKUP_DIR_DEFAULT
    if not os.path.isdir(destino):
        return []
    out = []
    for nombre in sorted(os.listdir(destino), reverse=True):
        if nombre.startswith("kobra_backup_") and nombre.endswith(".zip"):
            ruta = os.path.join(destino, nombre)
            out.append({"nombre": nombre, "ruta": ruta, "bytes": os.path.getsize(ruta),
                       "modificado": datetime.fromtimestamp(os.path.getmtime(ruta), tz=timezone.utc).isoformat()})
    return out


def limpiar_backups_viejos(destino: str | None = None, mantener: int = 10) -> int:
    """Retención simple: conserva los `mantener` backups más recientes, borra el resto."""
    backups = listar_backups(destino)
    a_borrar = backups[mantener:]
    for b in a_borrar:
        os.remove(b["ruta"])
    return len(a_borrar)


def restaurar_backup(ruta_zip: str, destino_root: str | None = None) -> dict:
    """
    Extrae un backup de vuelta a su lugar. `destino_root` es la raíz del
    proyecto (default ROOT) — los archivos de config vuelven a
    KOBRA_CONFIG_DIR, el resto a `data/`/`outputs/` bajo destino_root.
    **Sobrescribe** los archivos existentes; no hace un backup del estado
    actual antes de restaurar (hacelo vos mismo con `crear_backup()` primero
    si querés poder volver atrás).
    """
    if not os.path.exists(ruta_zip):
        return {"ok": False, "detalle": "El archivo de backup no existe."}
    destino_root = destino_root or ROOT
    from kobra import config as kconfig

    extraidos = []
    with zipfile.ZipFile(ruta_zip) as z:
        for info in z.infolist():
            if info.filename == "manifiesto.json":
                continue
            carpeta, nombre = info.filename.split("/", 1)
            _nombres_config = {
                os.path.basename(kconfig.CONFIG_FILE_CIFRADO),
                os.path.basename(kconfig.CLAVE_CIFRADO_FILE),
                os.path.basename(kconfig.CONFIG_FILE_PLANO),
            }
            if nombre in _nombres_config:
                destino_path = os.path.join(kconfig.CONFIG_DIR, nombre)
            else:
                destino_path = os.path.join(destino_root, carpeta, nombre)
            os.makedirs(os.path.dirname(destino_path), exist_ok=True)
            with z.open(info) as origen, open(destino_path, "wb") as f:
                shutil.copyfileobj(origen, f)
            extraidos.append(destino_path)

    from kobra import auditoria as kauditoria
    kauditoria.registrar("backup_restaurado", {"ruta": ruta_zip, "archivos": len(extraidos)})
    return {"ok": True, "archivos": len(extraidos), "rutas": extraidos}


def _cli():
    import argparse
    p = argparse.ArgumentParser(description="Backup/restauración de datos locales de MV Kobra AI")
    sub = p.add_subparsers(dest="accion", required=True)

    p_crear = sub.add_parser("crear")
    p_crear.add_argument("--destino")

    p_listar = sub.add_parser("listar")
    p_listar.add_argument("--destino")

    p_restaurar = sub.add_parser("restaurar")
    p_restaurar.add_argument("archivo")
    p_restaurar.add_argument("--destino")

    args = p.parse_args()
    if args.accion == "crear":
        r = crear_backup(args.destino)
        print(f"[backup] {r}")
    elif args.accion == "listar":
        for b in listar_backups(args.destino):
            print(f"  {b['nombre']}  ({b['bytes']/1024:.0f} KB)  {b['modificado']}")
    elif args.accion == "restaurar":
        r = restaurar_backup(args.archivo, args.destino)
        print(f"[restaurar] {r}")


if __name__ == "__main__":
    _cli()
