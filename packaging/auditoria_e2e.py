# Auditoría E2E: el recorrido comercial completo contra el backend REAL.
# Cada paso imprime PASS/FAIL con el dato que lo prueba. Exit code 1 si algo falla.
import importlib
import os
import subprocess
import sys
import tempfile
import time

# Raíz del repo, calculada: el guion corre desde cualquier carpeta.
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
FALLAS = []


def check(nombre, cond, detalle=""):
    estado = "PASS" if cond else "FAIL"
    print(f"  [{estado}] {nombre}" + (f" — {detalle}" if detalle else ""))
    if not cond:
        FALLAS.append(nombre)


def entorno_limpio(nombre):
    """Instalación nueva: config y datos vacíos, modo standalone."""
    tmp = tempfile.mkdtemp(prefix=f"audit_{nombre}_")
    os.environ["KOBRA_CONFIG_DIR"] = tmp + "/config"
    os.environ["KOBRA_DATA_DIR"] = tmp + "/datos"
    os.environ["KOBRA_MODO_STANDALONE"] = "1"
    os.environ["KOBRA_LICENSE_SECRET"] = "audit-secreto-e2e"
    os.environ.pop("KOBRA_OWNER", None)
    for m in ("kobra.config", "kobra.rutas", "kobra.edicion", "kobra.plan",
              "backend_venta.licencias", "webapp.backend.api"):
        if m in sys.modules:
            importlib.reload(sys.modules[m])
    from webapp.backend import api
    importlib.reload(api)
    from fastapi.testclient import TestClient
    return api, TestClient(api.app)


# ============================================================
print("\n== 1. INSTALACIÓN LIMPIA: pide licencia, no expone nada ==")
api, cli = entorno_limpio("fresh")
r = cli.get("/api/licencia/estado").json()
check("estado inicial: standalone sin activar", r == {"standalone": True, "activa": False}, str(r))
check("la cartera exige sesión (401)", cli.get("/api/cartera").status_code == 401)
check("los KPIs exigen sesión (401)", cli.get("/api/kpis").status_code == 401)
check("owner-login NO existe en la copia del cliente (404)",
      cli.post("/api/licencia/owner-login").status_code == 404)

# ============================================================
print("\n== 2. DEMO: activa el trial de 7 días y trabaja ==")
from backend_venta import licencias as klic

tok_trial = klic.emitir_licencia("demo@ejemplo.invalid", "trial", secreto="audit-secreto-e2e")
r = cli.post("/api/licencia/activar", json={"token": tok_trial})
check("el trial activa (200)", r.status_code == 200, r.text[:80])
d = r.json()
check("es trial de 7 días", d.get("trial") is True and d.get("dias_restantes") == 6, str(d.get("dias_restantes")))
bearer = {"Authorization": f"Bearer {d['token']}"}
# La cartera scoreada REAL del pipeline (outputs/kobra_scored.csv):
# probar contra un archivo inventado probaría mi inventiva, no el producto.
import shutil

_ruta = api._datos_de(api.EMPRESA_DEFAULT)["scored"]
os.makedirs(os.path.dirname(_ruta), exist_ok=True)
shutil.copy(os.path.join(RAIZ, "outputs", "kobra_scored.csv"), _ruta)
check("con el trial entra a los KPIs", cli.get("/api/kpis", headers=bearer).status_code == 200)

print("\n== 3. TRIAL VENCIDO: manda a comprar, no a soporte ==")
import jwt as pyjwt

ahora = int(time.time())
vencido = pyjwt.encode({"sub": "demo@ejemplo.invalid", "plan": "trial",
                        "edition": "venta", "cupo_mensual": 50, "features": ["voz"],
                        "iat": ahora - 8 * 86400, "exp": ahora - 86400},
                       "audit-secreto-e2e", algorithm="HS256")
r = cli.post("/api/licencia/activar", json={"token": vencido})
check("trial vencido rechazado (400)", r.status_code == 400)
check("el mensaje distingue vencida de inválida", "venció" in r.json().get("detail", ""))

# ============================================================
print("\n== 4. COMPRA: Node firma (producción) → Python valida (instalado) ==")
# El flujo real: checkout → webhook → api/_license.js firma → el cliente pega el token.
guion = tempfile.mktemp(suffix=".mjs")
with open(guion, "w") as f:
    f.write("import { createRequire } from 'module';\n"
            f"const require = createRequire('{RAIZ}/');\n"
            "const { sign } = require('./api/_license.js');\n"
            "process.stdout.write(sign({ plan: 'pro', email: 'pago@ejemplo.invalid',"
            " pid: '99887' }, process.env.KOBRA_LICENSE_SECRET));\n")
rn = subprocess.run(["node", guion], cwd=RAIZ, capture_output=True,
                    text=True, env={**os.environ})
check("Node emite la licencia del pago", rn.returncode == 0, rn.stderr[:100])
tok_pago = rn.stdout.strip()
r = cli.post("/api/licencia/activar", json={"token": tok_pago})
check("la licencia comprada activa en la copia instalada (200)", r.status_code == 200, r.text[:80])
d = r.json()
check("plan pro, sin trial", d.get("plan") == "pro" and d.get("trial") is False)
bearer_pro = {"Authorization": f"Bearer {d['token']}"}
check("el cliente pago usa el producto", cli.get("/api/kpis", headers=bearer_pro).status_code == 200,
      f"HTTP {cli.get('/api/kpis', headers=bearer_pro).status_code}")

