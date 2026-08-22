# © 2026 Martín Viera. Todos los derechos reservados.

"""Marca blanca: la feature de Enterprise que se cobraba y no existía.

`white_label` viajaba firmada en el JWT del plan Enterprise —desde
US$1.500/mes— y ningún código del producto la miraba. El cliente abría el
programa y veía "MV KOBRA AI" en la barra lateral igual que todos.

Lo que se prueba acá, además de que ahora funcione:

  * **El logo es una vía de XSS con permanencia.** Entra como data URI y sale
    renderizado en un `<img>` de todas las pantallas. Un
    `data:text/html;base64,...` ahí adentro lo escribe un admin una vez y lo
    ejecuta cada gestor, cada vez que abre el programa. SVG queda afuera por
    lo mismo: puede traer `<script>` adentro.
  * **Una licencia que se degradó no puede seguir mostrando la marca.** Si un
    cliente pasa de Enterprise a Pro, seguir pintando su logo es seguir
    entregando la feature después de que dejó de pagarla.
  * **Leer la marca no puede exigir el plan.** Lo pide toda pantalla al
    abrirse; un 403 ahí deja sin nombre de producto a los planes que no la
    tienen, que son casi todos.
"""
import pytest

from kobra import marca_blanca as km

BUENA = {"nombre": "Cobranzas del Plata", "color": "#1B4D3E",
         "logo": "data:image/png;base64,iVBORw0KGgo="}


@pytest.fixture(autouse=True)
def _config_aislada(tmp_path, monkeypatch):
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path))
    import importlib

    from kobra import config as kconfig
    importlib.reload(kconfig)
    yield
    importlib.reload(kconfig)


@pytest.fixture()
def con_enterprise(monkeypatch):
    from kobra import plan as kplan
    monkeypatch.setattr(kplan, "permite", lambda f: True)


# ---------------------------------------------------------------------------
# 1) El logo no puede ser un vector de ejecución
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("logo", [
    "data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
    "data:image/svg+xml;base64,PHN2Zz48c2NyaXB0PmFsZXJ0KDEpPC9zY3JpcHQ+PC9zdmc+",
    "javascript:alert(1)",
    "data:application/javascript;base64,YWxlcnQoMSk=",
    "<img src=x onerror=alert(1)>",
    "https://atacante.com/logo.png",     # tampoco: sale un pedido a un tercero
])
def test_el_logo_no_puede_traer_codigo(logo):
    """Lo escribe un admin una vez y lo ve cada gestor, todos los días."""
    with pytest.raises(km.MarcaInvalida):
        km.validar({**BUENA, "logo": logo})


def test_el_svg_no_se_acepta_aunque_sea_una_imagen():
    """Un SVG puede traer `<script>` adentro: como data URI en un `<img>` es
    una vía de ejecución más, no un formato de logo más."""
    assert "image/svg+xml" not in km.TIPOS_LOGO
    with pytest.raises(km.MarcaInvalida):
        km.validar({**BUENA, "logo": "data:image/svg+xml;base64,PHN2Zy8+"})


@pytest.mark.parametrize("tipo", ["png", "jpeg", "webp", "gif"])
def test_los_formatos_de_imagen_normales_sí_entran(tipo):
    m = km.validar({**BUENA, "logo": f"data:image/{tipo};base64,iVBORw0KGgo="})
    assert m["logo"].startswith(f"data:image/{tipo}")


def test_un_logo_enorme_se_rechaza_con_un_motivo_util():
    """Viaja en cada respuesta de /api/marca. Y el mensaje tiene que decir qué
    hacer, no solo que está mal."""
    gigante = "data:image/png;base64," + "A" * km.MAX_LOGO
    with pytest.raises(km.MarcaInvalida) as e:
        km.validar({**BUENA, "logo": gigante})
    assert "128" in str(e.value), "no dice qué tamaño sí sirve"


# ---------------------------------------------------------------------------
# 2) Nombre y color
# ---------------------------------------------------------------------------
def test_sin_nombre_no_se_guarda_nada():
    with pytest.raises(km.MarcaInvalida):
        km.validar({"nombre": "   ", "logo": "", "color": ""})


