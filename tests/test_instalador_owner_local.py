# © 2026 Martín Viera. Todos los derechos reservados.

"""El instalador OWNER, construible en la PC del dueño.

(El workflow que lo arma en GitHub lo cubre `test_instalador_owner.py`;
acá se fija la vía local, que es la única disponible sin Actions.)

El pedido: *"mi versión owner no me hagas poner licencia para descargar,
ponele el instalador exe react electron separado para owner sin límites"*.

La edición Owner ya existía —`MVKobraAI_Setup_OWNER.exe`, con appId y carpeta
propios para convivir con la copia de cliente— pero la armaba SOLO
`.github/workflows/release_owner.yml`. Con las Actions del repo sin cupo, no
había ninguna forma de generarla: existía en el papel y no en el disco.

Lo que se fija acá es lo que hace que la construcción local sea confiable y no
un atajo:

  * el sello del dueño se VERIFICA antes de compilar, no después. Un token
    cortado al copiar produce un `edicion.json` de aspecto perfecto que el
    programa rechaza al arrancar: sin este control, el resultado serían veinte
    minutos de compilación y un .exe de 270 MB que pide licencia igual que el
    de un cliente;
  * sin sello no sale NADA. Nunca un instalador Owner a medias;
  * el token no se imprime: es la credencial que convierte cualquier copia en
    la edición sin límites, y la salida del build termina en la consola;
  * hay una sola tubería de compilación para las dos ediciones. Dos .bat
    paralelos se separan a la primera corrección que se haga en uno solo.
"""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "packaging"))

import sellar_bundle_owner as sellador  # noqa: E402

from kobra import edicion as kedicion  # noqa: E402

BAT_CLIENTE = os.path.join(ROOT, "packaging", "construir_instalador.bat")
BAT_OWNER = os.path.join(ROOT, "packaging", "construir_instalador_owner.bat")


@pytest.fixture()
def bundle(tmp_path):
    """El layout que deja PyInstaller 6 en onedir: `_internal/` es `_MEIPASS`."""
    d = tmp_path / "dist" / "MVKobraAI"
    (d / "_internal").mkdir(parents=True)
    (d / "MVKobraAI.exe").touch()
    return d


def _texto(ruta):
    with open(ruta, encoding="utf-8-sig") as f:
        return f.read()


# --- Sin sello no sale un instalador a medias -------------------------------
def test_sin_sello_no_se_escribe_nada(bundle, monkeypatch):
    monkeypatch.delenv("KOBRA_OWNER_SELLO", raising=False)
    monkeypatch.delenv("KOBRA_OWNER_SELLO_ARCHIVO", raising=False)
    with pytest.raises(SystemExit) as e:
        sellador.main(["--bundle", str(bundle)])
    assert "KOBRA_OWNER_SELLO" in str(e.value)
    assert not (bundle / "_internal" / "edicion.json").exists()


def test_un_token_cortado_se_detecta_antes_de_compilar(bundle, monkeypatch, sello_owner):
    """El caso real: se copia el token de un mail y se pierde el último tramo.
    El JSON queda impecable y el programa lo rechaza al arrancar."""
    monkeypatch.setenv("KOBRA_OWNER_SELLO", sello_owner["token_owner"][:-12])
    with pytest.raises(SystemExit) as e:
        sellador.main(["--bundle", str(bundle)])
    assert "no valida" in str(e.value)
    assert not (bundle / "_internal" / "edicion.json").exists(), \
        "escribió un sello que el programa no va a aceptar"


def test_una_licencia_comprada_no_sirve_de_sello(bundle, monkeypatch, par_owner):
    """Una licencia Enterprise valida con la MISMA pública. Si alcanzara para
    sellar, cualquier cliente pago se fabricaría la edición del dueño."""
    import time

    import jwt
    ahora = int(time.time())
    comprada = jwt.encode({"sub": "cliente", "plan": "enterprise",
                           "iat": ahora, "exp": ahora + 365 * 24 * 3600},
                          par_owner, algorithm="RS256")
    monkeypatch.setenv("KOBRA_OWNER_SELLO", comprada)
    with pytest.raises(SystemExit):
        sellador.main(["--bundle", str(bundle)])
    assert not (bundle / "_internal" / "edicion.json").exists()


