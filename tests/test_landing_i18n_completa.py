# © 2026 Martín Viera. Todos los derechos reservados.
"""Eje DISEÑO: la landing dice lo mismo en los tres idiomas.

El cuerpo de la landing está escrito en español y cada nodo traducible lleva
un `data-i="clave"`; el diccionario `var I18N={pt:{…},en:{…}}` al final del
archivo tiene la traducción de cada clave. Nada verificaba esa
correspondencia, y se notó: la bajada de la sección de PRECIOS (`sl3`) estaba
traducida a medias —

    es  "…al tipo de cambio del día. Al confirmarse el pago, descargás el
         programa con todo incluido."
    pt  "…na cotação do dia. Ao confirmar o pagamento,"
    en  "…at the day's exchange rate. Once payment clears,"

— o sea que un visitante en portugués o en inglés llegaba a la sección donde
se decide la compra y leía una oración que se cortaba en seco después de la
coma. Estaba así en producción.

Estos tests fijan tres cosas: que ninguna clave usada en el cuerpo se quede
sin traducir, que ninguna traducción termine cortada, y que las funciones que
se fueron sumando a la plataforma se anuncien en los tres idiomas y no solo
en español.
"""
import os
import re
from html.parser import HTMLParser

from kobra import rutas as krutas

LANDING = os.path.join(krutas.ROOT_REPO, "landing", "index.html")
IDIOMAS = ("pt", "en")


def _leer():
    with open(LANDING, encoding="utf-8") as f:
        return f.read()


class _Cosecha(HTMLParser):
    """Junta el texto en español de cada nodo con `data-i`."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.textos = {}
        self._pila = []

    def handle_starttag(self, tag, attrs):
        clave = dict(attrs).get("data-i")
        if clave is not None:
            self._pila.append([clave, []])

    def handle_data(self, data):
        if self._pila:
            self._pila[-1][1].append(data)

    def handle_endtag(self, tag):
        if self._pila:
            clave, partes = self._pila.pop()
            texto = re.sub(r"\s+", " ", "".join(partes)).strip()
            # Un nodo puede cerrar hijos antes que a sí mismo; nos quedamos con
            # la versión más larga vista para esa clave.
            if len(texto) > len(self.textos.get(clave, "")):
                self.textos[clave] = texto


def _es():
    c = _Cosecha()
    c.feed(_leer())
    return {k: v for k, v in c.textos.items() if v}


def _diccionario(idioma):
    """El objeto `pt:{…}` / `en:{…}` de `var I18N`, leído como texto.

    No se evalúa como JS: alcanza con recortar el bloque del idioma y sacarle
    los pares `clave:"valor"`, respetando las comillas escapadas."""
    html = _leer()
    inicio = html.index("var I18N=")
    bloque = html[inicio:]
    m = re.search(rf"\n\s*{idioma}:\{{", bloque)
    assert m, f"no está el diccionario de {idioma}"
    # Desde la llave de apertura hasta la que la cierra, contando anidamiento.
    i = m.end() - 1
    nivel, j, en_texto, escape, comilla = 0, i, False, False, ""
    while j < len(bloque):
        ch = bloque[j]
        if en_texto:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == comilla:
                en_texto = False
        elif ch in "\"'":
            en_texto, comilla = True, ch
        elif ch == "{":
            nivel += 1
        elif ch == "}":
            nivel -= 1
            if nivel == 0:
                break
        j += 1
    cuerpo = bloque[i : j + 1]
    pares = re.findall(r'([A-Za-z0-9_]+)\s*:\s*(["\'])((?:\\.|(?!\2).)*)\2', cuerpo)
    return {k: v.replace('\\"', '"').replace("\\'", "'") for k, _q, v in pares}


def test_ninguna_clave_del_cuerpo_se_quedo_sin_traducir():
    es = _es()
    assert len(es) > 80, f"se leyeron solo {len(es)} claves: el parser no está viendo la página"
    for idioma in IDIOMAS:
        dic = _diccionario(idioma)
        faltan = sorted(k for k in es if not dic.get(k, "").strip())
        assert not faltan, (
            f"{idioma}: sin traducir {faltan} — el visitante ve esas partes en español")


def test_ninguna_traduccion_quedo_cortada_a_mitad_de_frase():
    """Terminar en coma donde el español no termina así es la firma de una
    traducción que se copió a medias.

    Es el error exacto que tenía `sl3`: se tradujo hasta donde el original
    cortaba de línea y el resto de la oración nunca se copió. La comparación
    es contra el español y no absoluta porque hay etiquetas que legítimamente
    terminan en dos puntos («Medios de pago:»)."""
    corte = (",", ";", ":")
    es = _es()
    for idioma in IDIOMAS:
        for clave, valor in _diccionario(idioma).items():
            if es.get(clave, "").rstrip().endswith(corte):
                continue
            assert not valor.rstrip().endswith(corte), (
                f"{idioma}.{clave} termina cortada: …{valor[-70:]!r}")


def test_ninguna_traduccion_es_una_fraccion_del_original():
    """Una traducción de menos de la mitad del largo del original casi siempre
    es texto perdido, no una lengua más compacta (pt y en no comprimen tanto
    al español)."""
    es = _es()
    for idioma in IDIOMAS:
        dic = _diccionario(idioma)
        for clave, original in es.items():
            if len(original) < 60:
                continue          # frases cortas: la varianza de largo es normal
            traducido = dic.get(clave, "")
            assert len(traducido) >= len(original) * 0.5, (
                f"{idioma}.{clave} mide {len(traducido)} contra {len(original)} del "
                f"español — parece que se perdió texto: {traducido!r}")


def test_lo_nuevo_de_la_plataforma_se_anuncia_en_los_tres_idiomas():
    """Cuentas por cobrar y el portal de pagos son las dos funciones que se
    sumaron después del lanzamiento. Si solo se anuncian en español, para dos
    de cada tres visitantes la plataforma no las tiene."""
    es = _es()
    assert "cuentas por cobrar" in es["vnuevo"].lower()
    assert "portal de pagos" in es["vnuevo"].lower()
    esperado = {
        "pt": ("contas a receber", "portal de pagamentos"),
        "en": ("accounts receivable", "payment portal"),
    }
    for idioma, frases in esperado.items():
        aviso = _diccionario(idioma)["vnuevo"].lower()
        for frase in frases:
            assert frase in aviso, f"{idioma}: la novedad no menciona «{frase}»: {aviso!r}"


def test_precios_aclara_en_los_tres_idiomas_que_la_licencia_no_se_pierde():
    """El webhook de MercadoPago existe para que cerrar la pestaña no deje al
    comprador sin licencia. Es una garantía de compra: tiene que estar escrita
    donde se decide comprar, en el idioma del que compra."""
    es = _es()["sl3"].lower()
    assert "no se pierde" in es and "pestaña" in es
    for idioma, marcas in {"pt": ("não se perde", "aba"), "en": ("not lost", "tab")}.items():
        bajada = _diccionario(idioma)["sl3"].lower()
        for marca in marcas:
            assert marca in bajada, f"{idioma}: la bajada de precios no dice «{marca}»: {bajada!r}"
