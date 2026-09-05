# © 2026 Martín Viera. Todos los derechos reservados.

"""La memoria técnica: qué hace el pipeline, para las dos audiencias.

Pedido: *"una pestaña de todas las transformaciones y características técnicas
en lenguaje técnico y criollo, para que lo entiendan desde programadores hasta
un jefe/gerente... en orden secuencial del pipeline, exportable html/Word/pdf"*.

Un documento así se pudre solo: el código cambia, nadie relee el texto, y a los
seis meses describe un programa que no existe. Lo que se fija acá es lo que una
máquina SÍ puede verificar:

  * cada etapa nombra módulos que existen de verdad;
  * el orden es secuencial y sin huecos;
  * las dos audiencias están cubiertas, y el texto "en criollo" no es el
    técnico con otro nombre;
  * los tres formatos salen del MISMO catálogo — si salieran de plantillas
    separadas, el PDF y el HTML se separarían sin que nadie se entere.
"""
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from kobra import memoria_tecnica as mt  # noqa: E402


# --- El catálogo describe el programa que existe ---------------------------
def test_cada_etapa_apunta_a_modulos_reales():
    """La guarda que hace que el documento no se pudra: si un módulo se
    renombra o se borra, esto falla y alguien tiene que releer el texto."""
    faltan = []
    for e in mt.etapas():
        for modulo in e.modulos:
            ruta = os.path.join(ROOT, modulo)
            if not (os.path.isfile(ruta) or os.path.isdir(ruta.rstrip("/"))):
                faltan.append(f"{e.id} -> {modulo}")
    assert not faltan, f"la memoria describe módulos que no existen: {faltan}"


def test_el_orden_es_secuencial_y_sin_huecos():
    """Es un pipeline, no una lista de features: el número de etapa tiene que
    poder leerse como «esto pasa después de aquello»."""
    ordenes = [e.orden for e in mt.etapas()]
    assert ordenes == list(range(1, len(ordenes) + 1)), \
        f"el orden tiene huecos o repetidos: {ordenes}"


def test_no_hay_ids_repetidos():
    ids = [e.id for e in mt.etapas()]
    assert len(ids) == len(set(ids)), f"ids duplicados: {ids}"


def test_arranca_en_la_entrada_de_datos_y_termina_en_la_salida():
    """Si el orden fuera temático en vez de secuencial, el lector no podría
    seguir el recorrido de un dato."""
    etapas = mt.etapas()
    assert etapas[0].id == "ingesta"
    assert etapas[-1].id == "exports"


def test_el_modelo_va_despues_de_los_datos_y_antes_de_la_estrategia():
    """El orden que importa: no se puede scorear lo que no se cargó, ni
    decidir una oferta sin el score."""
    pos = {e.id: e.orden for e in mt.etapas()}
    assert pos["ingesta"] < pos["ingenieria"] < pos["probpago"]
    assert pos["probpago"] < pos["negociador"] < pos["campana"]
    assert pos["cumplimiento"] < pos["campana"], \
        "la campaña se arma antes de chequear si se puede contactar"


# --- Las dos audiencias ----------------------------------------------------
@pytest.mark.parametrize("campo", ["tecnico", "criollo", "por_que",
                                   "repercusion", "entradas", "salidas"])
def test_ninguna_etapa_queda_a_medio_documentar(campo):
    vacias = [e.id for e in mt.etapas() if not getattr(e, campo).strip()]
    assert not vacias, f"etapas sin '{campo}': {vacias}"


def test_el_criollo_no_es_el_texto_tecnico_con_otro_nombre():
    """El punto de tener dos registros es que digan lo mismo de dos maneras.
    Copiar y pegar deja un documento que no le sirve a ninguno de los dos."""
    iguales = [e.id for e in mt.etapas() if e.criollo.strip() == e.tecnico.strip()]
    assert not iguales, f"criollo copiado del técnico en: {iguales}"


# La jerga que un gerente no tiene por qué saber. Si aparece en el texto
# "en criollo", ese texto no está cumpliendo su función.
_JERGA = ("dataframe", "auc", "sqlalchemy", "gradient boosting", "endpoint",
          "json", "encoding", "booleano", "csv/xlsx", "reason code")


def test_el_texto_en_criollo_no_usa_jerga_tecnica():
    """No es purismo: es el criterio que hace útil la columna. Un gerente que
    encuentra «AUC-ROC» deja de leer, y el documento no cumplió su objetivo."""
    sucias = []
    for e in mt.etapas():
        bajo = e.criollo.lower()
        for palabra in _JERGA:
            if palabra in bajo:
                sucias.append(f"{e.id}: '{palabra}'")
    assert not sucias, f"jerga en el texto para gerencia: {sucias}"


