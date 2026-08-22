# © 2026 Martín Viera. Todos los derechos reservados.

"""El multi-tenant aísla de verdad: la empresa es parte de la credencial.

La contraseña se guardaba SOLO por rol (`AUTH_ADMIN_HASH`), compartida por
todo el despliegue, y el login tomaba el nombre de empresa del CUERPO del
pedido. Las dos cosas juntas hacían que el aislamiento no existiera: con la
contraseña del cliente A y `empresa: "clienteB"` se emitía un token de B y se
leía su cartera entera —deudores, montos, teléfonos y probabilidad de pago—.

No era un descuido: el docstring de `/api/tenant/alta` decía "login con la
misma contraseña + nombre de empresa". Estaba diseñado así.
"""
import os
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.fixture()
def dos_clientes(monkeypatch):
    """Dos empresas con cartera propia y contraseña propia."""
    pytest.importorskip("fastapi")
    base = tempfile.mkdtemp()
    monkeypatch.setenv("KOBRA_DATA_DIR", base)
    monkeypatch.setenv("KOBRA_CONFIG_DIR", os.path.join(base, "cfg"))
    monkeypatch.delenv("KOBRA_MODO_STANDALONE", raising=False)
    monkeypatch.delenv("KOBRA_OWNER", raising=False)

    # Los módulos se reimportan para que tomen este KOBRA_DATA_DIR, pero se
    # GUARDAN antes y se restauran al final. Dejarlos borrados le pasa a los
    # tests siguientes módulos que apuntan a un directorio temporal ya
    # eliminado: pasan solos y fallan en la suite completa. Pasó de verdad —
    # tres tests de audio se cayeron solo cuando corrían después de este.
    previos = {k: v for k, v in sys.modules.items()
               if k.startswith(("kobra", "webapp"))}
    for m in previos:
        del sys.modules[m]

    for emp, deudor, monto in (("cliente-a", "A-001", 111111),
                               ("cliente-b", "B-999", 999999)):
        d = os.path.join(base, "data", "tenants", emp)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "kobra_scored.csv"), "w", encoding="utf-8") as f:
            f.write("id_deudor,segmento,monto_deuda,dias_mora,"
                    "cuotas_atrasadas,probpago\n")
            f.write(f"{deudor},Retail,{monto},60,2,0.7\n")

    from fastapi.testclient import TestClient

    from kobra import autenticacion as kauth
    from webapp.backend import api
    kauth.establecer_password("admin", "clave-de-A", empresa="cliente-a")
    kauth.establecer_password("admin", "clave-de-B", empresa="cliente-b")
    yield api, TestClient(api.app)
    for m in [k for k in sys.modules if k.startswith(("kobra", "webapp"))]:
        del sys.modules[m]
    sys.modules.update(previos)


def _cartera(cli, token):
    r = cli.get("/api/cartera", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    filas = r.json().get("filas") or r.json().get("items") or []
    return [f.get("id_deudor") for f in filas]


def test_la_clave_de_un_cliente_no_abre_la_empresa_de_otro(dos_clientes):
    """EL bug. Con la clave propia y el nombre del vecino se leía su cartera."""
    _api, cli = dos_clientes
    r = cli.post("/api/auth/login",
                 json={"password": "clave-de-A", "empresa": "cliente-b"})
    assert r.status_code == 401, (
        "la contraseña de un cliente sigue abriendo la empresa de otro: "
        "eso es la cartera del competidor")


def test_cada_cliente_ve_su_propia_cartera(dos_clientes):
    """El candado no puede volverse un muro para el uso legítimo."""
    _api, cli = dos_clientes
    a = cli.post("/api/auth/login",
                 json={"password": "clave-de-A", "empresa": "cliente-a"})
    b = cli.post("/api/auth/login",
                 json={"password": "clave-de-B", "empresa": "cliente-b"})
    assert a.status_code == 200 and b.status_code == 200
    assert _cartera(cli, a.json()["token"]) == ["A-001"]
    assert _cartera(cli, b.json()["token"]) == ["B-999"]


def test_una_empresa_inexistente_da_401_y_no_409(dos_clientes):
    """Distinguir "no existe" de "clave incorrecta" convierte el login en un
    enumerador de clientes: con 401 en los dos casos, no se puede averiguar
    quién más está en el despliegue."""
    _api, cli = dos_clientes
    r = cli.post("/api/auth/login",
                 json={"password": "cualquiera", "empresa": "no-existe-esta"})
    assert r.status_code == 401


def test_el_nombre_de_empresa_no_puede_fabricar_otra_clave(monkeypatch):
    """El nombre entra en el nombre de una clave de configuración. Sin
    normalizar, `admin` de una empresa podría pisar la credencial de otra."""
    base = tempfile.mkdtemp()
    monkeypatch.setenv("KOBRA_CONFIG_DIR", os.path.join(base, "cfg"))
    previos = {k: v for k, v in sys.modules.items() if k.startswith("kobra")}
    for m in previos:
        del sys.modules[m]
    try:
        from kobra import autenticacion as kauth
        kauth.establecer_password("admin", "clave-1", empresa="acme")
        # Variantes que apuntan al mismo tenant lógico no pueden divergir…
        assert kauth.verificar_password("admin", "clave-1", empresa="ACME")
        assert kauth.verificar_password("admin", "clave-1", empresa=" acme ")
        # …y una empresa distinta no comparte credencial.
        assert not kauth.verificar_password("admin", "clave-1", empresa="acme-2")
    finally:
        for m in [k for k in sys.modules if k.startswith("kobra")]:
            del sys.modules[m]
        sys.modules.update(previos)


def test_la_instalacion_de_un_solo_cliente_sigue_igual(monkeypatch):
    """`principal` conserva las claves SIN prefijo: ninguna instalación
    existente se queda afuera por este cambio."""
    base = tempfile.mkdtemp()
    monkeypatch.setenv("KOBRA_CONFIG_DIR", os.path.join(base, "cfg"))
    previos = {k: v for k, v in sys.modules.items() if k.startswith("kobra")}
    for m in previos:
        del sys.modules[m]
    try:
        from kobra import autenticacion as kauth
        from kobra import config as kconfig
        kauth.establecer_password("admin", "la-de-siempre")
        assert kconfig.leer_extra("AUTH_ADMIN_HASH"), \
            "cambió el nombre de la clave: las instalaciones ya hechas no entrarían"
        assert kauth.verificar_password("admin", "la-de-siempre")
        assert kauth.login("la-de-siempre") == "admin"
    finally:
        for m in [k for k in sys.modules if k.startswith("kobra")]:
            del sys.modules[m]
        sys.modules.update(previos)
