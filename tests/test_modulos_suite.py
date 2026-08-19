# © 2026 Martín Viera. Todos los derechos reservados.

"""Los módulos de la suite: qué habilita cada plan y qué corta.

Kobra pasa de ser un producto único a una suite con precio escalable. Sobre el
núcleo de cobranzas se enchufan tres módulos que se venden aparte —gobernanza
de datos, medidas calculadas (dax) y automl—, y de cuáles incluye cada plan
sale la escalera de precios.

Lo que se prueba acá es el contrato comercial, que es lo que se puede romper
sin que nadie se entere:

  * que un plan más caro nunca incluya menos módulos que uno más barato,
  * que los planes de entrada NO los tengan (si los tuvieran, no habría
    escalera y el precio dejaría de ser escalable),
  * que un módulo no incluido efectivamente CORTE la acción, en vez de dejarla
    pasar — que es el modo de fallar que ya tuvo este repo: durante un tiempo
    la licencia viajaba firmada con las features y la app instalada no las
    miraba, así que un cliente de Básico recibía lo mismo que uno de Pro.

No se prueba acá que los módulos hagan lo suyo: todavía no están portados
(ver docs/PLAN_SUITE_KOBRA.md). Esto cubre el gateo, que es lo que ya existe.
"""
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend_venta import licencias as klicencias  # noqa: E402

SECRETO = "secreto-de-prueba-para-los-modulos-de-la-suite"


def _plan_activo(tmp_path, monkeypatch, plan, features=None):
    """Una copia instalada con la licencia de `plan` ya activada.

    Mismo montaje que tests/test_plan_diferenciado.py::_entorno — la clave de
    configuración es `LICENCIA_TOKEN`, y hay que recargar también `rutas` y
    `edicion` porque leen las variables de entorno al importarse.
    """
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.setenv("KOBRA_LICENSE_SECRET", SECRETO)
    monkeypatch.delenv("KOBRA_OWNER", raising=False)

    from kobra import config as kconfig
    importlib.reload(kconfig)
    from kobra import rutas as krutas
    importlib.reload(krutas)
    from kobra import edicion as kedicion
    importlib.reload(kedicion)
    from kobra import plan as kplan
    importlib.reload(kplan)

    token = klicencias.emitir_licencia("cliente-test", plan,
                                       features=features, secreto=SECRETO)
    kconfig.guardar_extra("LICENCIA_TOKEN", token)
    return kplan


def test_los_tres_modulos_estan_declarados():
    """`MODULOS` es el único lugar donde se listan. Si se agrega uno al plan y
    no acá, `kobra/plan.py` no lo puede distinguir del núcleo."""
    assert set(klicencias.MODULOS) == {"gobernanza", "dax", "automl"}


@pytest.mark.parametrize("plan", ["trial", "basico"])
def test_los_planes_de_entrada_no_traen_modulos(plan):
    """Si Básico ya trajera todo, no habría a qué mejorar y el precio dejaría
    de ser escalable. Es la razón de existir de la escalera."""
    feats = set(klicencias.PLANES[plan]["features"])
    incluidos = feats & set(klicencias.MODULOS)
    assert not incluidos, (
        f"{plan} incluye {sorted(incluidos)}: es un plan de entrada y no "
        "debería traer módulos de la suite.")


def test_enterprise_trae_todos_los_modulos():
    """El tope de la escalera. Si un módulo nuevo se agrega a MODULOS y se
    olvida acá, Enterprise deja de ser el plan completo sin que nadie avise."""
    feats = set(klicencias.PLANES["enterprise"]["features"])
    faltan = set(klicencias.MODULOS) - feats
    assert not faltan, f"a Enterprise le faltan módulos: {sorted(faltan)}"


def test_ningun_plan_caro_trae_menos_modulos_que_uno_barato():
    """La misma regla que ya cuida el cupo (test_plan_diferenciado.py), ahora
    sobre los módulos: pagar más y recibir menos es un cliente con razón para
    reclamar, y se rompe con una sola línea mal editada del catálogo."""
    cobrables = [(p, c) for p, c in klicencias.PLANES.items() if c["precio"]]
    for plan_a, cfg_a in cobrables:
        for plan_b, cfg_b in cobrables:
            if cfg_a["precio"] <= cfg_b["precio"]:
                continue
            mods_a = set(cfg_a["features"]) & set(klicencias.MODULOS)
            mods_b = set(cfg_b["features"]) & set(klicencias.MODULOS)
            faltan = mods_b - mods_a
            assert not faltan, (
                f"{plan_a} (US${cfg_a['precio']:.0f}) no incluye "
                f"{sorted(faltan)} y {plan_b} (US${cfg_b['precio']:.0f}), que "
                "es más barato, sí.")


# ---------------------------------------------------------------------------
# Que el gateo corte de verdad
# ---------------------------------------------------------------------------
def test_un_plan_sin_el_modulo_corta_la_accion(tmp_path, monkeypatch):
    """El modo de fallar que ya tuvo este repo: la licencia viajaba firmada
    con las features y nadie las miraba."""
    kplan = _plan_activo(tmp_path, monkeypatch, "basico")
    for modulo in klicencias.MODULOS:
        assert kplan.permite(modulo) is False, (
            f"Básico habilita {modulo} sin haberlo pagado")
        with pytest.raises(kplan.FeatureNoIncluida):
            kplan.exigir(modulo, "la gobernanza de datos")


def test_el_plan_que_lo_incluye_lo_deja_pasar(tmp_path, monkeypatch):
    """La otra mitad: un test que solo verifica que corta pasaría igual si
    cortara SIEMPRE, y ahí el cliente que pagó tampoco entra."""
    kplan = _plan_activo(tmp_path, monkeypatch, "enterprise")
    for modulo in klicencias.MODULOS:
        assert kplan.permite(modulo) is True, (
            f"Enterprise pagó {modulo} y no lo puede usar")
        kplan.exigir(modulo)          # no debe lanzar


def test_el_mensaje_de_corte_dice_donde_mejorar(tmp_path, monkeypatch):
    """Un cliente que se topa con un módulo que no tiene es una oportunidad de
    venta, no un error técnico: el mensaje tiene que decirle adónde ir."""
    kplan = _plan_activo(tmp_path, monkeypatch, "basico")
    with pytest.raises(kplan.FeatureNoIncluida) as e:
        kplan.exigir("automl", "el entrenamiento con tus propios datos")
    texto = str(e.value)
    assert "el entrenamiento con tus propios datos" in texto
    assert "mvkobranzaia.com" in texto, (
        "el mensaje no dice dónde mejorar el plan: se pierde la venta")


def test_un_modulo_se_puede_vender_suelto(tmp_path, monkeypatch):
    """Sin esto, venderle AutoML a un cliente de Básico obligaría a subirlo de
    plan entero. Es el mismo mecanismo que ya usa "voz_premium"."""
    kplan = _plan_activo(
        tmp_path, monkeypatch, "basico",
        features=[*klicencias.PLANES["basico"]["features"], "automl"])

    assert kplan.permite("automl") is True
    # y sigue sin tener los que no compró
    assert kplan.permite("dax") is False
