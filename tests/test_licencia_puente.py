"""
El puente entre el checkout web (Node) y la app instalada (Python).

Por qué existe este archivo: `api/_license.js` emitía un formato propio
("KOBRA1.<body>.<sig>") que `backend_venta/licencias.py` — que es lo que corre
en la máquina del cliente — era incapaz de leer. Cada lado tenía sus tests, cada
lado pasaba en verde, y aun así un cliente que pagaba US$ 690 pegaba su licencia
y recibía "Licencia inválida". El bug vivía exactamente en el hueco entre las
dos suites.

Estos tests cruzan el hueco: emiten con el JS real y validan con el Python real.
Si alguien vuelve a cambiar el formato de un solo lado, esto se pone en rojo.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

import pytest

from backend_venta import licencias

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETO = "secreto-compartido-de-prueba-0123456789abcdef"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="requiere Node para ejecutar el emisor real del checkout",
)


def emitir_con_el_checkout(datos: dict, secreto: str = SECRETO, ahora=None) -> str:
    """
    Emite una licencia con el MISMO módulo que corre en Vercel.

    Se usa `emitirLicencia` a propósito, no `sign`: `sign` es el firmador JWT
    crudo, y quien arma los claims de una compra (sub, edition, cupo_mensual,
    features, exp) es `emitirLicencia`. Probar `sign` no probaría lo que
    realmente recibe el cliente.
    """
    argumento_ahora = "" if ahora is None else f", {int(ahora)}"
    r = subprocess.run(
        [
            "node", "-e",
            'const {emitirLicencia} = require("./api/_license");'
            'const lic = emitirLicencia(JSON.parse(process.argv[1]), '
            f'process.env.KOBRA_LICENSE_SECRET{argumento_ahora});'
            'process.stdout.write(lic === null ? "" : lic);',
            json.dumps(datos),
        ],
        cwd=ROOT, capture_output=True, text=True,
        env={**os.environ, "KOBRA_LICENSE_SECRET": secreto, "LICENSE_SECRET": secreto},
    )
    assert r.returncode == 0, f"el emisor falló: {r.stderr}"
    return r.stdout.strip()


@pytest.mark.parametrize("plan", sorted(licencias.PLANES))
def test_la_app_acepta_la_licencia_que_emite_el_checkout(plan):
    """Cada plan del catálogo: se emite en JS y la app lo valida."""
    lic = emitir_con_el_checkout({"plan": plan, "pid": "123", "email": "cliente@ejemplo.com"})
    r = licencias.licencia_activa(lic, SECRETO)
    assert r["ok"], f"la app rechazó una licencia legítima del plan {plan}: {r['error']}"


@pytest.mark.parametrize("plan", sorted(licencias.PLANES))
def test_cupo_y_features_coinciden_con_el_catalogo_de_la_app(plan):
    """
    Un JWT bien firmado pero con otro cupo pasaría la validación y recién
    rompería después, en el gateway. Los dos catálogos tienen que coincidir.
    """
    lic = emitir_con_el_checkout({"plan": plan, "pid": "123"})
    claims = licencias.licencia_activa(lic, SECRETO)["claims"]
    esperado = licencias.PLANES[plan]
    assert claims["cupo_mensual"] == esperado["cupo_mensual"]
    assert claims["features"] == esperado["features"]
    assert claims["plan"] == plan


def test_los_planes_vendidos_son_licenciables():
    """
    Todo plan que el checkout sepa cobrar tiene que existir en el catálogo de
    licencias. Si no, se cobra y después no se puede emitir nada.
    """
    r = subprocess.run(
        ["node", "-e",
         'const s=require("fs").readFileSync("./api/checkout.js","utf8");'
         'const m=s.match(/const PLANS = \\{([\\s\\S]*?)\\};/);'
         'process.stdout.write(JSON.stringify([...m[1].matchAll(/^\\s*(\\w+)\\s*:/gm)].map(x=>x[1])));'],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    planes_cobrables = json.loads(r.stdout)
    assert planes_cobrables, "no se pudieron leer los planes del checkout"
    faltantes = [p for p in planes_cobrables if p not in licencias.PLANES]
    assert not faltantes, f"el checkout cobra planes que no se pueden licenciar: {faltantes}"


def test_un_plan_fuera_del_catalogo_no_emite_licencia():
    """
    Mejor no entregar licencia que entregar una que la app rechaza delante del
    cliente. `emitirLicencia` devuelve null, que acá llega como cadena vacía.
    """
    assert emitir_con_el_checkout({"plan": "inventado", "pid": "1"}) == ""


def test_la_app_rechaza_una_licencia_firmada_con_otro_secreto():
    lic = emitir_con_el_checkout({"plan": "pro", "pid": "1"}, secreto="un-secreto-que-no-es-el-de-la-app")
    r = licencias.licencia_activa(lic, SECRETO)
    assert not r["ok"]


def test_la_app_rechaza_una_licencia_adulterada():
    lic = emitir_con_el_checkout({"plan": "basico", "pid": "1"})
    header, payload, firma = lic.split(".")
    adulterada = f"{header}.{payload}.{'A' * len(firma)}"
    assert not licencias.licencia_activa(adulterada, SECRETO)["ok"]


def test_la_app_rechaza_una_licencia_vencida():
    import time
    # `exp` sale de iat + dias del plan, así que para tener una vencida se emite
    # con un `ahora` lo bastante viejo como para que ya haya expirado.
    dias = licencias.PLANES["pro"]["dias"]
    hace_mucho = int(time.time()) - (dias + 1) * 24 * 3600
    lic = emitir_con_el_checkout({"plan": "pro", "pid": "1"}, ahora=hace_mucho)
    r = licencias.licencia_activa(lic, SECRETO)
    assert not r["ok"]
    assert r["error"] == "licencia_expirada"