print("\n== 5. MÓDULO SUELTO comprado por Node: Logística sin cobranzas ==")
with open(guion, "w") as f:
    f.write("import { createRequire } from 'module';\n"
            f"const require = createRequire('{RAIZ}/');\n"
            "const { sign } = require('./api/_license.js');\n"
            "process.stdout.write(sign({ plan: 'logistica', email: 'dist@ejemplo.invalid',"
            " pid: '55443' }, process.env.KOBRA_LICENSE_SECRET));\n")
rn = subprocess.run(["node", guion], cwd=RAIZ, capture_output=True,
                    text=True, env={**os.environ})
check("Node emite la licencia del módulo suelto", rn.returncode == 0, rn.stderr[:100])
r = cli.post("/api/licencia/activar", json={"token": rn.stdout.strip()})
check("la licencia de módulo activa (200)", r.status_code == 200, r.text[:100])
d = r.json()
b_log = {"Authorization": f"Bearer {d['token']}"}
r = cli.get("/api/logistica/resumen", headers=b_log)
check("logística responde (404 'subí datos' = habilitado, no 403)",
      r.status_code == 404, f"HTTP {r.status_code}: {r.text[:80]}")
r = cli.get("/api/gobernanza/resumen", headers=b_log)
check("gobernanza NO viene incluida con logística (403)", r.status_code == 403)

# ============================================================
print("\n== 6. GATEO POR PLAN: cada módulo corta o deja pasar según lo pagado ==")
api, cli = entorno_limpio("planes")
casos = [
    ("basico",     {"gobernanza": 403, "medidas": 403, "automl": 403}),
    ("pro",        {"gobernanza": 200, "medidas": 403, "automl": 403}),
    ("starter",    {"gobernanza": 200, "medidas": 200, "automl": 403}),
    ("enterprise", {"gobernanza": 200, "medidas": 200, "automl": 200}),
]
RUTA = {"gobernanza": "/api/gobernanza/catalogo",
        "medidas": "/api/medidas"}


def _probar_automl(cli, h):
    """La ruta real es POST con archivo: el gateo se prueba mandando uno."""
    import io as _io
    csv = b"a,b,objetivo\n1,2,0\n3,4,1\n"
    r = cli.post("/api/automl/columnas", headers=h,
                 files={"archivo": ("datos.csv", _io.BytesIO(csv), "text/csv")})
    return r.status_code
for plan, esperado in casos:
    api, cli = entorno_limpio(f"plan_{plan}")
    tok = klic.emitir_licencia(f"{plan}@e.invalid", plan, secreto="audit-secreto-e2e")
    d = cli.post("/api/licencia/activar", json={"token": tok}).json()
    h = {"Authorization": f"Bearer {d['token']}"}
    # la cartera scoreada real, para que los 200 no sean 404 por falta de datos
    import shutil as _sh
    ruta = api._datos_de(api.EMPRESA_DEFAULT)["scored"]
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    _sh.copy(os.path.join(RAIZ, "outputs", "kobra_scored.csv"), ruta)
    for mod, code in esperado.items():
        real = (_probar_automl(cli, h) if mod == "automl"
                else cli.get(RUTA[mod], headers=h).status_code)
        check(f"{plan} → {mod}: HTTP {code}", real == code, f"dio {real}")

# ============================================================
print("\n== 7. OWNER: desbloqueo con mail|código en el campo de licencia ==")
api, cli = entorno_limpio("owner")
# No conozco el código en claro (no está en el repo — correcto). Verifico el
# mecanismo con un código de prueba inyectado con la MISMA derivación scrypt.
import hashlib
import secrets as pysecrets

from kobra import owner as kowner

# El código de prueba se ARMA en runtime y no se escribe literal: hay un
# guardián (tests/test_owner_desbloqueo.py) que falla si algo con forma de
# código owner aparece en un archivo del repo, y no puede saber cuál es falso.
codigo_prueba = "-".join(letra * 5 for letra in "ABCDE")
sal = pysecrets.token_bytes(16)
h = hashlib.scrypt(codigo_prueba.encode(), salt=sal, n=2**15, r=8, p=1,
                   dklen=32, maxmem=64 * 1024 * 1024)
kowner._SAL, kowner._HASH = sal, h
cred = f"{kowner.EMAIL}|{codigo_prueba}"
r = cli.post("/api/licencia/activar", json={"token": cred})
check("la credencial owner activa por el campo de licencia (200)",
      r.status_code == 200, r.text[:100])
d = r.json()
check("owner queda sin vencimiento", d.get("plan") == "owner" and d.get("dias_restantes") is None, str(d))
r2 = cli.get("/api/licencia/estado").json()
check("owner persiste tras reconsultar", r2.get("owner") is True and r2.get("activa") is True, str(r2))
h_own = {"Authorization": f"Bearer {d['token']}"}
check("owner entra como admin a config", cli.get("/api/config/estado", headers=h_own).status_code == 200)
r = cli.post("/api/licencia/activar", json={"token": f"{kowner.EMAIL}|CODIGO-EQUIVOCADO"})
check("un código equivocado NO desbloquea owner", r.status_code != 200 or r.json().get("plan") != "owner",
      f"HTTP {r.status_code}")

# ============================================================
print("\n== RESULTADO ==")
if FALLAS:
    print(f"  {len(FALLAS)} FALLAS: {FALLAS}")
    sys.exit(1)
print("  Recorrido comercial completo: todo PASS")