def test_el_nombre_no_puede_romper_el_layout():
    """Va a un `<b>` y a un `<title>`: un salto de línea ahí rompe la barra
    lateral sin avisar."""
    m = km.validar({**BUENA, "nombre": "Cobranzas\n\tdel  Plata\r\n"})
    assert m["nombre"] == "Cobranzas del Plata"


def test_el_nombre_se_recorta():
    m = km.validar({**BUENA, "nombre": "X" * 500})
    assert len(m["nombre"]) == km.MAX_NOMBRE


@pytest.mark.parametrize("color", ["#1B4D3E", "#1B4", "#abc", "#ABCDEF", ""])
def test_los_colores_validos_pasan(color):
    assert km.validar({**BUENA, "color": color})["color"] == color


@pytest.mark.parametrize("color", [
    "rojo", "#12345", "rgb(1,2,3)", "#GGGGGG",
    "red; background:url(javascript:alert(1))",
])
def test_un_color_que_no_es_un_color_se_rechaza(color):
    """El valor va a un `style` inline: dejar pasar texto arbitrario ahí es
    inyección de CSS."""
    with pytest.raises(km.MarcaInvalida):
        km.validar({**BUENA, "color": color})


# ---------------------------------------------------------------------------
# 3) El plan manda
# ---------------------------------------------------------------------------
def test_sin_enterprise_se_ve_la_marca_de_fabrica(monkeypatch):
    from kobra import plan as kplan
    monkeypatch.setattr(kplan, "permite", lambda f: True)
    km.guardar(BUENA)
    assert km.leer()["nombre"] == BUENA["nombre"]

    # El cliente se degrada de Enterprise a Pro.
    monkeypatch.setattr(kplan, "permite", lambda f: f != "white_label")
    vista = km.leer()
    assert vista["nombre"] == "MV Kobra AI", (
        "sigue mostrando la marca del cliente después de que dejó de pagarla")
    assert vista["propia"] is False
    assert vista["logo"] == ""


def test_con_enterprise_pero_sin_configurar_tambien_es_la_de_fabrica(con_enterprise):
    assert km.leer() == km.DEFECTO


def test_guardar_y_leer_devuelve_lo_mismo(con_enterprise):
    guardada = km.guardar(BUENA)
    leida = km.leer()
    for campo in ("nombre", "color", "logo"):
        assert leida[campo] == guardada[campo] == BUENA[campo]
    assert leida["propia"] is True


def test_se_puede_volver_atras(con_enterprise):
    km.guardar(BUENA)
    assert km.borrar() == km.DEFECTO
    assert km.leer() == km.DEFECTO


def test_una_marca_invalida_no_pisa_la_que_estaba(con_enterprise):
    """No se guarda a medias: si el logo nuevo no pasa, la marca anterior
    sigue en pie."""
    km.guardar(BUENA)
    with pytest.raises(km.MarcaInvalida):
        km.guardar({**BUENA, "nombre": "Otro", "logo": "javascript:alert(1)"})
    assert km.leer()["nombre"] == BUENA["nombre"]


# ---------------------------------------------------------------------------
# 4) Lo que NO se marca blanca, a propósito
# ---------------------------------------------------------------------------
def test_la_marca_blanca_no_borra_de_donde_salio_el_producto():
    """Marca blanca en un producto vendido significa que la HERRAMIENTA se ve
    del cliente —lo que ve su equipo— no que se borre el rastro de quién lo
    fabricó. Si esto cambia, que sea una decisión, no un descuido."""
    doc = km.__doc__
    assert "landing" in doc and "instalador" in doc, (
        "no queda escrito qué NO alcanza la marca blanca")


# ---------------------------------------------------------------------------
# 5) Contra la API real: es ahí donde el gateo cuenta
# ---------------------------------------------------------------------------
SECRETO_API = "secreto-de-prueba-marca-blanca"
_RECARGABLES = ("kobra.config", "kobra.rutas", "kobra.edicion", "kobra.plan",
                "kobra.marca_blanca", "webapp.backend.api")


