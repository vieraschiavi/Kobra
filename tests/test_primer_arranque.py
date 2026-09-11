# © 2026 Martín Viera. Todos los derechos reservados.

"""El primer contacto con el producto.

Los dos defectos que estos tests fijan no rompían nada: hacían que el programa
pareciera roto o lento a quien lo abría por primera vez, que es peor, porque no
hay a quién preguntarle y no queda ningún error para buscar.

1. `./run.sh` reentrenaba el modelo siempre — 10m21s medidos, de consola muda,
   antes de que apareciera una sola pantalla. Y no hacía falta: el modelo
   elegido y calibrado viene commiteado.
2. El backend en un clon fresco contestaba `{"detail":"Not Found"}` en `/`,
   porque la interfaz no está compilada y nada lo dice. El síntoma de "faltó
   compilar" era idéntico al de "escribiste mal la URL".
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

RUN_SH = os.path.join(ROOT, "run.sh")


def _guion():
    with open(RUN_SH, encoding="utf-8") as f:
        texto = f.read()
    # Los comentarios de este archivo explican POR QUÉ cada cosa, así que un
    # grep crudo se encuentra la explicación a sí mismo.
    return "\n".join(re.sub(r"#.*$", "", ln) for ln in texto.splitlines())


def _rama(nombre):
    """La línea del `case` para esa opción, sin comentarios."""
    for linea in _guion().splitlines():
        if linea.strip().startswith(f"{nombre})"):
            return linea
    raise AssertionError(f"run.sh no tiene la opción {nombre}")


# ---------------------------------------------------------------------------
# 1. Arrancar no cuesta diez minutos
# ---------------------------------------------------------------------------

def test_el_arranque_normal_no_reentrena_el_modelo():
    """`./run.sh` sin argumentos es lo que corre alguien que recién llega."""
    for opcion in ("all", "pipeline"):
        linea = _rama(opcion)
        assert "train_si_falta" in linea, f"{opcion} no usa el train condicional"
        assert not re.search(r"(^|[;\s])train($|[;\s])", linea), (
            f"{opcion} sigue reentrenando siempre: son 10 minutos de consola "
            f"muda antes de la primera pantalla")


def test_entrenar_a_mano_sigue_siendo_posible():
    """Saltear el entrenamiento no puede significar que no se pueda hacer."""
    assert re.search(r"(^|[;\s])train($|[;\s])", _rama("train")), (
        "`./run.sh train` tiene que reentrenar aunque el modelo ya esté")


def test_si_el_modelo_falta_se_entrena_igual():
    """Saltearlo cuando NO está sería peor que tardar: ahí el programa cae en
    el Gradient Boosting ad-hoc y 4.635 de 12.000 deudores (38,6%) cambian de
    decil — y el decil decide a quién se llama primero."""
    cuerpo = _guion().split("train_si_falta()", 1)[1].split("\n}", 1)[0]
    assert "outputs/probpago_model.joblib" in cuerpo
    assert "outputs/model_selection.json" in cuerpo, (
        "el joblib solo no alcanza: sin la selección se usa otro modelo")


def test_las_dos_ramas_hacen_lo_que_dicen(tmp_path):
    """Se ejecuta de verdad, con `train` reemplazado por un eco.

    Leer el `if` no alcanza: lo que importa es cuál de los dos caminos toma.
    """
    extraer = ["sed", "-n", "/^train_si_falta()/,/^}/p", RUN_SH]
    fuente = subprocess.run(extraer, capture_output=True, text=True,
                            check=True).stdout
    guion = fuente + '\ntrain() { echo "ENTRENA"; }\ntrain_si_falta\n'

    # Con el modelo: no entrena.
    r = subprocess.run(["bash", "-c", guion], cwd=ROOT,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "ENTRENA" not in r.stdout, r.stdout

    # Sin el modelo: entrena.
    (tmp_path / "outputs").mkdir()
    r = subprocess.run(["bash", "-c", guion], cwd=str(tmp_path),
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "ENTRENA" in r.stdout, r.stdout


# ---------------------------------------------------------------------------
# 2. Un 404 mudo no es una respuesta
# ---------------------------------------------------------------------------

def test_sin_interfaz_compilada_la_raiz_explica_que_hacer():
    """La función se prueba directo y no por HTTP a propósito: el `dist` existe
    o no según la máquina, así que un test que levantara el server daría verde
    por el motivo equivocado en cuanto alguien compile la interfaz."""
    from webapp.backend import api

    r = api.respuesta_sin_interfaz()
    assert r["ok"] is True, "no es un error: la API funciona, falta la pantalla"
    assert "npm" in " ".join(r["como_compilarla"]), "falta el comando exacto"
    assert "run build" in " ".join(r["como_compilarla"])
    # La salida que no necesita Node: quien solo quiere ver el producto no
    # tiene por qué instalar una toolchain de frontend.
    assert "streamlit run app/app.py" in r["mientras_tanto"]


def test_la_raiz_solo_se_reemplaza_cuando_no_hay_interfaz():
    """Si el dist está, manda el dist: esta respuesta no puede taparlo."""
    codigo = "\n".join(
        re.sub(r"#.*$", "", ln)
        for ln in open(os.path.join(ROOT, "webapp", "backend", "api.py"),
                       encoding="utf-8").read().splitlines())
    assert "if not _MONTADO:" in codigo
    montaje = codigo.split("if not _MONTADO:", 1)[0]
    assert 'app.mount("/"' in montaje, (
        "el montaje del dist tiene que seguir estando, y antes")
