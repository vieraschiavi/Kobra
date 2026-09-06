# © 2026 Martín Viera. Todos los derechos reservados.

"""El panel de frecuencia de cargas: que el semáforo diga la verdad.

Lo que se prueba acá no es que la pantalla dibuje: es que el veredicto sea
correcto. Un panel de frescura que marca verde una tabla vencida es peor que
no tenerlo — le pone un sello de confianza a un dato viejo.

Todos los tests inyectan `ahora`: un semáforo que depende del reloj de la
máquina deja una suite que falla sola un martes a la madrugada.
"""
import ast
import json
import os
import sys
from datetime import datetime, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import frecuencia_cargas as kfc  # noqa: E402

AHORA = datetime(2026, 9, 6, 10, 0, 0)


def _archivo(tmp_path, nombre, contenido, hace_horas=0.0):
    """Un archivo con una fecha de modificación puesta a mano.

    La fecha de carga sale del mtime del archivo real: falsear el reloj no
    alcanza, hay que falsear el archivo.
    """
    ruta = tmp_path / nombre
    ruta.write_text(contenido, encoding="utf-8")
    cuando = (AHORA - timedelta(hours=hace_horas)).timestamp()
    os.utime(ruta, (cuando, cuando))
    return str(ruta)


def _tabla(id_tabla):
    tabla = kfc.por_id(id_tabla)
    assert tabla is not None, f"El catálogo no tiene la tabla {id_tabla}"
    return tabla


# ---------------------------------------------------------------------------
# El veredicto
# ---------------------------------------------------------------------------

def test_una_tabla_que_nunca_se_cargo_no_se_muestra_como_al_dia(tmp_path):
    """El caso más peligroso: el archivo no está y la pantalla igual dibuja.

    Sin este estado, una instalación nueva sin la cartera importada se ve
    idéntica a una que carga todos los días.
    """
    ficha = kfc.estado_de(str(tmp_path / "no_existe.csv"),
                          _tabla("scored"), AHORA)
    assert ficha["estado"] == kfc.SIN_DATOS
    assert ficha["carga"] is None
    assert ficha["filas"] is None
    assert ficha["motivo"], "Sin motivo, el operador no sabe qué hacer"


def test_una_carga_diaria_de_hace_cinco_horas_esta_al_dia(tmp_path):
    ruta = _archivo(tmp_path, "scored.csv", "a,b\n1,2\n", hace_horas=5)
    ficha = kfc.estado_de(ruta, _tabla("scored"), AHORA)
    assert ficha["estado"] == kfc.AL_DIA
    assert ficha["carga"] == "2026-09-06 05:00:00"


def test_una_carga_diaria_de_hace_tres_dias_aparece_atrasada(tmp_path):
    ruta = _archivo(tmp_path, "scored.csv", "a,b\n1,2\n", hace_horas=72)
    ficha = kfc.estado_de(ruta, _tabla("scored"), AHORA)
    assert ficha["estado"] == kfc.ATRASADA
    assert "3 días" in ficha["motivo"], ficha["motivo"]


@pytest.mark.parametrize("horas,esperado", [
    (30, kfc.AL_DIA),      # dentro de la tolerancia: el proceso corrió tarde
    (36, kfc.AL_DIA),      # el borde exacto (24h x 1,5) todavía es verde
    (40, kfc.ATRASADA),    # pasada la tolerancia ya es un problema
])
def test_la_tolerancia_evita_el_rojo_de_todas_las_mananas(tmp_path, horas,
                                                          esperado):
    """Sin margen, el panel se pone rojo todos los días antes de que corra el
    proceso — y un semáforo que siempre está en rojo se deja de mirar."""
    ruta = _archivo(tmp_path, "scored.csv", "a\n1\n", hace_horas=horas)
    assert kfc.estado_de(ruta, _tabla("scored"), AHORA)["estado"] == esperado


