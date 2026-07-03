"""
Kobra · Empaquetador de releases
================================
Arma los dos paquetes distribuibles, listos para entregar como software:

  dist/Kobra_Demo_v{VERSION}.zip        → para prospectos: doble clic y corre
                                          (dashboard offline, sin instalar nada)
  dist/Kobra_Produccion_v{VERSION}.zip  → software completo con instalador
                                          (Docker o Python), manual y licencia

Ambos incluyen lanzadores para Windows (.bat) y Linux/Mac (.sh), LEEME,
licencia, VERSION y checksums SHA-256. `referencia_R/`, `.git` y artefactos
pesados no distribuibles quedan fuera.

Uso:
    python packaging/build_release.py
"""
import hashlib
import os
import shutil
import zipfile

VERSION = "1.3.0"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "dist")

# ---------------------------------------------------------------------------
# Textos comunes
# ---------------------------------------------------------------------------
LICENCIA_DEMO = f"""KOBRA IA · LICENCIA DE EVALUACIÓN (DEMO) · v{VERSION}
=====================================================

Este paquete es una DEMOSTRACIÓN de Kobra IA, Plataforma de Cobranzas
Inteligentes, con DATOS 100% SINTÉTICOS (sin datos de personas reales).

1. Se concede permiso de uso únicamente para EVALUACIÓN interna del
   producto. No incluye derecho de uso productivo ni comercial.
2. Prohibida la redistribución, modificación, ingeniería inversa o
   publicación de este software sin autorización escrita del titular.
3. Las métricas de impacto y de modelo incluidas son ILUSTRATIVAS de la
   metodología; no constituyen resultados medidos ni promesa de resultados.
4. El software se entrega "TAL CUAL", sin garantías de ningún tipo.
5. Todos los derechos reservados al titular de Kobra.

(Borrador comercial: revisar con asesoría legal antes de distribuir.)
"""

LICENCIA_PROD = f"""KOBRA IA · CONTRATO DE LICENCIA DE USO (EULA) · v{VERSION}
========================================================

1. OBJETO. El titular de Kobra concede al cliente una licencia de uso, no
   exclusiva e intransferible, del software Kobra IA (Plataforma de Cobranzas
   Inteligentes) para uso interno, según la propuesta comercial acordada.
2. PROPIEDAD. El software, su código, diseño y documentación son propiedad
   del titular. Esta licencia no transfiere titularidad alguna.
3. DATOS. El cliente es responsable de los datos que cargue (incl. Ley
   18.331 de Protección de Datos Personales de Uruguay). El paquete se
   distribuye con datos sintéticos, sin información personal real.
4. ALCANCE HONESTO. Las métricas de la demo son ilustrativas de la
   metodología. El desempeño real (modelo e impacto) se mide durante el
   piloto/implementación con datos del cliente.
5. RESTRICCIONES. Prohibida la redistribución, sublicencia, ingeniería
   inversa y remoción de avisos de titularidad.
6. GARANTÍA Y RESPONSABILIDAD. Salvo pacto escrito, el software se entrega
   "TAL CUAL"; la responsabilidad total queda limitada a lo abonado por la
   licencia en los últimos 12 meses.
7. LEY APLICABLE. República Oriental del Uruguay.

(Borrador comercial: revisar y completar con asesoría legal antes de firmar.)
"""


def _write(path, content=None, crlf=False, **kw):
    if content is None:
        content = kw["content"]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if crlf:
        content = content.replace("\n", "\r\n")
    with open(path, "w", encoding="utf-8-sig" if crlf else "utf-8", newline="") as f:
        f.write(content)


def _copy(src_rel, dst):
    src = os.path.join(ROOT, src_rel)
    if os.path.isdir(src):
        shutil.copytree(src, dst, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    elif os.path.exists(src):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)