def test_el_texto_tecnico_si_puede_ser_tecnico():
    """El control opuesto: si el lado técnico también evitara la jerga, no le
    serviría a un programador y el documento sería uno solo, más flojo."""
    todo = " ".join(e.tecnico.lower() for e in mt.etapas())
    assert sum(p in todo for p in _JERGA) >= 3, \
        "el texto técnico es tan vago como el criollo: no le sirve a un programador"


def test_cada_etapa_explica_como_repercute():
    """Es lo que convierte una lista de features en un pipeline: sin esto, el
    lector no entiende por qué el orden importa."""
    for e in mt.etapas():
        assert len(e.repercusion) > 40, \
            f"{e.id}: la repercusión aguas abajo está apenas esbozada"


def test_dice_lo_que_el_programa_NO_hace():
    """Un documento que solo suma es publicidad. Los límites son lo que lo
    vuelve creíble cuando lo lee alguien que va a auditarlo."""
    con_limites = [e for e in mt.etapas() if e.limites.strip()]
    assert len(con_limites) >= len(mt.etapas()) * 0.8, \
        "casi ninguna etapa aclara sus límites"


def test_la_demo_sintetica_se_declara_donde_se_habla_de_impacto():
    """Las cifras de impacto son ilustrativas. Decirlo en la etapa donde
    aparecen los números es lo que evita que se lean como resultados medidos."""
    analitica = mt.por_id("analitica")
    assert analitica is not None
    texto = (analitica.limites + analitica.tecnico + analitica.criollo).lower()
    assert "sintétic" in texto or "ilustrativ" in texto


# --- Los tres formatos, del mismo catálogo ---------------------------------
@pytest.fixture(scope="module")
def exportador():
    from kobra import memoria_tecnica_export as ex
    return ex


def test_el_html_es_autocontenido(exportador):
    """Se manda adjunto por mail y se abre con doble clic. Un CSS por CDN lo
    deja sin formato en la mitad de esos casos, y un <script> hace que algunos
    clientes de correo lo bloqueen entero."""
    h = exportador.como_html()
    assert h.startswith("<!doctype html>")
    assert "<script" not in h.lower(), "el HTML lleva JavaScript"
    assert not re.search(r'(src|href)=["\']https?://', h), \
        "el HTML depende de un recurso externo"


def test_el_html_escapa_el_contenido(exportador):
    """El texto sale del catálogo del repo, pero escaparlo igual cuesta nada y
    evita que un `<` en una descripción futura rompa el documento."""
    assert "&lt;" in exportador.como_html() or "<" not in "".join(
        e.tecnico for e in mt.etapas())


def test_el_docx_es_un_docx_de_verdad(exportador):
    """No un HTML con la extensión cambiada: eso Word lo abre, pero se rompe en
    Google Docs y en LibreOffice, y deja al que lo recibe explicando por qué su
    editor no lo toma."""
    import zipfile
    datos = exportador.como_docx()
    assert datos[:2] == b"PK", "no es un archivo OOXML"
    with zipfile.ZipFile(__import__("io").BytesIO(datos)) as z:
        assert "word/document.xml" in z.namelist()


def test_el_pdf_es_un_pdf(exportador):
    assert exportador.como_pdf()[:5] == b"%PDF-"


def test_el_pdf_no_explota_con_acentos_ni_comillas(exportador):
    """FPDF con las fuentes del núcleo solo escribe latin-1: un guion largo
    pegado desde Word tiraba abajo la generación entera."""
    # Los acentos SÍ están en latin-1 y se conservan: lo que rompía eran los
    # signos tipográficos (guion largo, comillas curvas, puntos suspensivos).
    assert exportador._latin1("cómo — “así” … 3 × 4") == 'cómo - "así" ... 3 x 4'
    assert exportador.como_pdf()  # el catálogo real, con sus acentos


def _texto(salida):
    """El contenido legible de un export.

    HTML y DOCX se inspeccionan enteros. El PDF NO: fpdf comprime los streams
    de texto, así que buscar una palabra en los bytes crudos no encuentra nada
    aunque esté ahí. Por eso la paridad de contenido se verifica sobre los dos
    formatos inspeccionables, y que el PDF salga del mismo catálogo se prueba
    aparte (`test_el_pdf_se_arma_desde_el_catalogo`), midiendo que cambie
    cuando el catálogo cambia.
    """
    if isinstance(salida, bytes) and salida[:2] == b"PK":
        import io as _io
        import zipfile
        with zipfile.ZipFile(_io.BytesIO(salida)) as z:
            return z.read("word/document.xml").decode("utf-8")
    return salida


