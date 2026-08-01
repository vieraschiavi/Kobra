"""Eje DISEÑO: la landing nombra, con nombre propio, lo que la hace creíble.

Antes, las tres menciones de integración de la landing eran genéricas —"tu
ERP", "por WhatsApp", "Hasta 50 llamadas"— sin decir nunca qué ERP, qué
proveedor de voz, ni qué motores de base de datos soporta de verdad. El
código sí lo dice: `kobra/integracion.py` documenta connection strings reales
de PostgreSQL, MySQL, SQL Server y SQLite; el README documenta con detalle
técnico que la voz se conecta por Avaya/Genesys/Cisco/Asterisk (SIPREC/AES/
DMCC) o por Twilio. Estos tests fijan que la landing cite eso — lo real, no
más — en los tres idiomas.
"""
import os
import re

from kobra import rutas as krutas

LANDING = os.path.join(krutas.ROOT_REPO, "landing", "index.html")

# Nombres concretos que el código respalda de verdad (ver kobra/integracion.py
# y el README, sección "Integración con telefonía"). No incluye Oracle: no
# está documentado ni probado acá, así que no se promete.
MOTORES_DB = ("PostgreSQL", "MySQL", "SQL Server", "SQLite")
PLATAFORMAS_VOZ = ("Avaya", "Genesys", "Cisco", "Asterisk", "Twilio")


def _leer():
    with open(LANDING, encoding="utf-8") as f:
        return f.read()


def test_el_cuerpo_en_espanol_nombra_los_motores_de_base_de_datos():
    """El español vive directo en el HTML (no en el diccionario I18N)."""
    html = _leer()
    ini = html.index('data-i="f4p"')
    bloque = html[ini:ini + 300]
    faltan = [m for m in MOTORES_DB if m not in bloque]
    assert not faltan, f"la tarjeta de integración no nombra: {faltan}"


def test_el_cuerpo_en_espanol_nombra_las_plataformas_de_voz():
    html = _leer()
    ini = html.index('data-i="f1p"')
    bloque = html[ini:ini + 300]
    faltan = [m for m in PLATAFORMAS_VOZ if m not in bloque]
    assert not faltan, f"la tarjeta de voz no nombra: {faltan}"


def _bloque_i18n(html, lang, clave):
    ini = html.index(f"{lang}:{{" if False else f"  {lang}:{{")
    fin = html.index("\n};", ini)
    seccion = html[ini:fin]
    m = re.search(re.escape(clave) + r':"', seccion)
    assert m, f"no encontré la clave {clave} en I18N.{lang}"
    return seccion[m.start():m.start() + 400]


def test_portugues_e_ingles_tambien_nombran_los_motores_de_base_de_datos():
    html = _leer()
    for lang in ("pt", "en"):
        bloque = _bloque_i18n(html, lang, "f4p")
        faltan = [m for m in MOTORES_DB if m not in bloque]
        assert not faltan, f"I18N.{lang}.f4p no nombra: {faltan}"


def test_portugues_e_ingles_tambien_nombran_las_plataformas_de_voz():
    html = _leer()
    for lang in ("pt", "en"):
        bloque = _bloque_i18n(html, lang, "f1p")
        faltan = [m for m in PLATAFORMAS_VOZ if m not in bloque]
        assert not faltan, f"I18N.{lang}.f1p no nombra: {faltan}"


def test_no_se_promete_un_motor_que_el_codigo_no_soporta():
    """Nombrar de más es peor que nombrar de menos: Oracle no está en
    `kobra/integracion.py`, así que la landing no puede prometerlo."""
    html = _leer()
    assert "Oracle" not in html, (
        "la landing promete Oracle, que kobra/integracion.py no soporta")


def test_kobra_integracion_respalda_los_motores_que_se_nombran():
    """Que no se invente la lista: los cuatro tienen que estar en el código
    real que sincroniza, no solo en el texto de marketing."""
    with open(os.path.join(krutas.ROOT_REPO, "kobra", "integracion.py"),
              encoding="utf-8") as f:
        codigo = f.read().lower()
    for motor, pista in [("PostgreSQL", "postgresql"), ("MySQL", "mysql"),
                         ("SQL Server", "mssql"), ("SQLite", "sqlite")]:
        assert pista in codigo, f"{motor} se nombra en la landing pero no en integracion.py"
