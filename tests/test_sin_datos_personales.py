# © 2026 Martín Viera. Todos los derechos reservados.

"""Que no entren datos personales reales al repositorio.

`vieraschiavi/Kobra` es un repositorio **público**. Un celular uruguayo
commiteado acá queda indexado por Google y lo levantan los bots que rastrean
GitHub buscando exactamente eso; un número de cuenta bancaria publicado es
directamente material de fraude. Y la regla del proyecto es explícita: datos
siempre sintéticos, nunca PII (CLAUDE.md, Ley 18.331).

Esto no es teórico. Un celular real estuvo commiteado en
`webapp/backend/api.py` dentro de `_DEUDOR_DEMO_GESTOR`, con el comentario
"deudor sintético" al lado — precisamente el caso que un test como este
detecta y una revisión a ojo deja pasar.

Cuando la demostración tiene que llamar a un teléfono de verdad, el número
sale de la configuración cifrada de la máquina (`kobra/demo_vivo.py`), que
vive fuera del repositorio.
"""
import os
import re
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Extensiones donde buscar. Los binarios y los datos generados quedan afuera.
EXTS = (".py", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".json",
        ".md", ".bat", ".sh", ".ps1", ".yml", ".yaml", ".txt")

# Lo que NO se busca: dependencias, artefactos de build y material de
# referencia que no es código nuestro.
EXCLUIR = ("node_modules/", "/dist/", "ui_dist/", "referencia_R/", ".min.js",
           "package-lock.json", "chart.umd", "xlsx.full", "botid-init.js")

# Un número "claramente inventado": el prefijo 099000xxx que usan las
# plantillas, el rango 555 reservado para ficción, o un patrón evidente de
# dato de prueba —dígitos repetidos (99000000, 99111111) o una secuencia
# (123456)—. Un celular de verdad no se ve así, y ese es justamente el punto:
# lo que el test busca es el que NO se ve así.
_SINTETICOS = re.compile(
    r"099000\d{3}"                 # plantillas del repo
    r"|555[\s.-]?\d{3}"            # rango reservado para ficción
    r"|(\d)\1{5,}"                 # 000000, 111111, 999999…
    r"|123456|111222|333444"       # secuencias y pares obvios de test
)

# Un celular uruguayo: 09X con X de 1 a 9, más seis dígitos. En formato
# nacional (098576279) o internacional (+59898576279).
_CELULAR_NACIONAL = re.compile(r"(?<!\d)09[1-9]\d{6}(?!\d)")
_CELULAR_INTERNACIONAL = re.compile(r"\+?598\s?9[1-9][\s.-]?\d{3}[\s.-]?\d{3}")


def _archivos():
    salida = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.splitlines()
    for rel in salida:
        if not rel.endswith(EXTS) or any(x in rel for x in EXCLUIR):
            continue
        ruta = os.path.join(ROOT, rel)
        if not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, encoding="utf-8", errors="ignore") as f:
                yield rel, f.read()
        except OSError:
            continue


@pytest.mark.parametrize("patron,que", [
    (_CELULAR_NACIONAL, "celular uruguayo (formato nacional)"),
    (_CELULAR_INTERNACIONAL, "celular uruguayo (formato internacional)"),
])
def test_no_hay_celulares_reales(patron, que):
    """Los números de ejemplo van con 099000xxx o el rango 555; cualquier otro
    celular uruguayo en el código es, muy probablemente, el de alguien."""
    hallazgos = []
    for rel, texto in _archivos():
        for linea_n, linea in enumerate(texto.splitlines(), 1):
            for m in patron.finditer(linea):
                if _SINTETICOS.search(m.group(0)):
                    continue
                hallazgos.append(f"{rel}:{linea_n} → {m.group(0)}")
    assert not hallazgos, (
        f"hay {que} en el repositorio, que es público:\n  " + "\n  ".join(hallazgos) +
        "\n\nLos números reales van en la configuración cifrada de la máquina "
        "(kobra/demo_vivo.py), nunca en el código.")


# Sobre los correos: acá había un cuarto test que los buscaba, y se sacó
# porque daba más ruido que valor. El mail del dueño está a propósito en
# `kobra/owner.py` (es el identificador de su credencial, no un secreto) y en
# los endpoints que le avisan de una venta — es su propio mail en su propio
# producto—, y distinguir "mail de un tercero" de "mail del dueño" o de una
# versión de paquete (`chart.js@4.4.1` matchea cualquier patrón de correo
# razonable) no se puede hacer sin una lista de excepciones que crece sola.
# Un test que hay que silenciar seguido termina desactivado; los tres que
# quedan disparan solo cuando hay algo de verdad.