def test_sin_bundle_compilado_lo_dice(tmp_path, monkeypatch, sello_owner):
    monkeypatch.setenv("KOBRA_OWNER_SELLO", sello_owner["token_owner"])
    with pytest.raises(SystemExit) as e:
        sellador.main(["--bundle", str(tmp_path / "no-existe")])
    assert "PyInstaller" in str(e.value), "no dice cómo compilar el motor"


# --- Con el sello, el .exe que salga es el del dueño ------------------------
def test_el_bundle_sellado_arranca_como_owner(bundle, monkeypatch, sello_owner):
    monkeypatch.setenv("KOBRA_OWNER_SELLO", sello_owner["token_owner"])
    monkeypatch.delenv("KOBRA_OWNER_TOKEN", raising=False)
    assert sellador.main(["--bundle", str(bundle)]) == 0

    # Lo que hace el launcher al abrir la copia instalada, con el código real.
    interno = str(bundle / "_internal")
    assert kedicion.activar(interno)["owner"] is True
    v = kedicion.vigencia()
    assert v["ok"] and v["owner"]
    assert v["dias_restantes"] is None, "una copia owner no puede vencer"


def test_el_sello_va_a_internal_y_no_a_la_raiz(bundle, monkeypatch, sello_owner):
    """`_internal` es `sys._MEIPASS` del bundle congelado. En la raíz el
    programa no lo lee y el instalador sale pidiendo licencia."""
    monkeypatch.setenv("KOBRA_OWNER_SELLO", sello_owner["token_owner"])
    sellador.main(["--bundle", str(bundle)])
    assert (bundle / "_internal" / "edicion.json").exists()
    assert not (bundle / "edicion.json").exists()


def test_el_sello_es_el_mismo_que_escribe_el_ci(bundle, monkeypatch, sello_owner):
    """El CI, `Owner.bat` y esto arman el JSON en un solo lugar: si se
    separaran, la construcción local andaría hoy y se rompería en la próxima
    release sin que nadie lo note."""
    monkeypatch.setenv("KOBRA_OWNER_SELLO", sello_owner["token_owner"])
    sellador.main(["--bundle", str(bundle)])
    escrito = json.loads((bundle / "_internal" / "edicion.json").read_text("utf-8"))
    assert escrito == sello_owner


def test_el_sello_se_puede_dar_en_un_archivo(bundle, tmp_path, monkeypatch, sello_owner):
    """Un JWT de 700 caracteres pegado en una consola de Windows queda en el
    historial de `cmd`. Un archivo suelto fuera del repo se guarda una vez."""
    monkeypatch.delenv("KOBRA_OWNER_SELLO", raising=False)
    archivo = tmp_path / "sello_owner.txt"
    # Como llega de un mail: partido en líneas y con espacios al final.
    t = sello_owner["token_owner"]
    archivo.write_text(f"{t[:40]}\n{t[40:]}\n", encoding="utf-8")
    assert sellador.main(["--bundle", str(bundle),
                          "--sello-archivo", str(archivo)]) == 0
    assert kedicion.sello_owner_valido(
        json.loads((bundle / "_internal" / "edicion.json").read_text("utf-8")))


def test_el_token_no_se_imprime(bundle, monkeypatch, sello_owner, capsys):
    """La salida del build queda en la consola y a veces en un archivo de log.
    El token es la credencial que hace owner a cualquier copia."""
    monkeypatch.setenv("KOBRA_OWNER_SELLO", sello_owner["token_owner"])
    sellador.main(["--bundle", str(bundle)])
    salida = capsys.readouterr()
    assert sello_owner["token_owner"] not in (salida.out + salida.err)


def test_solo_verificar_no_toca_el_bundle(bundle, monkeypatch, sello_owner):
    """Es el control que corre ANTES de compilar: mira el sello sin escribir."""
    monkeypatch.setenv("KOBRA_OWNER_SELLO", sello_owner["token_owner"])
    assert sellador.main(["--bundle", str(bundle), "--solo-verificar"]) == 0
    assert not (bundle / "_internal" / "edicion.json").exists()