@pytest.mark.parametrize("fn", ["como_html", "como_docx"])
def test_los_formatos_traen_TODAS_las_etapas(exportador, fn):
    """La prueba de que salen del mismo catálogo. Con plantillas separadas,
    agregar una etapa la deja fuera de un formato y nadie se entera."""
    salida = _texto(getattr(exportador, fn)())
    for e in mt.etapas():
        clave = max(re.findall(r"[A-Za-zÁÉÍÓÚáéíóúñ]{5,}", e.titulo), key=len)
        assert clave.lower() in salida.lower(), \
            f"{fn}: falta la etapa {e.orden} ({e.titulo})"


def test_el_pdf_se_arma_desde_el_catalogo(exportador, monkeypatch):
    """El PDF no se puede inspeccionar por texto (streams comprimidos), pero sí
    se puede comprobar que DEPENDE del catálogo: con menos etapas tiene que
    salir más chico. Un PDF con el texto quemado adentro pesaría igual."""
    completo = len(exportador.como_pdf())
    monkeypatch.setattr(mt, "etapas", lambda: mt.ETAPAS[:2])
    recortado = len(exportador.como_pdf())
    assert recortado < completo, \
        "el PDF pesa lo mismo con 2 etapas que con todas: no lee el catálogo"


@pytest.mark.parametrize("fn", ["como_html", "como_docx"])
def test_los_formatos_avisan_que_la_demo_es_sintetica(exportador, fn):
    """El documento se manda a un cliente. Sin la aclaración, los números se
    leen como resultados medidos en producción."""
    assert "ILUSTRATIVAS" in _texto(getattr(exportador, fn)(True))


def test_sin_demo_no_mete_el_disclaimer_de_sintetico(exportador):
    """Control negativo: en una instalación con datos del cliente, decir que
    los datos son sintéticos sería falso.

    Se busca la frase del PIE y no la palabra suelta: «sintéticos» aparece
    también en el texto de la etapa de ProbPago, que habla de los datos de la
    demo y tiene que seguir estando en las dos variantes.
    """
    con_demo, sin_demo = exportador.como_html(True), exportador.como_html(False)
    frase = "esta instalación son SINTÉTICOS"
    assert frase in con_demo
    assert frase not in sin_demo


# --- La API ----------------------------------------------------------------
@pytest.fixture()
def cliente(monkeypatch, tmp_path):
    import importlib
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("KOBRA_MODO_STANDALONE", "1")
    from kobra import config as kconfig
    importlib.reload(kconfig)
    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    cli = TestClient(api.app)
    cli.headers.update({
        "Authorization": f"Bearer {api._emitir_token('admin', api.EMPRESA_DEFAULT)}"})
    return cli


def test_la_api_devuelve_las_etapas_en_orden(cliente):
    r = cliente.get("/api/memoria-tecnica")
    assert r.status_code == 200
    etapas = r.json()["etapas"]
    assert [e["orden"] for e in etapas] == list(range(1, len(etapas) + 1))
    assert etapas[0]["criollo"] and etapas[0]["tecnico"]


@pytest.mark.parametrize("formato,firma", [
    ("html", b"<!doctype"), ("docx", b"PK"), ("pdf", b"%PDF-")])
def test_los_tres_exports_se_descargan(cliente, formato, firma):
    r = cliente.get(f"/api/memoria-tecnica/export.{formato}")
    assert r.status_code == 200, r.text[:200]
    assert r.content.startswith(firma)
    assert "attachment" in r.headers["content-disposition"]
    assert formato in r.headers["content-disposition"]


def test_un_formato_inventado_da_400_y_dice_cuales_hay(cliente):
    """Un 500 acá manda a alguien a leer logs por un error de tipeo."""
    r = cliente.get("/api/memoria-tecnica/export.rtf")
    assert r.status_code == 400
    assert "html" in r.json()["detail"] and "pdf" in r.json()["detail"]


def test_sin_sesion_no_se_lee_ni_se_exporta():
    """Describe cómo funciona el producto por dentro: no es información
    pública."""
    import importlib

    from fastapi.testclient import TestClient

    from webapp.backend import api
    importlib.reload(api)
    anon = TestClient(api.app)
    for ruta in ("/api/memoria-tecnica", "/api/memoria-tecnica/export.pdf"):
        assert anon.get(ruta).status_code in (401, 403), f"{ruta} quedó abierta"