def test_no_hay_numeros_de_cuenta_bancaria():
    """Una cuenta bancaria publicada es material de fraude. La de la demo sale
    de la configuración del portal, que vive en la carpeta de datos."""
    # Una cuenta uruguaya: 6 a 14 dígitos SEGUIDOS cerca de la palabra cuenta.
    # El `\D{0,12}` no puede tragarse letras pegadas al número, o "contactar
    # KB-100773" (un id de deudor) se lee como una cuenta bancaria.
    patron = re.compile(r"(caja de ahorro|cuenta|cta\.?)[\s:.-]{0,6}(\d{6,14})\b", re.I)
    hallazgos = []
    for rel, texto in _archivos():
        if rel.startswith("tests/"):
            continue
        for linea_n, linea in enumerate(texto.splitlines(), 1):
            for m in patron.finditer(linea):
                numero = m.group(2)
                if set(numero) <= {"0"} or numero.startswith("000"):
                    continue          # 0000000 y similares son claramente de ejemplo
                hallazgos.append(f"{rel}:{linea_n} → {m.group(0)[:60]}")
    assert not hallazgos, ("hay números de cuenta en el repositorio:\n  "
                           + "\n  ".join(hallazgos))


def test_el_deudor_de_la_demo_no_tiene_telefono_real():
    """Regresión puntual: `_DEUDOR_DEMO_GESTOR` tenía un celular real con el
    comentario "sintético" al lado."""
    sys.path.insert(0, ROOT)
    with open(os.path.join(ROOT, "webapp", "backend", "api.py"), encoding="utf-8") as f:
        codigo = f.read()
    bloque = codigo[codigo.index("_DEUDOR_DEMO_GESTOR"):][:400]
    tel = re.search(r'"telefono":\s*"([^"]+)"', bloque)
    assert tel, "el deudor de la demo perdió el campo teléfono"
    assert _SINTETICOS.search(tel.group(1)), \
        f"el teléfono del deudor de demo no parece inventado: {tel.group(1)}"


# ---------------------------------------------------------------------------
# CORS: la otra puerta por la que se colaban datos
# ---------------------------------------------------------------------------
def test_cors_no_esta_abierto_a_todo_el_mundo():
    """`allow_origins=["*"]` habilitaba una toma de control concreta.

    La app de escritorio deja el backend escuchando en localhost. Con el CORS
    abierto, cualquier página que el usuario visitara podía hacerle un POST a
    `/api/auth/setup` —el navegador manda preflight por el `Content-Type:
    application/json`, y con `*` el preflight pasaba— y quedarse con el admin
    de una instalación recién hecha, antes de que el dueño configurara su
    contraseña.

    La interfaz se sirve desde el mismo backend, así que el uso normal es
    same-origin y no necesita CORS para nada.
    """
    with open(os.path.join(ROOT, "webapp", "backend", "api.py"), encoding="utf-8") as f:
        # Sin las líneas de comentario: el bloque que documenta este arreglo
        # cita el `allow_origins=["*"]` viejo para explicar por qué se sacó, y
        # sin filtrarlo el comentario que explica el arreglo hace fallar al
        # test que verifica ese mismo arreglo.
        codigo = "\n".join(ln for ln in f.read().splitlines()
                           if not ln.strip().startswith("#"))
    assert 'allow_origins=["*"]' not in codigo, \
        "el CORS volvió a quedar abierto a cualquier origen"


def test_el_preflight_de_un_origen_desconocido_no_pasa(tmp_path, monkeypatch):
    """El gate de verdad: que el servidor no devuelva la cabecera que le
    permite al navegador seguir adelante."""
    import importlib
    monkeypatch.setenv("KOBRA_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("KOBRA_DATA_DIR", str(tmp_path / "datos"))
    monkeypatch.delenv("KOBRA_CORS_ORIGINS", raising=False)
    sys.path.insert(0, ROOT)
    from fastapi.testclient import TestClient

    from kobra import config as kconfig
    importlib.reload(kconfig)
    from webapp.backend import api
    importlib.reload(api)
    c = TestClient(api.app)

    malicioso = "https://sitio-malicioso.invalid"
    r = c.options("/api/auth/setup", headers={
        "Origin": malicioso, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    permitido = r.headers.get("access-control-allow-origin")
    assert permitido not in (malicioso, "*"), \
        f"el servidor le permite el pedido a {malicioso}"

    # Y el origen de desarrollo tiene que seguir funcionando.
    ok = c.options("/api/auth/estado", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
