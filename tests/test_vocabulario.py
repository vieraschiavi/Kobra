# © 2026 Martín Viera. Todos los derechos reservados.

"""El vocabulario del producto en tres idiomas — y los datos del cliente, no.

Con la interfaz en portugués la tabla de cartera mostraba encabezados en
portugués y celdas que decían "Recordatorio suave" e "Individuo": la mitad de
lo que se lee en esa pantalla son VALORES que escribe Kobra al scorear, no
etiquetas de la interfaz.

La línea que se fija acá es cuál es cuál. Se traduce lo que genera el producto
(estrategia, resultado de una gestión, segmento de propensión). NO se traduce
lo que trajo el cliente en su archivo: su deudor se llama como se llama.
"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import vocabulario as kv  # noqa: E402


def test_traduce_el_vocabulario_que_genera_el_producto():
    df = pd.DataFrame([{"estrategia": "Recordatorio suave",
                        "segmento_propension": "Alta",
                        "resultado": "No contactado"}])
    en = kv.traducir(df, "en").iloc[0]
    assert en["estrategia"] == "Gentle reminder"
    assert en["segmento_propension"] == "High"
    assert en["resultado"] == "Not reached"
    pt = kv.traducir(df, "pt").iloc[0]
    assert pt["estrategia"] == "Lembrete leve"
    assert pt["resultado"] == "Não contatado"


def test_no_toca_los_datos_del_cliente():
    """Traducir el nombre de un deudor o el rubro que puso el cliente en su
    archivo sería inventarle otra base de datos."""
    df = pd.DataFrame([{"nombre": "Ana Pérez", "notas": "Llamar al hijo",
                        "producto_propio": "Crédito Verano 2026",
                        "estrategia": "Plan de cuotas"}])
    for idioma in ("pt", "en"):
        fila = kv.traducir(df, idioma).iloc[0]
        assert fila["nombre"] == "Ana Pérez"
        assert fila["notas"] == "Llamar al hijo"
        assert fila["producto_propio"] == "Crédito Verano 2026"
        assert fila["estrategia"] != "Plan de cuotas"   # esto sí es nuestro


def test_un_valor_desconocido_pasa_intacto():
    """Una cartera real trae valores que no están en el catálogo: tienen que
    llegar a la pantalla como vinieron, no desaparecer ni romper."""
    df = pd.DataFrame([{"estrategia": "Convenio judicial propio del cliente"}])
    assert kv.traducir(df, "en").iloc[0]["estrategia"] == \
        "Convenio judicial propio del cliente"


def test_en_castellano_devuelve_lo_mismo_sin_copiar_de_mas():
    df = pd.DataFrame([{"estrategia": "Plan de cuotas"}])
    assert kv.traducir(df, "es") is df


def test_no_modifica_el_dataframe_original():
    """Lo que se guarda en disco sigue en castellano: una sola verdad en los
    datos. Si el cliente cambia de idioma, sus archivos no cambian."""
    df = pd.DataFrame([{"estrategia": "Plan de cuotas"}])
    kv.traducir(df, "en")
    assert df.iloc[0]["estrategia"] == "Plan de cuotas"


@pytest.mark.parametrize("idioma", ["pt", "en"])
def test_todo_el_catalogo_esta_completo(idioma):
    faltan = [k for k, v in kv._CATALOGO.items() if not v.get(idioma, "").strip()]
    assert not faltan, f"sin traducción a {idioma}: {faltan}"


def test_el_catalogo_cubre_lo_que_de_verdad_genera_el_scoring():
    """Control del control: se scorea una cartera de verdad y se exige que
    todas las estrategias que salieron estén en el catálogo. Si mañana el
    negociador agrega una estrategia nueva, este test la reclama en vez de
    dejarla saliendo en castellano en la app en inglés."""
    from data.generate_dataset import generar
    from kobra import negociador
    df = negociador.recomendar(generar(n=300, seed=42).assign(
        probpago=lambda d: (d["score_buro"] - 400) / 500))
    sin_traducir = sorted(set(df["estrategia"]) - set(kv._CATALOGO))
    assert not sin_traducir, (
        f"el negociador genera estrategias que el catálogo no conoce: "
        f"{sin_traducir}")
