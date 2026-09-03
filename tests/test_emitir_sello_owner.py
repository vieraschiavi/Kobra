# © 2026 Martín Viera. Todos los derechos reservados.

"""Emitir el sello del dueño sin pelear con la consola.

El pedido, textual: *"no quiero ejecutar esto es incómodo"*, sobre

    KOBRA_LICENSE_PRIVATE_KEY=... python -c \\
      "from backend_venta import licencias as l; print(l.emitir_sello_owner())"

Tres cosas lo hacían incómodo, y las tres eran evitables:

  * las comillas anidadas — en `cmd` hay que escaparlas y es donde se rompe;
  * una clave RSA de varias líneas metida en una variable de entorno, que
    `set` de Windows no conserva;
  * el token saliendo por pantalla para copiarlo a mano, que es justo el paso
    donde se corta y produce un instalador que pide licencia.

Los tres se cierran igual: la clave se lee de un `.pem` y el token se escribe
DIRECTO al archivo donde lo busca el build. Lo que se fija acá es eso, más lo
que no puede aflojarse por hacerlo cómodo.
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "packaging"))

import emitir_sello_owner as emisor  # noqa: E402

from kobra import edicion as kedicion  # noqa: E402

BAT = os.path.join(ROOT, "packaging", "generar_sello_owner.bat")
BAT_BUILD = os.path.join(ROOT, "packaging", "construir_instalador.bat")


def _texto(ruta):
    with open(ruta, encoding="utf-8-sig") as f:
        return f.read()


@pytest.fixture()
def pem(tmp_path, par_owner):
    """La privada del par de prueba, en un `.pem` como el que va a arrastrar
    el dueño sobre el .bat."""
    ruta = tmp_path / "privada.pem"
    ruta.write_text(par_owner, encoding="utf-8")
    return str(ruta)


# --- El recorrido completo, con el código real ------------------------------
def test_emite_un_sello_que_el_programa_acepta(tmp_path, pem, monkeypatch):
    """La prueba de fondo: se emite, y el sello emitido activa la edición del
    dueño por el mismo camino que corre al arrancar el programa."""
    monkeypatch.delenv("KOBRA_OWNER_TOKEN", raising=False)
    destino = tmp_path / "sello_owner.txt"
    assert emisor.main(["--clave", pem, "--destino", str(destino)]) == 0

    token = destino.read_text(encoding="utf-8").strip()
    (tmp_path / "edicion.json").write_text(
        '{"edition":"Owner","plan":null,"dias":null,"owner":true,'
        f'"token_owner":"{token}"}}', encoding="utf-8")
    assert kedicion.activar(str(tmp_path))["owner"] is True
    v = kedicion.vigencia()
    assert v["ok"] and v["owner"] and v["dias_restantes"] is None


def test_el_sello_lo_lee_el_sellador_sin_tocar_nada(tmp_path, pem, monkeypatch):
    """Las dos mitades tienen que encajar: lo que escribe el emisor es
    exactamente lo que el build va a buscar. Si no, el dueño hace los dos
    pasos bien y el segundo dice que falta el sello."""
    import sellar_bundle_owner as sellador
    destino = tmp_path / "sello_owner.txt"
    emisor.main(["--clave", pem, "--destino", str(destino)])

    monkeypatch.delenv("KOBRA_OWNER_SELLO", raising=False)
    monkeypatch.setenv("KOBRA_OWNER_SELLO_ARCHIVO", str(destino))
    bundle = tmp_path / "dist" / "MVKobraAI"
    (bundle / "_internal").mkdir(parents=True)
    assert sellador.main(["--bundle", str(bundle)]) == 0
    assert kedicion.sello_owner_valido(
        kedicion.leer(str(bundle / "_internal")))


# --- Lo que no se afloja por hacerlo cómodo --------------------------------
def test_sin_clave_no_emite_nada(tmp_path, monkeypatch):
    monkeypatch.delenv("KOBRA_LICENSE_PRIVATE_KEY", raising=False)
    destino = tmp_path / "sello_owner.txt"
    with pytest.raises(SystemExit) as e:
        emisor.main(["--destino", str(destino)])
    assert "clave privada" in str(e.value)
    assert not destino.exists(), "creó un archivo de sello vacío"


def test_una_clave_de_otro_par_se_rechaza_antes_de_guardar(tmp_path, par_owner):
    """Firmar con una clave vieja da un token perfectamente válido que el
    programa NO acepta. Detectarlo acá evita descubrirlo después de compilar
    el instalador."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    otra = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ruta = tmp_path / "otra.pem"
    ruta.write_text(otra.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode(), encoding="utf-8")

    destino = tmp_path / "sello_owner.txt"
    with pytest.raises(SystemExit) as e:
        emisor.main(["--clave", str(ruta), "--destino", str(destino)])
    assert "NO lo acepta" in str(e.value)
    assert not destino.exists(), "guardó un sello que el programa rechaza"