# --- El .bat que lo construye en la PC del dueño ----------------------------
def test_el_bat_owner_no_duplica_la_tuberia():
    """Dos tuberías de compilación paralelas se separan a la primera
    corrección que se haga en una sola."""
    bat = _texto(BAT_OWNER)
    assert "construir_instalador.bat" in bat and "owner" in bat
    # Un envoltorio, no una copia: la tubería entera son ~250 líneas.
    assert len(bat.splitlines()) < 30, "el .bat owner recopió la tubería"


def test_el_bat_verifica_el_sello_antes_de_compilar():
    """El orden es el punto: verificar después de PyInstaller no evita nada."""
    bat = _texto(BAT_CLIENTE)
    verificacion = bat.index("--solo-verificar")
    pyinstaller = bat.index("-m PyInstaller")
    assert verificacion < pyinstaller, \
        "verifica el sello después de compilar: no sirve de nada"


def test_el_bat_sella_el_bundle_antes_de_empaquetar():
    """Después de electron-builder ya no hay nada que sellar: el .exe estaría
    hecho y sería el de un cliente con otro nombre."""
    bat = _texto(BAT_CLIENTE)
    sellado = bat.index("sellar_bundle_owner.py --bundle")
    empaquetado = bat.index("--config electron-builder.owner.yml")
    assert sellado < empaquetado


def test_el_bat_usa_la_identidad_separada_del_owner():
    """Con el mismo appId, instalar el owner PISA la copia de cliente: misma
    carpeta, mismos accesos y una sola entrada en Agregar o quitar programas."""
    bat = _texto(BAT_CLIENTE)
    assert "--config electron-builder.owner.yml" in bat
    assert "dist_installer_owner\\MVKobraAI_Setup_OWNER.exe" in bat


def test_el_bat_avisa_como_emitir_el_sello_si_falta():
    """El que corre esto es el dueño en su PC, sin nadie a quien preguntarle.

    Antes el mensaje lo mandaba a tipear un `python -c` con comillas
    anidadas. Ahora apunta al `.bat` que hace todo — el pedido fue textual:
    *"no quiero ejecutar esto es incómodo"*.
    """
    bat = _texto(BAT_CLIENTE)
    assert "KOBRA_OWNER_SELLO_ARCHIVO" in bat
    assert "generar_sello_owner.bat" in bat, "no dice cómo conseguir el sello"
    assert "python -c" not in bat, "sigue mandando a tipear el one-liner"


def test_el_bat_recuerda_que_el_owner_no_va_al_repo_publico():
    """`mv-kobra-ai-releases` es público y esta edición no pide licencia:
    subirla ahí es regalar el producto."""
    assert "mv-kobra-ai-releases" in _texto(BAT_CLIENTE)


def test_el_instalador_de_clientes_sigue_saliendo_igual():
    """Control negativo: la edición por defecto no puede haberse vuelto owner
    por agregar la variante."""
    bat = _texto(BAT_CLIENTE)
    assert 'set "EDICION=cliente"' in bat
    assert 'set "SALIDA=dist_installer\\MVKobraAI_Setup.exe"' in bat


@pytest.mark.parametrize("ruta", [BAT_CLIENTE, BAT_OWNER])
def test_los_bat_no_tienen_lo_que_cmd_no_perdona(ruta):
    """Un BOM y `cmd.exe` directamente no abre el archivo; un `\\r\\r\\n` (de
    escribir los saltos a mano sobre un `newline=""`) lo confunde."""
    with open(ruta, "rb") as f:
        crudo = f.read()
    assert not crudo.startswith(b"\xef\xbb\xbf"), "tiene BOM"
    assert b"\r\r\n" not in crudo, "tiene doble CR"


def test_el_bat_owner_lleva_saltos_de_windows():
    """El envoltorio se genera desde Python justamente para esto: un .bat con
    saltos de Unix y etiquetas `goto` es la forma clásica de que la ventana
    se abra y se cierre sin decir nada."""
    with open(BAT_OWNER, "rb") as f:
        assert b"\r\n" in f.read(), "no tiene saltos de Windows"