def test_una_tabla_manual_no_vence_por_antiguedad(tmp_path):
    """La cartera real la sube una persona cuando corresponde: marcarla en rojo
    a los dos meses es ruido, no información."""
    ruta = _archivo(tmp_path, "cartera.csv", "a\n1\n", hace_horas=24 * 200)
    ficha = kfc.estado_de(ruta, _tabla("cartera_real"), AHORA)
    assert ficha["estado"] == kfc.AL_DIA
    assert kfc.PERIODOS_HORAS["manual"] is None


def test_la_fecha_del_dato_y_la_fecha_de_carga_se_informan_por_separado(
        tmp_path):
    """El error clásico: un proceso que corrió hoy a las 6 AM pero trajo el
    cierre de hace tres semanas está «actualizado» y sus datos están viejos.
    Con un solo campo eso es invisible."""
    contenido = ("fecha_gestion,gestor\n"
                 "2026-08-01,ana\n2026-08-15,ana\n")
    ruta = _archivo(tmp_path, "gestiones.csv", contenido, hace_horas=1)
    ficha = kfc.estado_de(ruta, _tabla("gestiones"), AHORA)
    assert ficha["estado"] == kfc.AL_DIA           # se cargó hace una hora
    assert ficha["fecha_dato"] == "2026-08-15"     # y el dato es de agosto
    assert ficha["carga"].startswith("2026-09-06")


def test_una_columna_de_fecha_rota_no_tira_abajo_el_panel(tmp_path):
    """Un archivo sin la columna esperada tiene que salir sin fecha de dato, no
    hacer explotar la pantalla entera."""
    ruta = _archivo(tmp_path, "gestiones.csv", "otra_cosa\n1\n", hace_horas=1)
    ficha = kfc.estado_de(ruta, _tabla("gestiones"), AHORA)
    assert ficha["fecha_dato"] is None
    assert ficha["estado"] == kfc.AL_DIA


def test_las_filas_se_cuentan_sin_contar_el_encabezado(tmp_path):
    ruta = _archivo(tmp_path, "scored.csv", "a,b\n1,2\n3,4\n5,6\n")
    assert kfc.estado_de(ruta, _tabla("scored"), AHORA)["filas"] == 3


def test_un_binario_no_reporta_registros(tmp_path):
    """El modelo entrenado es un `.joblib`: contarle "líneas" devuelve un
    número con toda la pinta de ser un dato —la pantalla llegó a decir «45
    registros»— y un número inventado en el panel que existe para dar
    confianza es exactamente lo que no puede pasar."""
    ruta = _archivo(tmp_path, "modelo.joblib", "\x80\x04\n\n\x95bin\nario\n",
                    hace_horas=1)
    ficha = kfc.estado_de(ruta, _tabla("modelo"), AHORA)
    assert ficha["filas"] is None
    assert ficha["estado"] == kfc.AL_DIA      # el resto del veredicto sigue
    assert ficha["carga"] is not None


def test_solo_el_modelo_esta_marcado_como_no_tabular():
    """Un CSV marcado como binario perdería el conteo de filas en silencio."""
    no_tabulares = {t.id for t in kfc.TABLAS if not t.tabular}
    assert no_tabulares == {"modelo"}


def test_el_dia_de_la_semana_acompana_a_la_fecha_de_carga(tmp_path):
    """«cargó un domingo» se detecta más rápido por el nombre del día que por
    la fecha."""
    ruta = _archivo(tmp_path, "scored.csv", "a\n1\n", hace_horas=0)
    ficha = kfc.estado_de(ruta, _tabla("scored"), AHORA)
    assert ficha["dia_carga"] == "domingo"   # 2026-09-06 cae domingo


# ---------------------------------------------------------------------------
# El panel completo
# ---------------------------------------------------------------------------