def _zipdir(staging, zpath):
    os.makedirs(DIST, exist_ok=True)
    if os.path.exists(zpath):
        os.remove(zpath)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for base, _dirs, files in os.walk(staging):
            for fn in files:
                full = os.path.join(base, fn)
                z.write(full, os.path.relpath(full, staging))
    return zpath


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Paquete DEMO
# ---------------------------------------------------------------------------
def build_demo(tmp):
    stage = os.path.join(tmp, f"Kobra_Demo_v{VERSION}")
    shutil.rmtree(stage, ignore_errors=True)

    # Dashboard offline completo (corre con doble clic, sin instalar nada)
    _copy("dashboard_estatico", os.path.join(stage, "dashboard"))
    # Reportes Excel de ejemplo
    _copy("outputs/kobra_scored.xlsx",
          os.path.join(stage, "reportes_excel", "Kobra_Cartera_Scoreada.xlsx"))
    _copy("outputs/kobra_analitica_gestion.xlsx",
          os.path.join(stage, "reportes_excel", "Kobra_Analitica_Gestion.xlsx"))
    # Presentación gerencial
    _copy("presentation/Kobra_Presentacion_Gerencial.pptx",
          os.path.join(stage, "presentacion", "Kobra_Presentacion_Gerencial.pptx"))
    # Capturas del producto completo
    for img in ("dashboard_overview.png", "dashboard_negociador.png",
                "realtime_copiloto.png", "dashboard_gestores.png"):
        _copy(f"assets/{img}", os.path.join(stage, "capturas", img))
    # Video demo del copiloto en vivo + identidad de marca
    _copy("assets/video/Kobra_Copiloto_Demo.mp4",
          os.path.join(stage, "video", "Kobra_Copiloto_Demo.mp4"))
    _copy("assets/brand/kobra.ico", os.path.join(stage, "kobra.ico"))
    _copy("assets/brand/kobra_wordmark.png",
          os.path.join(stage, "kobra_logo.png"))

    # Lanzadores
    _write(os.path.join(stage, "INICIAR_DEMO.bat"),
           "@echo off\r\n"
           "title Kobra - Demo\r\n"
           "echo Abriendo la demo de Kobra en su navegador...\r\n"
           "start \"\" \"%~dp0dashboard\\index.html\"\r\n"
           "exit\r\n")
    _write(os.path.join(stage, "iniciar_demo.sh"),
           "#!/usr/bin/env bash\n"
           "cd \"$(dirname \"$0\")\"\n"
           "xdg-open dashboard/index.html 2>/dev/null || open dashboard/index.html\n")
    # autorun.inf: solo surte efecto en CD/DVD (Windows lo bloquea en USB/carpetas
    # por seguridad desde Win7); se incluye por compatibilidad con medios ópticos.
    _write(os.path.join(stage, "autorun.inf"),
           "[autorun]\r\nopen=INICIAR_DEMO.bat\r\nicon=kobra.ico\r\n"
           "label=Kobra IA Demo\r\n")

    _write(os.path.join(stage, "LEEME.txt"), crlf=True, content=f"""KOBRA IA · DEMO v{VERSION}
Plataforma de Cobranzas Inteligentes
=====================================

CÓMO VER LA DEMO (no requiere instalar nada):

  ► Windows : doble clic en  INICIAR_DEMO.bat
  ► Mac/Linux: ejecutar      ./iniciar_demo.sh
  ► Manual  : abrir          dashboard/index.html  en cualquier navegador

QUÉ INCLUYE
  dashboard/        Dashboard interactivo offline: KPIs, filtros, gráficos,
                    cartera priorizada, export a Excel/CSV y el Copiloto de
                    Negociación (análisis de sentimiento) corriendo en su
                    navegador, sin conexión.
  video/            Video demo del Copiloto EN VIVO asesorando durante una
                    llamada (KPIs, sentimiento y próxima frase en tiempo real).
  reportes_excel/   Reportes de ejemplo listos para abrir en Excel.
  presentacion/     Presentación gerencial (PPTX).
  capturas/         Vistas del producto completo (copiloto de voz en vivo,
                    analítica de gestores, integración telefónica).
  kobra_logo.png / kobra.ico   Identidad de marca.

IMPORTANTE — HONESTIDAD DE LOS DATOS
  Esta demo usa datos 100% SINTÉTICOS (sin personas reales). Las métricas de
  impacto y de modelo son ILUSTRATIVAS de la metodología: el desempeño real
  se mide con la cartera de su empresa durante un piloto.

VERSIÓN COMPLETA
  La versión de producción agrega: modelo ProbPago entrenable con su cartera,
  copiloto de voz EN VIVO (transcripción + emoción de voz), integración con
  su central telefónica (Avaya, Genesys, Twilio…), analítica por gestor/mes
  y despliegue con Docker. Solicite el paquete "Kobra Producción".

Licencia de evaluación: ver LICENCIA.txt
""")
    _write(os.path.join(stage, "LICENCIA.txt"), LICENCIA_DEMO, crlf=True)
    _write(os.path.join(stage, "VERSION.txt"),
           f"Kobra IA Demo v{VERSION}\nDatos sintéticos · sin información personal real\n",
           crlf=True)

    os.chmod(os.path.join(stage, "iniciar_demo.sh"), 0o755)
    return _zipdir(stage, os.path.join(DIST, f"Kobra_Demo_v{VERSION}.zip"))