def test_el_sello_no_quedo_commiteado():
    """Un token del dueño dentro del repo es la llave del producto. El repo es
    privado, pero un clon en una PC prestada o un colaborador futuro alcanzan.

    Se busca un JWT de verdad (`eyJ…`, el `{"` de la cabecera en base64) y no
    la mención de la variable: los tests y los scripts la nombran a propósito.
    """
    import subprocess
    # Los patrones se ARMAN en vez de escribirse: un `git grep` de la cadena
    # literal encuentra este mismo archivo y el test falla por existir.
    jwt = "ey" + "J"
    for patron in (f"KOBRA_OWNER_SELLO={jwt}", f'token_owner": *"{jwt}'):
        r = subprocess.run(["git", "grep", "-lIE", "-e", patron],
                           cwd=ROOT, capture_output=True, text=True)
        assert not r.stdout.strip(), f"hay un sello firmado en: {r.stdout}"


# --- Los lanzadores que prometían "entra directo" --------------------------
LANZADORES = [os.path.join(ROOT, "owner", n) for n in
              ("MVKobraAI_Owner.bat", "MVKobraAI_Owner_desde_codigo.bat",
               "mvkobraai_owner.sh")]


def test_la_variable_vieja_ya_no_desbloquea_nada():
    """El control que da sentido a todo lo de abajo: `KOBRA_OWNER=1` era lo
    que exportaban los lanzadores, y desde el endurecimiento del sello no
    activa la edición del dueño. Se comprueba con el código real."""
    import subprocess
    r = subprocess.run(
        [sys.executable, "-c",
         "from kobra import edicion; print(edicion.es_owner())"],
        cwd=ROOT, env=dict(os.environ, KOBRA_OWNER="1"),
        capture_output=True, text=True)
    assert r.stdout.strip() == "False", \
        "KOBRA_OWNER=1 volvió a desbloquear: el sello firmado dejó de ser necesario"


def _codigo_efectivo(ruta: str) -> str:
    """El archivo sin comentarios ni `echo`.

    Los comentarios de estos archivos NOMBRAN la variable muerta a propósito
    —explican por qué se fue— y los `echo` la mencionan en los avisos. Mirar
    el texto crudo daba un test que fallaba por la explicación en vez de por
    el código, que es la forma más rápida de que alguien borre el comentario
    para que pase.
    """
    lineas = []
    for linea in _texto(ruta).splitlines():
        limpia = linea.strip()
        if limpia.lower().startswith(("rem ", "::", "#", "echo ")):
            continue
        lineas.append(linea)
    return "\n".join(lineas)


@pytest.mark.parametrize("ruta", LANZADORES)
def test_ningun_lanzador_confia_en_la_variable_muerta(ruta):
    """Prometían «sin licencia, entra directo» y entregaban la pantalla de
    licencia: la peor forma de fallar, porque parece que el programa se rompió."""
    codigo = _codigo_efectivo(ruta)
    for muerta in ("set KOBRA_OWNER=1", "export KOBRA_OWNER=1"):
        assert muerta not in codigo, f"{os.path.basename(ruta)} sigue usando {muerta}"


@pytest.mark.parametrize("ruta", LANZADORES)
def test_cada_lanzador_resuelve_el_sello_firmado(ruta):
    """Directamente o llamando al resolutor común, pero el sello tiene que
    quedar en `KOBRA_OWNER_TOKEN`: es lo único que el programa lee."""
    codigo = _codigo_efectivo(ruta)
    if "sello_owner.bat" in codigo:
        codigo += _codigo_efectivo(os.path.join(ROOT, "owner", "sello_owner.bat"))
    assert "KOBRA_OWNER_TOKEN" in codigo, "no exporta el sello que el programa lee"
    assert "KOBRA_OWNER_SELLO_ARCHIVO" in codigo, "no dice de dónde sacarlo"


@pytest.mark.parametrize("ruta", LANZADORES)
def test_cada_lanzador_avisa_si_no_hay_sello(ruta):
    """Sin sello el programa va a pedir una clave. Que lo diga ANTES, con el
    remedio: en silencio parece un programa roto."""
    texto = _texto(ruta).lower()
    assert "sello" in texto and ("licencia" in texto or "clave" in texto)