def test_el_resumen_cuenta_y_el_titular_nombra_lo_que_esta_mal(tmp_path):
    rutas = {
        "scored": _archivo(tmp_path, "scored.csv", "a\n1\n", hace_horas=2),
        "gestiones": _archivo(tmp_path, "gestiones.csv", "fecha_gestion\n"
                              "2026-09-05\n", hace_horas=24 * 9),
        "calidad": _archivo(tmp_path, "calidad.csv", "fecha\n2026-09-01\n",
                            hace_horas=3),
        "cartera_real": str(tmp_path / "falta.csv"),
        "modelo": str(tmp_path / "falta.joblib"),
    }
    datos = kfc.panel(rutas, "es", AHORA)

    assert datos["resumen"]["total"] == len(kfc.TABLAS)
    assert datos["resumen"]["atrasadas"] == 1
    assert datos["resumen"]["sin_datos"] == 2
    assert datos["resumen"]["al_dia"] == len(kfc.TABLAS) - 3
    # El titular es lo que se copia en un mail: tiene que nombrar la tabla.
    assert kfc.textos("es")["tablas"]["gestiones"]["nombre"] in datos["titular"]


def test_con_todo_al_dia_el_titular_lo_dice_sin_rodeos(tmp_path):
    rutas = {t.id: _archivo(tmp_path, f"{t.id}.csv", "a\n1\n", hace_horas=1)
             for t in kfc.TABLAS}
    datos = kfc.panel(rutas, "es", AHORA)
    assert datos["resumen"]["atrasadas"] == 0
    assert datos["titular"] == kfc.textos("es")["titular"]["todo_al_dia"]


def test_el_panel_no_se_rompe_si_falta_una_ruta_en_el_diccionario():
    """El backend podría no saber ubicar una tabla: eso es «sin cargar», no
    una excepción en la mitad de la pantalla."""
    datos = kfc.panel({}, "es", AHORA)
    assert datos["resumen"]["sin_datos"] == len(kfc.TABLAS)


def test_proxima_carga_solo_existe_donde_hay_cadencia():
    ultima = datetime(2026, 9, 6, 6, 0, 0)
    assert kfc.proxima_carga(_tabla("scored"), ultima) == ultima + timedelta(
        hours=24)
    assert kfc.proxima_carga(_tabla("cartera_real"), ultima) is None


# ---------------------------------------------------------------------------
# Los tres idiomas
# ---------------------------------------------------------------------------

def _dic(idioma):
    ruta = os.path.join(ROOT, "kobra", "frecuencia", f"{idioma}.json")
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _rutas(o, prefijo=""):
    salida = {}
    for k, v in o.items():
        if isinstance(v, dict):
            salida.update(_rutas(v, f"{prefijo}{k}."))
        else:
            salida[f"{prefijo}{k}"] = v
    return salida


@pytest.mark.parametrize("idioma", ["en", "pt"])
def test_los_tres_diccionarios_tienen_exactamente_las_mismas_claves(idioma):
    """Una clave que falte deja media pantalla en castellano y media en el otro
    idioma, que es peor que no traducir."""
    es, otro = _rutas(_dic("es")), _rutas(_dic(idioma))
    assert not set(es) - set(otro), f"{idioma}: faltan {sorted(set(es) - set(otro))}"
    assert not set(otro) - set(es), f"{idioma}: sobran {sorted(set(otro) - set(es))}"


@pytest.mark.parametrize("idioma", ["es", "en", "pt"])
def test_los_huecos_de_las_frases_sobreviven_a_la_traduccion(idioma):
    """`{n}`, `{hace}`, `{nombres}`… los rellena el código. Si la traducción se
    come uno, el cliente ve la frase sin el número; si lo renombra, el
    `.format()` levanta KeyError delante del cliente."""
    dic = _dic(idioma)
    assert set(_huecos(dic["motivo"]["atrasada"])) == {"frecuencia", "hace",
                                                       "atraso"}
    for clave in ("atrasadas", "sin_cargar"):
        assert set(_huecos(dic["titular"][clave])) == {"n", "nombres"}
    for plantilla in dic["hace"].values():
        assert set(_huecos(plantilla)) == {"n"}


def _huecos(plantilla):
    import string
    return [campo for _, campo, _, _ in string.Formatter().parse(plantilla)
            if campo]


