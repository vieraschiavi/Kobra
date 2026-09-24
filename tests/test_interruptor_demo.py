"""El interruptor Demo ON/OFF del tablero y la cartera que mira cada pestaña.

La queja, textual: «KOBRA SIGUE SIN INTERRUPTOR DEMO ON/OFF y por más que
cargue cartera sigue apareciendo los datos demos siempre».

Lo que había detrás eran dos cosas, y las dos se fijan acá:

1. No había interruptor global: un «Modo demo» adentro de UNA pestaña, y
   para que el resto dejara la demo había que apretar además «Usar en todas
   las pestañas».
2. Cuando por fin se adoptaba la cartera, el tablero entero reventaba con
   `KeyError: 'auc_roc'` en la cabecera (y `'resultado'` en Integración
   ERP): las métricas del modelo no existen para la cartera del cliente.

La lógica pura (`kobra.fuente.resolver`) se prueba sin Streamlit; el
tablero de verdad, con `streamlit.testing.v1.AppTest`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from kobra import cartera_manual, fuente  # noqa: E402

APP = str(RAIZ / "app" / "app.py")


def _deudores_demo() -> str:
    """Tamaño de la demo tal como está en disco, con el formato del KPI.

    No se fija en 12,000: el CI genera la demo con `--n 3000` para ir más
    rápido, y un número escrito a mano hacía fallar el test ahí y pasar acá.
    """
    import csv
    with open(RAIZ / "data" / "kobra_cartera.csv", encoding="utf-8") as f:
        n = sum(1 for _ in csv.reader(f)) - 1
    return f"{n:,}"


def _cartera(n: int) -> pd.DataFrame:
    """Una cartera sintética del tamaño que se pida (ningún dato real)."""
    return pd.DataFrame({
        "nombre": [f"Contacto {i}" for i in range(n)],
        "telefono": [f"09900{i:04d}" for i in range(n)],
        "deuda": [1000.0 + i * 137 for i in range(n)],
        "dias_mora": [5 + (i * 13) % 300 for i in range(n)],
    })


# ==========================================================================
# la lógica: qué mira el tablero
# ==========================================================================
def test_sin_cartera_se_ve_la_demo():
    assert fuente.resolver(True, None) == fuente.DEMO
    assert fuente.demo_por_defecto(None) is True


def test_con_cartera_cargada_y_demo_apagada_se_ve_la_cartera():
    assert fuente.resolver(False, _cartera(5)) == fuente.PROPIA


def test_con_cartera_cargada_el_interruptor_arranca_apagado():
    """El que ya cargó su cartera no tiene que ir a apagar nada para verla."""
    assert fuente.demo_por_defecto(_cartera(5)) is False


def test_demo_prendida_gana_aunque_haya_cartera():
    """Se puede volver a mirar la demo sin perder la cartera cargada."""
    assert fuente.resolver(True, _cartera(5)) == fuente.DEMO


def test_demo_apagada_sin_cartera_es_sin_datos_explicito():
    """Nunca la demo en silencio: eso era «sigue apareciendo la demo»."""
    assert fuente.resolver(False, None) == fuente.SIN_DATOS
    assert fuente.resolver(False, pd.DataFrame()) == fuente.SIN_DATOS
    assert "cargaste tu cartera" in fuente.aviso_sin_datos()
    assert "ninguno" in fuente.etiqueta(fuente.SIN_DATOS)


def test_la_etiqueta_dice_que_datos_se_ven():
    assert fuente.etiqueta(fuente.DEMO) == "Datos: DEMO sintética"
    f = fuente.desde_propia(_cartera(7), nombre="mi_cartera.csv")
    rotulo = fuente.etiqueta(fuente.PROPIA, f)
    assert "tu cartera" in rotulo and "mi_cartera.csv" in rotulo and "7" in rotulo


# ==========================================================================
# ninguna pestaña lee la demo por su cuenta
# ==========================================================================
def test_la_demo_se_lee_en_un_solo_lugar_del_tablero():
    """Si una pestaña llamara a `cargar()` o al generador por su cuenta,
    seguiría mostrando la demo con la cartera propia activa. Los únicos
    usos permitidos son la definición y `_fuente_activa()`."""
    import re
    src = Path(APP).read_text(encoding="utf-8")
    # `cargar()` suelto; `kconfig.cargar()` es otra cosa (la configuración).
    llamadas = re.findall(r"(?<![\w.])cargar\(\)", src)
    # La definición (`def cargar():`) y la única llamada, en _fuente_activa.
    assert len(llamadas) == 2, "alguien más lee la demo con cargar()"
    assert src.count("generate_dataset") == 1
    assert src.count('"kobra_cartera.csv")') == 1


# ==========================================================================
# el tablero de verdad
# ==========================================================================
@pytest.fixture
def app(monkeypatch):
    pytest.importorskip("streamlit.testing.v1")
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("KOBRA_DASHBOARD_SIN_LOGIN", "1")
    at = AppTest.from_file(APP, default_timeout=600)
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _metrica(at, etiqueta: str) -> str:
    return next(m.value for m in at.metric if m.label == etiqueta)


def test_el_interruptor_esta_arriba_y_arranca_en_demo(app):
    toggles = {t.key: t for t in app.sidebar.toggle}
    assert fuente.CLAVE_DEMO in toggles
    assert toggles[fuente.CLAVE_DEMO].value is True
    # El primer elemento de la barra lateral: antes de los filtros.
    assert app.sidebar.toggle[0].key == fuente.CLAVE_DEMO
    assert any("Datos: DEMO sintética" in i.value for i in app.info)
    assert _metrica(app, "Deudores") == _deudores_demo()


def test_con_la_cartera_en_sesion_los_kpis_cambian_y_nada_revienta(app):
    """El caso que tiraba el tablero entero con KeyError."""
    propia = cartera_manual.importar_y_scorear(_cartera(40))
    app.session_state[fuente.CLAVE_SESION] = propia
    app.session_state[fuente.CLAVE_NOMBRE] = "cartera_prueba.csv"
    app.toggle(key=fuente.CLAVE_DEMO).set_value(False).run()

    assert not app.exception, [e.value for e in app.exception]
    assert _metrica(app, "Deudores") == "40"
    # Una cartera chica no se muestra como «$U 0.0M».
    assert _metrica(app, "Cartera (UYU)") == f"$U {propia['monto_deuda'].sum():,.0f}"
    assert any("tu cartera" in s.value and "cartera_prueba.csv" in s.value
               for s in app.success)

    # Y prender la Demo vuelve a la demo sin perder la cartera.
    app.toggle(key=fuente.CLAVE_DEMO).set_value(True).run()
    assert _metrica(app, "Deudores") == _deudores_demo()
    assert app.session_state[fuente.CLAVE_SESION] is not None


def test_cargar_una_cartera_la_adopta_en_todas_las_pestanas_sin_segundo_clic(app):
    """Sin «Usar en todas las pestañas»: se carga y el interruptor pasa a OFF."""
    contactos = cartera_manual.desde_dataframe(_cartera(12))
    app.session_state["contactos_db"] = contactos
    app.radio(key="modo_cartera").set_value("Traer de mi base de datos").run()

    assert not app.exception, [e.value for e in app.exception]
    assert app.toggle(key=fuente.CLAVE_DEMO).value is False
    assert _metrica(app, "Deudores") == "12"


def test_demo_apagada_sin_cartera_avisa_y_no_revienta(app):
    app.toggle(key=fuente.CLAVE_DEMO).set_value(False).run()

    assert not app.exception, [e.value for e in app.exception]
    assert any("todavía no cargaste tu cartera" in w.value for w in app.warning)
    # No se dibujan KPIs de la demo en silencio.
    assert not any(m.label == "Deudores" for m in app.metric)


def test_una_cartera_que_deja_otro_programa_se_adopta_sola(app):
    """Adium All in One: lo cargado en el panel de datos de la pestaña Kobra
    tiene que llegar al tablero. Antes Kobra lo ignoraba y seguía en demo."""
    app.session_state[fuente.CLAVE_EXTERNA] = (_cartera(25), "consulta SQL de la suite")
    app.run()
    assert not app.exception, [e.value for e in app.exception]
    assert _metrica(app, "Deudores") == "25"
    assert app.session_state[fuente.CLAVE_DEMO] is False
    assert any("consulta SQL de la suite" in s.value for s in app.success)
    # Prender la demo NO la vuelve a imponer: se adopta una vez por dataset.
    app.toggle(key=fuente.CLAVE_DEMO).set_value(True).run()
    assert _metrica(app, "Deudores") == _deudores_demo()


def test_la_firma_distingue_carteras_distintas():
    a, b = _cartera(5), _cartera(6)
    assert fuente.firma(a) == fuente.firma(a.copy())
    assert fuente.firma(a) != fuente.firma(b)


# ==========================================================================
# el Copiloto: los ejemplos sintéticos sólo vienen puestos con la demo
# ==========================================================================
def test_los_ejemplos_del_copiloto_se_precargan_solo_con_la_demo():
    assert fuente.precargar_ejemplos(fuente.DEMO) is True
    assert fuente.precargar_ejemplos(fuente.PROPIA) is False
    assert fuente.precargar_ejemplos(fuente.SIN_DATOS) is False


def _conversacion(at) -> str:
    return next(t.value for t in at.text_area if t.label == "…o pegá la conversación acá")


def _usar_grabacion_demo(at) -> bool:
    return next(c.value for c in at.checkbox if c.label.startswith("Usar grabación de demo"))


def test_con_la_cartera_propia_el_copiloto_no_arranca_con_el_chat_de_la_demo(app):
    """La fuga que quedaba: con la cartera del cliente activa, el Copiloto
    seguía precargando y analizando el chat y la llamada sintéticos."""
    assert _conversacion(app).strip()          # con la demo, el ejemplo está
    assert _usar_grabacion_demo(app) is True

    app.session_state[fuente.CLAVE_SESION] = cartera_manual.importar_y_scorear(_cartera(40))
    app.session_state[fuente.CLAVE_NOMBRE] = "cartera_prueba.csv"
    app.toggle(key=fuente.CLAVE_DEMO).set_value(False).run()
    assert not app.exception, [e.value for e in app.exception]
    assert _conversacion(app) == ""
    assert _usar_grabacion_demo(app) is False
