"""El puente de licencia: lo que firma la venta (Node) lo valida la app (Python).

El bug que fija este archivo era el más caro del producto: quien PAGABA recibía
una licencia que la app rechazaba. Nadie lo veía porque cada lado estaba
probado por separado — `api/_license.test.js` verificaba el formato propio de
Node contra sí mismo, y los tests de Python verificaban JWT contra sí mismo.
Ninguno cruzaba el puente, que era justo donde estaba roto:

    Node emitía  ->  KOBRA1.<payload>.<firma>      (formato propio)
    Python leía  ->  JWT HS256                      (PyJWT)

Estos tests corren Node de verdad y le pasan el token a PyJWT. Si el puente se
vuelve a cortar —por formato, por claims o por el nombre del secreto— falla
acá, y no en la primera venta.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend_venta import licencias as klicencias  # noqa: E402

SECRETO = "secreto-compartido-entre-la-venta-y-la-app"
API = os.path.join(ROOT, "api")

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node no disponible")


def _node(script: str) -> str:
    """Corre un script Node dentro de api/ y devuelve su stdout."""
    r = subprocess.run([shutil.which("node"), "-e", script], cwd=API,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, f"node falló: {r.stderr}"
    return r.stdout.strip()


def _licencia_de_node(plan="pro", email="cliente@empresa.com", pid="12345") -> str:
    return _node(
        "const {emitirLicencia} = require('./_license');"
        f"process.stdout.write(emitirLicencia({{plan:{plan!r},pid:{pid!r},"
        f"email:{email!r}}}, {SECRETO!r}) || '');"
    )


# --- El puente, de punta a punta -------------------------------------------
def test_la_licencia_que_firma_la_venta_la_valida_la_app():
    """EL test. Node firma como en una compra real; PyJWT valida como la app."""
    token = _licencia_de_node()
    assert token, "Node no emitió licencia"
    claims = klicencias.validar_licencia(token, secreto=SECRETO)
    assert claims["plan"] == "pro"
    assert claims["sub"] == "cliente@empresa.com"


def test_la_licencia_trae_los_claims_QUE_LA_APP_LEE():
    """Segunda rotura del puente: aunque el formato coincidiera, el payload de
    Node no traía `exp` — y la app hace `claims["exp"]` para los días
    restantes, así que activar reventaba con KeyError."""
    claims = klicencias.validar_licencia(_licencia_de_node(), secreto=SECRETO)
    for clave in ("sub", "plan", "edition", "cupo_mensual", "features", "iat", "exp"):
        assert clave in claims, f"falta el claim {clave} que espera la app"
    assert claims["exp"] > claims["iat"]


def test_el_estado_de_licencia_de_la_app_acepta_la_licencia_comprada():
    """El camino real del cliente: pega la licencia y la app le dice cuántos
    días le quedan. Se ejerce la MISMA función que usa el endpoint."""
    token = _licencia_de_node(plan="basico")
    r = klicencias.licencia_activa(token, secreto=SECRETO)
    assert r["ok"], r["error"]
    # 30 días del plan básico (con margen por el segundo que corre entre medio).
    dias = (r["claims"]["exp"] - r["claims"]["iat"]) // 86400
    assert dias == 30


@pytest.mark.parametrize("plan", ["trial", "basico", "starter", "pro", "enterprise"])
def test_todos_los_planes_cruzan_el_puente(plan):
    claims = klicencias.validar_licencia(_licencia_de_node(plan=plan), secreto=SECRETO)
    assert claims["plan"] == plan
    assert claims["cupo_mensual"] == klicencias.PLANES[plan]["cupo_mensual"]
    assert claims["features"] == klicencias.PLANES[plan]["features"]


def test_un_plan_inventado_no_emite_licencia():
    """Si la metadata del pago trae un plan que no existe, es mejor no entregar
    licencia que entregar una que la app va a rechazar delante del cliente."""
    assert _licencia_de_node(plan="plan_que_no_existe") == ""


# --- Que las dos tablas de planes no se separen -----------------------------
def test_las_tablas_de_planes_no_divergen():
    """`PLANES` está escrito dos veces (JS y Python) porque los dos lenguajes
    tienen que emitir lo mismo. Este test es lo que impide que se separen: si
    alguien cambia el cupo de un plan en un solo lado, falla acá."""
    js = json.loads(_node(
        "const {PLANES} = require('./_license');"
        "process.stdout.write(JSON.stringify(PLANES));"))
    assert set(js) == set(klicencias.PLANES), "los planes no son los mismos"
    for plan, cfg_py in klicencias.PLANES.items():
        assert js[plan]["cupo_mensual"] == cfg_py["cupo_mensual"], plan
        assert js[plan]["features"] == cfg_py["features"], plan
        assert js[plan]["dias"] == cfg_py["dias"], plan


# --- Que la firma siga siendo una barrera ------------------------------------
def test_una_licencia_firmada_con_otro_secreto_no_entra():
    """Arreglar el puente no puede volverlo un colador: una licencia que no
    firmó la venta tiene que seguir siendo rechazada."""
    token = _node(
        "const {emitirLicencia} = require('./_license');"
        "process.stdout.write(emitirLicencia({plan:'pro'}, 'secreto-de-un-atacante'));")
    r = klicencias.licencia_activa(token, secreto=SECRETO)
    assert not r["ok"] and "invalida" in r["error"]


def test_no_se_puede_subir_de_plan_editando_el_payload():
    """El ataque obvio: comprar el básico y cambiar el claim a enterprise."""
    import base64
    token = _licencia_de_node(plan="basico")
    h, p, s = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(p + "=" * (-len(p) % 4)))
    payload["plan"] = "enterprise"
    p2 = base64.urlsafe_b64encode(
        json.dumps(payload).encode()).decode().rstrip("=")
    r = klicencias.licencia_activa(f"{h}.{p2}.{s}", secreto=SECRETO)
    assert not r["ok"], "se pudo cambiar el plan sin re-firmar"


def test_el_secreto_se_lee_con_cualquiera_de_los_dos_nombres():
    """Tercera rotura del puente: Vercel tiene `LICENSE_SECRET` y la app lee
    `KOBRA_LICENSE_SECRET`. Node acepta los dos, así la venta no depende de
    cuál quedó configurado."""
    for var in ("LICENSE_SECRET", "KOBRA_LICENSE_SECRET"):
        valor = _node(
            "const {secretoLicencia} = require('./_license');"
            f"process.stdout.write(secretoLicencia({{{var}: 'abc'}}) || 'NULO');")
        assert valor == "abc", f"no leyó {var}"