@pytest.mark.parametrize("idioma", ["es", "en", "pt"])
def test_cada_idioma_describe_todas_las_tablas_del_catalogo(idioma):
    fichas = _dic(idioma)["tablas"]
    for tabla in kfc.TABLAS:
        assert tabla.id in fichas, f"{idioma}: falta la tabla {tabla.id}"
        assert fichas[tabla.id]["nombre"].strip()
        assert fichas[tabla.id]["para_que"].strip()
    assert set(fichas) == {t.id for t in kfc.TABLAS}, (
        f"{idioma}: hay fichas de tablas que el catálogo no tiene")


@pytest.mark.parametrize("idioma", ["es", "en", "pt"])
def test_cada_idioma_nombra_las_cinco_cadencias_y_los_siete_dias(idioma):
    dic = _dic(idioma)
    assert set(dic["cada"]) == set(kfc.PERIODOS_HORAS)
    assert set(dic["frecuencia"]) == set(kfc.PERIODOS_HORAS)
    assert len(dic["dias"]) == 7


def test_el_panel_en_ingles_no_devuelve_texto_en_castellano(tmp_path):
    rutas = {"scored": _archivo(tmp_path, "scored.csv", "a\n1\n",
                                hace_horas=72)}
    datos = kfc.panel(rutas, "en", AHORA)
    assert datos["idioma"] == "en"
    ficha = next(t for t in datos["tablas"] if t["id"] == "scored")
    assert ficha["nombre"] == _dic("en")["tablas"]["scored"]["nombre"]
    assert ficha["nombre"] != _dic("es")["tablas"]["scored"]["nombre"]
    assert "days" in ficha["motivo"], ficha["motivo"]


def test_un_idioma_desconocido_cae_a_castellano_y_no_deja_la_pantalla_vacia():
    """Un `Accept-Language` raro (`de`, `zz`, vacío) no puede dejar una pantalla
    sin texto: cae a castellano, como el resto del programa."""
    for raro in ("de", "zz", "", None, "ES-419"):
        datos = kfc.panel({}, raro, AHORA)
        assert datos["idioma"] in kfc.IDIOMAS
        assert datos["titular"]
    assert kfc.normalizar("de") == "es"
    assert kfc.normalizar("pt-BR") == "pt"
    assert kfc.normalizar("EN") == "en"


# ---------------------------------------------------------------------------
# El cableado: catálogo ↔ backend ↔ pantalla
# ---------------------------------------------------------------------------

def _fuente(*partes):
    with open(os.path.join(ROOT, *partes), encoding="utf-8") as f:
        return f.read()


def test_el_backend_sabe_ubicar_todas_las_tablas_del_catalogo():
    """Si el catálogo nombra una tabla que `_rutas_de_tablas` no resuelve, el
    panel la muestra «sin cargar» para siempre y nadie se entera de por qué."""
    arbol = ast.parse(_fuente("webapp", "backend", "api.py"))
    funcion = next(n for n in ast.walk(arbol)
                   if isinstance(n, ast.FunctionDef)
                   and n.name == "_rutas_de_tablas")
    claves = {k.value for n in ast.walk(funcion) if isinstance(n, ast.Dict)
              for k in n.keys if isinstance(k, ast.Constant)}
    faltan = {t.id for t in kfc.TABLAS} - claves
    assert not faltan, f"El backend no sabe dónde vive: {sorted(faltan)}"


def test_el_endpoint_pide_el_idioma_como_el_resto_del_programa():
    """El texto que arma el motor viaja por `Accept-Language`. Si este endpoint
    no lo pide, la pantalla queda en inglés con los motivos en castellano."""
    arbol = ast.parse(_fuente("webapp", "backend", "api.py"))
    funcion = next(n for n in ast.walk(arbol)
                   if isinstance(n, ast.FunctionDef)
                   and n.name == "frecuencia_cargas")
    argumentos = [a.arg for a in funcion.args.args]
    assert "idioma" in argumentos, argumentos