# ---------------------------------------------------------------------------
# Paquete PRODUCCIÓN
# ---------------------------------------------------------------------------
PROD_ITEMS = [
    "kobra", "app", "realtime", "tests", "dashboard_estatico",
    "data/generate_dataset.py", "data/generate_gestiones.py",
    "data/generate_audio_demo.py", "data/ejemplo_whatsapp.txt",
    "presentation/build_ppt.py", "assets/brand",
    "requirements.txt", "run.sh", "Dockerfile", "docker-compose.yml",
    "docker-entrypoint.sh", ".dockerignore", "README.md",
    "MANUAL_PUESTA_EN_MARCHA.md", ".github",
]


def build_prod(tmp):
    stage = os.path.join(tmp, f"Kobra_Produccion_v{VERSION}")
    shutil.rmtree(stage, ignore_errors=True)

    for item in PROD_ITEMS:
        _copy(item, os.path.join(stage, "kobra_software", item))
    # Presentación lista para usar
    _copy("presentation/Kobra_Presentacion_Gerencial.pptx",
          os.path.join(stage, "presentacion", "Kobra_Presentacion_Gerencial.pptx"))

    # Lanzador Windows: Docker si existe; si no, Python local
    _write(os.path.join(stage, "INSTALAR_Y_EJECUTAR.bat"),
           "@echo off\r\n"
           "title Kobra - Instalador\r\n"
           "cd /d \"%~dp0kobra_software\"\r\n"
           "where docker >nul 2>nul\r\n"
           "if %errorlevel%==0 (\r\n"
           "  echo [Kobra] Docker detectado. Levantando dashboard y servicio de audio...\r\n"
           "  docker compose up --build -d\r\n"
           "  echo.\r\n"
           "  echo   Dashboard:  http://localhost:8501\r\n"
           "  echo   Realtime :  http://localhost:8000\r\n"
           "  start \"\" http://localhost:8501\r\n"
           "  pause\r\n"
           "  exit /b\r\n"
           ")\r\n"
           "where python >nul 2>nul\r\n"
           "if %errorlevel%==0 (\r\n"
           "  echo [Kobra] Docker no encontrado. Instalando con Python local...\r\n"
           "  python -m pip install -r requirements.txt\r\n"
           "  python data\\generate_dataset.py --n 12000 --seed 42\r\n"
           "  python -m kobra.pipeline\r\n"
           "  start \"\" http://localhost:8501\r\n"
           "  python -m streamlit run app\\app.py\r\n"
           "  exit /b\r\n"
           ")\r\n"
           "echo [Kobra] Instale Docker Desktop (recomendado) o Python 3.11+ y reintente.\r\n"
           "pause\r\n")
    _write(os.path.join(stage, "instalar_y_ejecutar.sh"),
           "#!/usr/bin/env bash\n"
           "set -e\n"
           "cd \"$(dirname \"$0\")/kobra_software\"\n"
           "if command -v docker >/dev/null 2>&1; then\n"
           "  echo '[Kobra] Docker detectado. Levantando servicios...'\n"
           "  docker compose up --build -d\n"
           "  echo '  Dashboard:  http://localhost:8501'\n"
           "  echo '  Realtime :  http://localhost:8000'\n"
           "else\n"
           "  echo '[Kobra] Docker no encontrado. Instalación con Python local...'\n"
           "  pip3 install -r requirements.txt\n"
           "  python3 data/generate_dataset.py --n 12000 --seed 42\n"
           "  python3 -m kobra.pipeline\n"
           "  streamlit run app/app.py\n"
           "fi\n")

    _write(os.path.join(stage, "LEEME_PRIMERO.txt"), crlf=True, content=f"""KOBRA IA · PRODUCCIÓN v{VERSION}
Plataforma de Cobranzas Inteligentes
=====================================

INSTALACIÓN EN 1 PASO
  ► Windows : doble clic en  INSTALAR_Y_EJECUTAR.bat
  ► Linux/Mac: ejecutar      ./instalar_y_ejecutar.sh

  Con Docker instalado (recomendado) levanta todo solo:
    Dashboard gerencial ......... http://localhost:8501
    Copiloto de audio en vivo ... http://localhost:8000
  Sin Docker, usa Python 3.11+ local.

PRIMEROS PASOS (detalle en kobra_software/MANUAL_PUESTA_EN_MARCHA.md)
  1. Configurar API keys (una sola vez): Dashboard → pestaña Configuración.
  2. Cargar la cartera real (mismo esquema que data/generate_dataset.py)
     y correr:  python -m kobra.pipeline
  3. Conectar la central telefónica (Avaya/Genesys/Twilio):
     grabación dual-channel o streaming (SIPREC / Media Streams / DMCC)
     → ver sección "Integración con telefonía" del README.
  4. Ciclo con el CTI: GET /brief/{{id_deudor}} antes de llamar; el registro
     post-llamada alimenta la pestaña "Gestores & Evolución" con datos reales.

CONTENIDO
  kobra_software/   Código completo, tests, Docker, manual y README.
  presentacion/     Presentación gerencial (PPTX).

HONESTIDAD DE LOS DATOS
  El paquete llega con datos SINTÉTICOS de demostración. Las métricas
  ilustran la metodología; el desempeño real se mide con su cartera
  (ver README → "Honestidad de los números").

Licencia de uso: ver LICENCIA.txt
""")
    _write(os.path.join(stage, "LICENCIA.txt"), LICENCIA_PROD, crlf=True)
    _write(os.path.join(stage, "VERSION.txt"),
           f"Kobra IA Producción v{VERSION}\n", crlf=True)

    os.chmod(os.path.join(stage, "instalar_y_ejecutar.sh"), 0o755)
    sh = os.path.join(stage, "kobra_software", "run.sh")
    if os.path.exists(sh):
        os.chmod(sh, 0o755)
    ep = os.path.join(stage, "kobra_software", "docker-entrypoint.sh")
    if os.path.exists(ep):
        os.chmod(ep, 0o755)
    return _zipdir(stage, os.path.join(DIST, f"Kobra_Produccion_v{VERSION}.zip"))


def main():
    tmp = os.path.join(DIST, "_staging")
    demo = build_demo(tmp)
    prod = build_prod(tmp)
    shutil.rmtree(tmp, ignore_errors=True)

    lines = []
    for z in (demo, prod):
        mb = os.path.getsize(z) / 1e6
        digest = _sha256(z)
        lines.append(f"{digest}  {os.path.basename(z)}")
        print(f"[OK] {os.path.basename(z)}  ({mb:.1f} MB)  sha256={digest[:16]}…")
    with open(os.path.join(DIST, "SHA256SUMS.txt"), "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] Checksums: dist/SHA256SUMS.txt")


if __name__ == "__main__":
    main()