def test_la_publica_no_sirve_para_firmar(tmp_path):
    """Confundir la pública con la privada es el error fácil: las dos son
    `.pem` y están al lado. Que lo diga, en vez de un error de criptografía."""
    from backend_venta import licencia_clave
    ruta = tmp_path / "publica.pem"
    ruta.write_text(licencia_clave.PUBLICA, encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        emisor.main(["--clave", str(ruta), "--destino", str(tmp_path / "s.txt")])
    assert "no parece una clave privada" in str(e.value)


def test_no_imprime_ni_la_clave_ni_el_sello(tmp_path, pem, capsys, par_owner):
    """La salida queda en la consola del dueño y a veces en un log. Las dos
    cosas son credenciales."""
    destino = tmp_path / "sello_owner.txt"
    emisor.main(["--clave", pem, "--destino", str(destino)])
    salida = capsys.readouterr()
    todo = salida.out + salida.err
    assert destino.read_text(encoding="utf-8").strip() not in todo, \
        "el sello salió por pantalla"
    assert "PRIVATE KEY" not in todo, "la clave salió por pantalla"


def test_no_deja_la_clave_en_el_entorno(tmp_path, pem, monkeypatch):
    """`emitir_sello_owner` de backend_venta lee la privada del entorno, así
    que hay que ponerla ahí un instante. Que no quede después: cualquier
    subproceso que se lance la heredaría."""
    monkeypatch.delenv("KOBRA_LICENSE_PRIVATE_KEY", raising=False)
    emisor.main(["--clave", pem, "--destino", str(tmp_path / "s.txt")])
    assert os.environ.get("KOBRA_LICENSE_PRIVATE_KEY") is None


def test_el_sello_no_se_guarda_dentro_del_repo():
    """Por defecto va al perfil del usuario. Dentro del repo sería una
    credencial a un `git add -A` de distancia."""
    destino = os.path.abspath(emisor.DESTINO_POR_DEFECTO)
    assert not destino.startswith(os.path.abspath(ROOT) + os.sep), \
        f"el sello se guardaría dentro del repo: {destino}"


def test_no_ofrece_generar_un_par_nuevo():
    """Rotar la clave invalida TODAS las licencias ya vendidas. Que eso no
    esté a un clic de distancia dentro de un script de build."""
    codigo = _texto(os.path.join(ROOT, "packaging", "emitir_sello_owner.py"))
    assert "generate_private_key" not in codigo
    assert "invalida" in codigo.lower() or "invalidar" in codigo.lower()


# --- Que el dueño no tenga que tipear el one-liner nunca más ---------------
def test_el_bat_existe_y_es_de_doble_clic():
    bat = _texto(BAT)
    assert "emitir_sello_owner.py" in bat
    assert "pause" in bat, "sin pause la ventana se cierra y no se lee nada"


def test_el_bat_acepta_la_clave_arrastrada():
    """Arrastrar el .pem sobre el .bat es el camino más corto que existe en
    Windows."""
    assert 'set "CLAVE=%~1"' in _texto(BAT)


def test_el_bat_deja_la_variable_puesta_para_la_proxima_consola():
    """`set` se pierde al cerrar la ventana; el build corre en OTRA. Sin
    `setx`, el dueño hace este paso bien y el siguiente le dice que falta el
    sello."""
    bat = _texto(BAT)
    assert "setx KOBRA_OWNER_SELLO_ARCHIVO" in bat


def test_el_bat_dice_de_donde_sacar_la_clave():
    """La privada vive en el servidor de ventas, no en la PC: sin esta pista
    el mensaje "falta la clave" no le sirve ni al dueño."""
    bat = _texto(BAT)
    assert "KOBRA_LICENSE_PRIVATE_KEY" in bat and "Vercel" in bat


def test_el_bat_no_imprime_la_clave_ni_el_sello():
    """Un `echo` de la ruta está bien; un `type` del archivo o un `echo` de
    la variable dejaría la credencial en pantalla."""
    for linea in _texto(BAT).splitlines():
        limpia = linea.strip().lower()
        if limpia.startswith("type ") or limpia.startswith("echo %kobra_license"):
            pytest.fail(f"el .bat muestra una credencial: {linea.strip()}")


def test_el_build_ya_no_manda_a_tipear_el_one_liner():
    """El mensaje del build apuntaba al `python -c` con comillas anidadas.
    Ahora apunta al .bat que hace todo."""
    bat = _texto(BAT_BUILD)
    assert "generar_sello_owner.bat" in bat
    assert "python -c" not in bat, "sigue mandando a tipear el one-liner"


@pytest.mark.parametrize("ruta", [BAT])
def test_el_bat_es_ejecutable_por_cmd(ruta):
    with open(ruta, "rb") as f:
        crudo = f.read()
    assert not crudo.startswith(b"\xef\xbb\xbf"), "tiene BOM"
    assert b"\r\n" in crudo, "no tiene saltos de Windows"
    assert b"\r\r\n" not in crudo, "tiene doble CR"


def test_ningun_echo_desbalancea_el_bloque(ruta=BAT):
    """Un `)` de más dentro de un `echo` cierra el `if (` que lo rodea y las
    líneas siguientes pasan a ejecutarse siempre."""
    malas = []
    for n, linea in enumerate(_texto(ruta).splitlines(), 1):
        limpia = linea.strip()
        if not limpia.lower().startswith("echo "):
            continue
        cuerpo, saldo = limpia[5:], 0
        for i, c in enumerate(cuerpo):
            if i and cuerpo[i - 1] == "^":
                continue
            saldo += (c == "(") - (c == ")")
            if saldo < 0:
                break
        if saldo != 0:
            malas.append(f"{n}: {limpia}")
    assert not malas, "parentesis desbalanceados:\n" + "\n".join(malas)
