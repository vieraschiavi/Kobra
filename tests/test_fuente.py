"""Qué mira el tablero cuando el cliente sube su cartera.

El pedido: «que al cargar o conectarse a una cartera TODAS las pestañas
hagan todo automático». Lo que estos casos fijan no es que el dato
llegue —eso es cableado— sino las dos cosas que se podrían romper
callando: que el historial del demo NO se muestre sobre la cartera del
cliente, y que una muestra chica se anuncie como chica.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from kobra import cartera_manual, fuente  # noqa: E402


def _cartera(n: int) -> pd.DataFrame:
    """Una cartera sintética del tamaño que se pida."""
    return pd.DataFrame({
        "nombre": [f"Contacto {i}" for i in range(n)],
        "telefono": [f"09900{i:04d}" for i in range(n)],
        "deuda": [1000.0 + i * 137 for i in range(n)],
        "dias_mora": [5 + (i * 13) % 300 for i in range(n)],
    })


def _gestiones_demo() -> pd.DataFrame:
    return pd.DataFrame({"mes": ["2026-01"], "segmento": ["Alta"],
                         "canal": ["Llamada"], "gestor": ["Ana"]})


# ==========================================================================
# la demo sigue siendo la demo
# ==========================================================================
def test_sin_cartera_propia_manda_la_demo_con_su_historial():
    f = fuente.desde_demo(_cartera(50), _gestiones_demo(), {"auc": 0.81})
    assert not f.propia
    assert f.hay_gestiones
    assert f.metricas == {"auc": 0.81}
    # Y no dibuja ningún cartel: uno permanente deja de leerse.
    assert fuente.aviso(f) == ""
    assert fuente.sin_historial(f) == ""


# ==========================================================================
# la cartera propia
# ==========================================================================
def test_la_cartera_propia_no_arrastra_el_historial_del_demo():
    """Lo que no se puede permitir bajo ningún concepto.

    Mostrarle al cliente la evolución de gestiones de los 12.000 deudores
    sintéticos con el nombre de su cartera es un gráfico plausible, sin
    error, y falso — la clase exacta de pantalla que este repo no entrega.
    """
    f = fuente.desde_propia(_cartera(50))
    assert f.propia
    assert not f.hay_gestiones
    assert f.gestiones.empty


def test_la_cartera_propia_no_hereda_las_metricas_del_modelo():
    """El AUC se midió sobre la cartera de referencia, no sobre ésta.

    Mostrarlo al lado de la cartera del cliente lo haría leer como «mi
    modelo acierta 0,81 sobre MIS deudores», que no se midió.
    """
    assert fuente.desde_propia(_cartera(50)).metricas is None


def test_se_dice_en_pantalla_que_se_esta_viendo_la_propia():
    aviso = fuente.aviso(fuente.desde_propia(_cartera(50)))
    assert "tu cartera" in aviso and "50" in aviso


# ==========================================================================
# la muestra chica
# ==========================================================================
def test_una_cartera_chica_se_anuncia_como_chica():
    """Con 12 filas, un decil tiene una fila: el corte describe el ruido
    de la muestra, no a la cartera. No se bloquea —el que sube 12 quiere
    verlos— pero se dice."""
    f = fuente.desde_propia(_cartera(12))
    assert f.pocas_filas
    assert "ruido de la muestra" in fuente.aviso(f)


def test_una_cartera_grande_no_lleva_esa_advertencia():
    f = fuente.desde_propia(_cartera(fuente.MINIMO_PARA_AGREGADOS + 5))
    assert not f.pocas_filas
    assert "ruido de la muestra" not in fuente.aviso(f)


def test_la_demo_nunca_se_marca_como_muestra_chica():
    """Aunque se le pase poco: el aviso habla de la cartera del cliente."""
    assert not fuente.desde_demo(_cartera(3), _gestiones_demo(), {}).pocas_filas


# ==========================================================================
# el camino completo, con el scoreador real
# ==========================================================================
def test_el_camino_entero_desde_un_archivo_hasta_la_fuente():
    """`importar_y_scorear` dice en su docstring que devuelve la cartera
    «lista para reemplazar los datos de demo del dashboard». Este test es
    lo que hacía falta para que eso fuera cierto y no una promesa."""
    scoreada = cartera_manual.importar_y_scorear(_cartera(40))
    f = fuente.desde_propia(scoreada)

    assert f.filas == 40
    # Las columnas que el tablero consume en sus tarjetas principales.
    for col in ("monto_deuda", "probpago", "segmento_propension",
                "valor_esperado_recupero", "dias_mora"):
        assert col in f.df.columns, col
    assert f.df["probpago"].between(0, 1).all()


def test_un_archivo_sin_columna_de_deuda_falla_diciendo_cual_falta():
    """El error tiene que nombrar la columna: un «no se pudo» genérico
    deja al usuario adivinando qué renombrar."""
    import pytest

    malo = pd.DataFrame({"nombre": ["A"], "telefono": ["099"]})
    with pytest.raises(ValueError) as exc:
        cartera_manual.importar_y_scorear(malo)
    assert "monto de deuda" in str(exc.value)
