# © 2026 Martín Viera. Todos los derechos reservados.

"""No se puede cobrar una feature que ningún código mira.

`backend_venta/licencias.py` y `api/_license.js` firman una lista de features
en el JWT de cada plan. El plan Enterprise otorgaba `white_label` y **ningún
archivo del producto la miraba**. Ni una línea. Aparecía solo en tests, que la
daban por buena porque comprobaban que el JWT la trajera — o sea que la suite
verificaba la factura, no el producto.

El cliente de Enterprise pagaba desde US$1.500/mes, abría el programa y veía
"MV KOBRA AI" en la barra lateral igual que todos.

(`sso`, que en la revisión figuraba en la misma bolsa, SÍ estaba implementada:
`kobra/sso_oidc.py` es un OIDC real, enganchado al login de la edición
Streamlit vía `kobra/autenticacion.py`. Lo que le falta es estar también en la
webapp React — otra cosa, y una decisión de producto, no un agujero.)

Este archivo convierte el hallazgo en falla de build: cada feature que un plan
otorga tiene que estar mirada por código de producción, no solo por la suite.
"""
import ast
import os
import pathlib
import re

import pytest

ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Dónde vive el código que DE VERDAD tiene que gatear. `tests/` afuera a
# propósito: que un test la nombre es exactamente lo que tapaba el agujero.
CODIGO = ("kobra", "webapp/backend", "realtime", "app", "backend_venta", "api")

# Features que no se gatean con `kplan.permite/exigir` porque su
# implementación es de otra naturaleza, con dónde mirar para comprobarlo.
# Cada excepción necesita una razón escrita: una lista de excepciones sin
# motivos vuelve a ser el agujero, solo que documentado.
SIN_GATE_EXPLICADAS = {
    # Vacío, y esa es la idea. Hoy TODAS las features que se venden están
    # gateadas por código de producción. Si alguna vez hace falta una
    # excepción, va acá con el motivo escrito — una lista de excepciones sin
    # razones vuelve a ser el mismo agujero, solo que documentado.
}


def features_de_los_planes() -> set:
    """Todas las features que algún plan otorga, leídas del código real."""
    fuente = (ROOT / "backend_venta" / "licencias.py").read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    encontradas = set()
    for nodo in ast.walk(arbol):
        # `"features": [*_NUCLEO, "white_label", "sso", ...]`
        if isinstance(nodo, ast.Dict):
            for clave, valor in zip(nodo.keys, nodo.values):
                if getattr(clave, "value", None) != "features":
                    continue
                for elem in getattr(valor, "elts", []):
                    if isinstance(elem, ast.Constant) and isinstance(elem.value, str):
                        encontradas.add(elem.value)
        # `_NUCLEO = ["cartera", "copiloto", "voz"]`
        if (isinstance(nodo, ast.Assign)
                and getattr(nodo.targets[0], "id", "") == "_NUCLEO"):
            for elem in getattr(nodo.value, "elts", []):
                if isinstance(elem, ast.Constant) and isinstance(elem.value, str):
                    encontradas.add(elem.value)
    assert encontradas, "no se pudo leer ninguna feature de backend_venta/licencias.py"
    return encontradas


def features_gateadas() -> set:
    """Las que el código de producción realmente mira."""
    patron = re.compile(r"(?:permite|exigir)\(\s*[\"']([a-z_]+)[\"']")
    vistas = set()
    for base in CODIGO:
        for archivo in (ROOT / base).rglob("*"):
            if archivo.suffix not in (".py", ".js", ".jsx"):
                continue
            if "node_modules" in archivo.parts or "__pycache__" in archivo.parts:
                continue
            if archivo.name.endswith((".test.js", ".test.jsx")):
                continue
            vistas |= set(patron.findall(archivo.read_text(encoding="utf-8",
                                                           errors="replace")))
    return vistas


def test_toda_feature_que_se_vende_esta_implementada():
    """El defecto exacto: Enterprise otorgaba `white_label` y `sso` y no había
    una sola línea que las mirara."""
    vendidas = features_de_los_planes()
    gateadas = features_gateadas()
    huerfanas = sorted(vendidas - gateadas - set(SIN_GATE_EXPLICADAS))
    assert not huerfanas, (
        "estos planes otorgan features que ningún código de producción mira — "
        f"se están cobrando y no existen: {huerfanas}. Implementalas, o "
        "sacalas del plan y de la landing.")


def test_las_excepciones_tienen_motivo_escrito():
    """Una lista de excepciones sin razones vuelve a ser el mismo agujero."""
    for feature, motivo in SIN_GATE_EXPLICADAS.items():
        assert motivo and len(motivo) > 10, (
            f"{feature} está exenta sin explicar por qué")


def test_la_marca_blanca_se_gatea_donde_corresponde():
    """Concretamente: `white_label` tiene que estar exigida en el endpoint que
    la configura, no solo mencionada en algún lado."""
    api = (ROOT / "webapp" / "backend" / "api.py").read_text(encoding="utf-8")
    assert 'kplan.exigir("white_label"' in api, (
        "la marca blanca no exige el plan: cualquier cliente la configura")
    # Y el que la lee NO puede exigirla: lo pide toda pantalla al abrirse, y un
    # 403 ahí dejaría la barra lateral sin nombre en los planes que no la tienen.
    bloque = api[api.index("def marca_leer"):api.index("def marca_guardar")]
    assert "kplan.exigir(" not in bloque, (
        "leer la marca exige el plan: los clientes sin Enterprise se quedan "
        "sin nombre de producto en la barra lateral")


def test_el_javascript_de_licencias_otorga_las_mismas_features():
    """`api/_license.js` (Vercel) y `backend_venta/licencias.py` (instalado)
    firman la misma licencia. Si divergen, el mismo plan da distinto según
    dónde se compró."""
    js = (ROOT / "api" / "_license.js").read_text(encoding="utf-8")
    for feature in features_de_los_planes():
        assert f'"{feature}"' in js or f"'{feature}'" in js, (
            f"{feature} la otorga el backend instalado y no el de Vercel")


@pytest.mark.parametrize("plan", ["enterprise"])
def test_enterprise_sigue_incluyendo_la_marca_blanca(plan):
    """La contracara: al arreglar esto no se puede haber sacado del plan lo que
    la landing promete."""
    from backend_venta.licencias import PLANES
    assert "white_label" in PLANES[plan]["features"]