def test_la_pestana_esta_enchufada_en_la_aplicacion():
    """Importada, en el menú y con ruta: las tres. Con la ruta pero sin la
    entrada del menú, la pantalla existe y nadie la encuentra."""
    app = _fuente("webapp", "frontend", "src", "App.jsx")
    assert "pages/FrecuenciaCargas.jsx" in app
    assert "app.nav.frecuencia_cargas" in app
    assert 'path="/frecuencia-cargas"' in app


def test_la_pantalla_muestra_las_dos_fechas_y_no_solo_la_de_carga():
    """La distinción entre fecha del dato y fecha de carga es la razón de ser
    del panel: si la pantalla muestra una sola, el panel deja de servir."""
    pagina = _fuente("webapp", "frontend", "src", "pages",
                     "FrecuenciaCargas.jsx")
    assert "frecuencia.fecha_dato" in pagina
    assert "frecuencia.fecha_carga" in pagina


def test_los_miles_salen_en_el_idioma_elegido_y_no_en_el_del_navegador():
    """`toLocaleString()` sin argumento usa el locale del navegador: el mismo
    programa mostraría «12,000» en una pantalla en castellano y «12.000» en la
    de al lado, que se lee como un error de datos."""
    pagina = _fuente("webapp", "frontend", "src", "pages",
                     "FrecuenciaCargas.jsx")
    assert "getIdioma" in pagina
    assert "toLocaleString(" + ")" not in pagina.replace(" ", "")


@pytest.mark.parametrize("archivo", ["es.json", "en.json", "pt-BR.json"])
def test_la_interfaz_tiene_las_etiquetas_de_la_pestana_en_los_tres_idiomas(
        archivo):
    ruta = os.path.join(ROOT, "webapp", "frontend", "src", "i18n", archivo)
    with open(ruta, encoding="utf-8") as f:
        dic = json.load(f)
    assert dic["app"]["nav"]["frecuencia_cargas"].strip()
    for clave in ("titulo", "fecha_dato", "fecha_carga", "estado_atrasada",
                  "estado_sin_datos", "actualizado", "revisar"):
        assert dic["frecuencia"][clave].strip(), f"{archivo}: falta {clave}"
    assert "{{cuando}}" in dic["frecuencia"]["actualizado"]


def test_una_fecha_con_hora_no_desaparece_de_la_columna(tmp_path):
    """Una cartera real trae «2026-01-01» y «2026-06-30 23:50» en la MISMA
    columna. Sin `format="mixed"`, pandas infiere el formato de la primera
    fila y convierte en NaT todas las que traen hora: con la fecha más nueva
    en una de esas filas, el panel informaba un dato de febrero cuando el
    último era de junio.

    Cinco meses de atraso inventados, en silencio, en la única pantalla que
    existe para que un atraso NO pase inadvertido.
    """
    contenido = ("fecha_gestion,gestor\n"
                 "2026-01-01,ana\n"
                 "2026-02-01,ana\n"
                 "2026-06-30 23:50,ana\n")
    ruta = _archivo(tmp_path, "gestiones.csv", contenido, hace_horas=1)
    ficha = kfc.estado_de(ruta, _tabla("gestiones"), AHORA)
    assert ficha["fecha_dato"] == "2026-06-30", (
        "se perdió la fila con hora: el panel reporta el dato más viejo de lo "
        f"que es ({ficha['fecha_dato']})")


def test_una_columna_entera_con_hora_tampoco_se_pierde(tmp_path):
    """El caso simétrico: si TODAS traen hora, el formato inferido funciona —
    pero el test lo fija para que el arreglo no se revierta a medias."""
    contenido = ("fecha_gestion,gestor\n"
                 "2026-05-01 08:00,ana\n2026-05-02 17:30,ana\n")
    ruta = _archivo(tmp_path, "gestiones.csv", contenido, hace_horas=1)
    assert kfc.estado_de(ruta, _tabla("gestiones"), AHORA)["fecha_dato"] == "2026-05-02"