def _montar(tmp_path, monkeypatch, plan):
    import importlib
    import sys
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("KOBRA_LICENSE_SECRET", SECRETO_API)
    monkeypatch.setenv("KOBRA_MODO_STANDALONE", "1")
    monkeypatch.delenv("KOBRA_OWNER", raising=False)
    for nombre in _RECARGABLES:
        if sys.modules.get(nombre) is not None:
            importlib.reload(sys.modules[nombre])

    from backend_venta import licencias as klic
    from kobra import config as kconfig
    kconfig.guardar_extra("LICENCIA_TOKEN",
                          klic.emitir_licencia("cliente-marca", plan,
                                               secreto=SECRETO_API))
    from webapp.backend import api
    importlib.reload(api)
    return api


def _cliente(api, rol="admin"):
    from fastapi.testclient import TestClient
    cli = TestClient(api.app)
    cli.headers.update({
        "Authorization": f"Bearer {api._emitir_token(rol, api.EMPRESA_DEFAULT)}"})
    return cli


@pytest.fixture(autouse=True)
def _devolver_los_modulos(monkeypatch):
    """Recargar módulos con el entorno del test los deja apuntando a la
    carpeta temporal, y `monkeypatch` no deshace un `reload`."""
    yield
    import importlib
    import sys
    monkeypatch.undo()
    for nombre in _RECARGABLES:
        if sys.modules.get(nombre) is not None:
            importlib.reload(sys.modules[nombre])


def test_un_plan_sin_enterprise_no_puede_configurarla(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    api = _montar(tmp_path, monkeypatch, "pro")
    cli = _cliente(api)
    r = cli.post("/api/marca", json=BUENA)
    assert r.status_code == 403
    assert r.json()["motivo"] == "feature_no_incluida"


def test_pero_sí_puede_LEER_la_marca(tmp_path, monkeypatch):
    """Lo pide toda pantalla al abrirse: un 403 acá deja la barra lateral sin
    nombre de producto en los planes que no tienen la feature, que son casi
    todos."""
    pytest.importorskip("fastapi")
    api = _montar(tmp_path, monkeypatch, "pro")
    cli = _cliente(api)
    r = cli.get("/api/marca")
    assert r.status_code == 200
    assert r.json()["nombre"] == "MV Kobra AI"
    assert r.json()["propia"] is False


def test_enterprise_la_configura_y_queda(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli = _cliente(api)
    assert cli.post("/api/marca", json=BUENA).status_code == 200
    visto = cli.get("/api/marca").json()
    assert visto["nombre"] == BUENA["nombre"] and visto["propia"] is True


def test_un_gestor_no_le_cambia_la_marca_a_toda_la_empresa(tmp_path, monkeypatch):
    """`solo_admin` no es decorativo: esto cambia lo que ve todo el equipo, y
    el logo queda embebido en cada pantalla."""
    pytest.importorskip("fastapi")
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli = _cliente(api, rol="gestor")
    assert cli.post("/api/marca", json=BUENA).status_code == 403
    assert cli.delete("/api/marca").status_code == 403


def test_un_logo_con_codigo_lo_rechaza_la_API_tambien(tmp_path, monkeypatch):
    """La validación no puede vivir solo en la pantalla: el endpoint es lo que
    de verdad protege."""
    pytest.importorskip("fastapi")
    api = _montar(tmp_path, monkeypatch, "enterprise")
    cli = _cliente(api)
    r = cli.post("/api/marca", json={**BUENA, "logo": "javascript:alert(1)"})
    assert r.status_code == 400
    assert "SVG" in r.json()["detail"] or "base64" in r.json()["detail"]


def test_sin_sesion_no_se_lee_ni_se_escribe(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    api = _montar(tmp_path, monkeypatch, "enterprise")
    anon = TestClient(api.app)
    assert anon.get("/api/marca").status_code == 401
    assert anon.post("/api/marca", json=BUENA).status_code == 401
