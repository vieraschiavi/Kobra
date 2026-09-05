# © 2026 Martín Viera. Todos los derechos reservados.

"""Borrar releases viejas sin borrar la que sostiene una descarga.

El repo juntó 20 releases y ~20 GB, casi todo duplicación. Borrarlas de a una
desde la web es media hora de clics, y un clic distraído borra la equivocada:
si cae la release que sirve `MVKobraAI_Setup.exe`, el cliente que pagó abre el
link del mail y encuentra un 404.

Por eso lo que se fija acá no es "borra", sino **qué no puede borrar nunca**:

  * el repo público de descargas, ni por accidente ni por parámetro;
  * la release de la versión actual;
  * la más nueva de cada familia (cliente y owner);
  * nada, mientras no se pida explícitamente `--ejecutar`.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "packaging"))

import limpiar_releases as limpiador  # noqa: E402


def _rel(tag, publicado, assets_mb=0):
    return {"tag_name": tag, "id": abs(hash(tag)) % 10**6,
            "published_at": publicado,
            "assets": [{"name": f"{tag}.exe", "id": 1,
                        "size": int(assets_mb * 1e6)}] if assets_mb else []}


@pytest.fixture()
def catalogo():
    """Un repo como el real: viejas, la última de cliente y la de owner."""
    return [
        _rel("v1.3.0", "2026-07-09T00:00:00Z", 260),
        _rel("v1.4.0", "2026-08-12T15:15:00Z", 260),
        _rel("v1.5.0", "2026-08-18T11:22:00Z", 258),
        _rel("owner-v1.3.9", "2026-08-12T12:17:00Z", 1070),
        _rel("owner-v1.4.0", "2026-08-12T15:08:00Z", 1070),
    ]


# --- Lo que no puede borrar nunca ------------------------------------------
def test_no_borra_la_release_de_la_version_actual(catalogo):
    """La que sirve la descarga viva. Aunque figure en la lista."""
    borrar, avisos = limpiador.plan(catalogo, "1.5.0")
    tags = [r["tag_name"] for r in borrar]
    assert "v1.5.0" not in tags


def test_no_borra_la_mas_nueva_de_cada_familia(catalogo):
    """Si se borraran todas las owner, el dueño se queda sin ninguna. Y si se
    borrara la última de cliente, la landing apunta a un 404."""
    borrar, _ = limpiador.plan(catalogo, "9.9.9")   # versión que no existe
    tags = [r["tag_name"] for r in borrar]
    assert "v1.5.0" not in tags, "borró la release de cliente más nueva"
    assert "owner-v1.4.0" not in tags, "borró la release owner más nueva"


def test_la_proteccion_usa_la_fecha_y_no_el_numero(catalogo):
    """Comparar versiones como texto ordena mal en cuanto aparece un v1.10.0,
    y equivocarse acá borra la release que sostiene la descarga."""
    catalogo.append(_rel("v1.10.0", "2026-09-01T00:00:00Z", 258))
    protegidas = limpiador._mas_nueva_por_familia(catalogo)
    assert "v1.10.0" in protegidas, \
        "con orden alfabético, v1.5.0 le gana a v1.10.0 y se borra la nueva"


def test_borra_las_viejas_que_si_corresponden(catalogo):
    borrar, _ = limpiador.plan(catalogo, "1.5.0")
    tags = {r["tag_name"] for r in borrar}
    assert {"v1.3.0", "v1.4.0", "owner-v1.3.9"} <= tags


def test_una_release_que_ya_no_esta_no_es_un_error(catalogo):
    """Correrlo dos veces tiene que ser inofensivo."""
    borrar, avisos = limpiador.plan([c for c in catalogo
                                     if c["tag_name"] != "v1.3.0"], "1.5.0")
    assert "v1.3.0" not in [r["tag_name"] for r in borrar]
    assert any("v1.3.0" in a and "ya no existe" in a for a in avisos)


# --- El repo público, ni por accidente -------------------------------------
def test_se_niega_a_tocar_el_repo_publico_de_descargas(monkeypatch):
    """De ahí baja el cliente que pagó. Una release borrada ahí es un link
    roto en un mail ya enviado."""
    monkeypatch.setenv("GH_TOKEN", "no-se-usa")
    with pytest.raises(SystemExit) as e:
        limpiador.main(["--repo", "vieraschiavi/mv-kobra-ai-releases",
                        "--ejecutar"])
    assert "público" in str(e.value).lower() and "404" in str(e.value)


def test_el_repo_por_defecto_es_el_privado():
    assert limpiador.REPO == "vieraschiavi/Kobra"
    assert limpiador.REPO_PROHIBIDO == "mv-kobra-ai-releases"


# --- Simula salvo que se le pida lo contrario ------------------------------
def test_sin_ejecutar_no_manda_ningun_DELETE(monkeypatch, catalogo, capsys):
    """La guarda que hace que probarlo sea gratis."""
    llamadas = []

    def _falso(ruta, token, metodo="GET"):
        llamadas.append((metodo, ruta))
        # Página 1 y después vacío, igual que la API real.
        #
        # `endswith` y no `in`: dos versiones de este mock colgaron el test.
        # La primera devolvía el catálogo para cualquier página; la segunda
        # buscaba `"page=1"` como substring, que también matchea adentro de
        # `per_page=100` — así que TODA página traía resultados y el bucle de
        # paginación giraba para siempre. Un test que cuelga es peor que uno
        # que falla: no dice qué está mal, y hay que matarlo a mano.
        return catalogo if ruta.endswith("page=1") else []

    monkeypatch.setenv("GH_TOKEN", "t")
    monkeypatch.setattr(limpiador, "_api", _falso)
    limpiador.main([])
    assert not [c for c in llamadas if c[0] == "DELETE"], \
        f"simulando mandó borrados: {llamadas}"
    assert "SIMULACIÓN" in capsys.readouterr().out


def test_con_ejecutar_borra_por_id(monkeypatch, catalogo):
    borrados = []

    def _falso(ruta, token, metodo="GET"):
        if metodo == "DELETE":
            borrados.append(ruta)
            return None
        return catalogo if ruta.endswith("page=1") else []

    monkeypatch.setenv("GH_TOKEN", "t")
    monkeypatch.setattr(limpiador, "_api", _falso)
    limpiador.main(["--ejecutar"])
    assert borrados, "con --ejecutar no borró nada"
    for r in catalogo:
        if r["tag_name"] in ("v1.5.0", "owner-v1.4.0"):
            assert not any(str(r["id"]) in b for b in borrados), \
                f"borró una release protegida: {r['tag_name']}"


def test_sin_token_no_hace_nada(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with pytest.raises(SystemExit) as e:
        limpiador.main([])
    assert "token" in str(e.value).lower()


# --- La lista es explícita, no una regla que se puede equivocar ------------
def test_la_lista_a_borrar_esta_escrita_a_mano():
    """Una regla tipo «todo lo menor a X» borra en silencio lo que no debe
    cuando el esquema de versiones cambia. La lista se revisa de un vistazo."""
    assert isinstance(limpiador.A_BORRAR, list)
    assert all(isinstance(t, str) for t in limpiador.A_BORRAR)
    assert "v1.5.0" not in limpiador.A_BORRAR, \
        "la release de cliente viva está en la lista de borrado"


def test_no_borra_tags():
    """La API de GitHub borra la release y deja el tag: así se conserva qué
    commit fue cada versión. Que el código no llame a /git/refs/tags."""
    with open(os.path.join(ROOT, "packaging", "limpiar_releases.py"),
              encoding="utf-8") as f:
        codigo = f.read()
    assert "git/refs/tags" not in codigo, "borraría también los tags"