def test_el_acceso_directo_del_instalador_tambien():
    """`instalar_windows.ps1 -Owner` escribe el .cmd del ícono del Escritorio.
    Con la variable muerta adentro, el ícono abría el programa y el programa
    pedía una clave."""
    ps1 = _codigo_efectivo(os.path.join(ROOT, "packaging", "instalar_windows.ps1"))
    assert "set KOBRA_OWNER=1" not in ps1
    assert "sello_owner.bat" in ps1


def test_el_resolutor_de_sello_es_uno_solo():
    """Tres copias de la misma resolución se separan a la primera corrección
    que se haga en una sola."""
    resolutor = os.path.join(ROOT, "owner", "sello_owner.bat")
    assert os.path.exists(resolutor)
    for ruta in LANZADORES:
        if ruta.endswith(".bat"):
            assert "sello_owner.bat" in _texto(ruta), \
                f"{os.path.basename(ruta)} no usa el resolutor común"


# --- Parentesis dentro de un bloque `if (` ---------------------------------
BATS_OWNER = [BAT_CLIENTE, BAT_OWNER,
              os.path.join(ROOT, "owner", "sello_owner.bat"),
              os.path.join(ROOT, "owner", "MVKobraAI_Owner.bat"),
              os.path.join(ROOT, "owner", "MVKobraAI_Owner_desde_codigo.bat")]


@pytest.mark.parametrize("ruta", BATS_OWNER)
def test_ningun_echo_desbalancea_el_bloque_que_lo_contiene(ruta):
    """Un `)` de más dentro de un `echo` cierra el `if (` que lo rodea y parte
    el script al medio: las líneas que seguían pasan a ejecutarse SIEMPRE.

    Lo que rompe es el desbalance, no el paréntesis: cmd cuenta los pares
    dentro de un bloque, así que `^(la 1a vez tarda unos minutos^)` y
    `(descarga incluida)` conviven bien. Por eso el test mide el balance y no
    la ausencia — un test que exigiera escapar todo marcaría como rotas líneas
    que funcionan, y el arreglo obvio sería borrar el mensaje.

    Se miran las líneas cuyo statement completo es un `echo`: en la forma
    `if ... ( echo. & pause )` los paréntesis son del bloque, no del texto.
    """
    malas = []
    for n, linea in enumerate(_texto(ruta).splitlines(), 1):
        limpia = linea.strip()
        if not limpia.lower().startswith("echo "):
            continue
        saldo = 0
        for i, c in enumerate(limpia[5:]):
            if i and limpia[5:][i - 1] == "^":
                continue          # escapado: cmd lo imprime, no lo cuenta
            if c == "(":
                saldo += 1
            elif c == ")":
                saldo -= 1
            if saldo < 0:
                break
        if saldo != 0:
            malas.append(f"{os.path.basename(ruta)}:{n}: {limpia}")
    assert not malas, ("parentesis desbalanceados en echo — cierran el bloque "
                       "que los contiene:\n" + "\n".join(malas))



def test_un_sello_con_espacios_de_mas_sigue_valiendo(sello_owner):
    """El token viaja por archivo o por variable de entorno, y ahí se le pega
    un salto de línea o un espacio con facilidad. Antes eso lo invalidaba: la
    copia del dueño abría la pantalla de licencia sin decir por qué."""
    limpio = {**sello_owner}
    assert kedicion.sello_owner_valido(limpio)
    for sucio in (f"{limpio['token_owner']}\n", f" {limpio['token_owner']} ",
                  f"{limpio['token_owner']}\r\n"):
        assert kedicion.sello_owner_valido({**limpio, "token_owner": sucio}), \
            "un espacio de más deja al dueño pidiendo licencia"


def test_un_sello_vacio_o_en_blanco_no_vale(sello_owner):
    """Control negativo: recortar espacios no puede volver válido un sello
    que no trae token."""
    for vacio in ("", "   ", "\n", None, 123):
        assert not kedicion.sello_owner_valido({"token_owner": vacio})
