# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · La película: la demo completa, de la mora al recupero
====================================================================
Los videos de la landing muestran piezas (el Copiloto, la suite). Faltaba la
historia entera para un gerente: la situación de partida —la mora creciendo en
el panel—, la cartera scoreada con ProbPago, el gestor IA por voz y WhatsApp,
el portal de pagos, el tablero conversacional, gobernanza, KPIs propios,
AutoML, logística, proyectos y el cierre en /roi. Un solo video, sin cortes.

Cómo se hace, y por qué así:

* **Se graba la plataforma real** (Playwright contra la app corriendo), igual
  que la suite: lo que se ve es lo que hace el producto, no una animación.
* **Los datos son el escenario de demo "financiera"** de
  `kobra/demo_escenarios.py`: la MISMA empresa sintética, completa y
  determinista, que un prospecto activa desde Configuración. La cartera pasa
  por el scoring real, así que las pantallas muestran probpago, estrategias y
  guiones de verdad — y ningún módulo queda vacío (eso ya lo garantizan sus
  tests).
* **El guion vive en `marketing/subtitulos.py::PELICULA_ESCENAS`**: la misma
  lista define el recorrido de la grabación, los subtítulos en tres idiomas y
  la narración. No hay tres copias que desincronizar.
* **La narración va en castellano** (misma decisión documentada en
  `subtitulos.py`: la interfaz dentro del video está en castellano); los tres
  idiomas viajan por los subtítulos `pelicula.{es,pt,en}.vtt`.

Uso:
    python3 -m marketing.pelicula_demo                   # graba + narra
    python3 -m marketing.pelicula_demo --sin-voz         # solo el screencast
    python3 -m marketing.pelicula_demo --voz es_MX-claude-high
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from marketing.subtitulos import PELICULA_CUES, PELICULA_ESCENAS

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA_DEFAULT = os.path.join(RAIZ, "landing", "video",
                              "MVKobraAI_Pelicula_Demo.webm")

# El recorrido sale del guion: misma fuente que subtítulos y narración.
RECORRIDO = [(ruta, segundos) for ruta, segundos, _ in PELICULA_ESCENAS]
ESCENARIO = "financiera"
VIEWPORT = {"width": 1280, "height": 800}   # igual que los otros videos


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _preparar_datos(dir_datos: str) -> dict:
    """Activa el escenario de demo en el layout de la empresa principal.

    `activar` deja todo junto en un directorio (así lo consume el endpoint,
    que para la principal apunta a `outputs/`); las gestiones y las llamadas
    evaluadas, en cambio, la API de la principal las lee de `data/` — se
    copian ahí, igual que hace el endpoint de activación, para que Agenda,
    Gestores y Calidad muestren la historia del escenario y no una pantalla
    vacía.

    Devuelve las rutas de los archivos que las escenas SUBEN en cámara: la
    cartera del escenario (ingeniería de datos la perfila en vivo) y el
    histórico con resultado (AutoML entrena en vivo — la cartera recién
    importada no trae `pago`, como una real; el histórico sale del generador
    canónico con la misma semilla que usa la verificación).
    """
    from data.generate_dataset import generar as gen_hist
    from kobra import demo_escenarios
    outputs = os.path.join(dir_datos, "outputs")
    demo_escenarios.activar(ESCENARIO, outputs)
    os.makedirs(os.path.join(dir_datos, "data"), exist_ok=True)
    for nombre in ("kobra_gestiones.csv", "calidad_evaluaciones.csv"):
        shutil.copy(os.path.join(outputs, nombre),
                    os.path.join(dir_datos, "data", nombre))

    historico = os.path.join(dir_datos, "historico_para_automl.csv")
    import pandas as pd
    pd.DataFrame(gen_hist(n=400, seed=demo_escenarios.ESCENARIOS_SEED_HIST)) \
        .to_csv(historico, index=False)
    return {"cartera": os.path.join(outputs, "kobra_scored.csv"),
            "historico": historico}


# Secreto de licencia SOLO del proceso de grabación (nunca el de producción):
# firma una licencia que vive lo que dura el screencast, en un config
# temporal. La película entra como entra un cliente — activando una licencia
# real por /api/licencia/activar — porque `KOBRA_OWNER=1` ya no desbloquea
# nada desde que `kobra/edicion.py::es_owner` exige credencial verificable
# (el atajo por variable de entorno era una puerta que cualquiera abría).
_SECRETO_GRABACION = "pelicula-demo-secreto-de-grabacion-local"


def _licencia_full() -> str:
    """Enterprise + los dos módulos sueltos: la película recorre TODAS las
    pantallas, y para eso hace falta la llave que abre todas las puertas —
    el mismo criterio que los tests E2E de escenarios."""
    from backend_venta import licencias as klic
    features = [*klic.PLANES["enterprise"]["features"], "logistica", "proyectos"]
    return klic.emitir_licencia("pelicula-demo", "enterprise",
                                secreto=_SECRETO_GRABACION,
                                cupo_mensual=None, features=features)


def _post_json(url: str, cuerpo: dict, token: str | None = None) -> dict:
    cabeceras = {"content-type": "application/json"}
    if token:
        cabeceras["Authorization"] = f"Bearer {token}"
    pedido = urllib.request.Request(
        url, data=json.dumps(cuerpo).encode(),
        headers=cabeceras, method="POST")
    with urllib.request.urlopen(pedido, timeout=30) as r:
        return json.loads(r.read())


def _configurar_caso_demo(base: str, token: str) -> None:
    """El contacto del caso de la demostración en vivo, con los datos de
    FICCIÓN del propio repo (`kobra/demo_vivo.py::_SINTETICO`): el teléfono
    usa el rango 555 reservado para ficción — formato Twilio, pero un número
    que no existe. Con el contacto cargado, la escena de la llamada muestra
    el guion completo del agente («Disca a +598 99 555 000 y se presenta…»)
    en vez del formulario de configuración vacío. Nunca se aprieta
    «Llamar»: la película muestra el circuito, no hace sonar un teléfono."""
    from kobra import demo_vivo
    _post_json(f"{base}/api/demo/contacto",
               {"valores": dict(demo_vivo._SINTETICO)}, token=token)


def _escena_ingenieria(pagina, archivos: dict) -> None:
    """Ingeniería de datos EN VIVO: se sube la cartera del propio escenario y
    la pantalla la perfila delante de cámara — sin esto, la escena era un
    formulario de subida vacío."""
    try:
        pagina.wait_for_timeout(2000)
        pagina.set_input_files("input[type=file]", archivos["cartera"])
        pagina.wait_for_timeout(2500)
        pagina.mouse.wheel(0, 500)
    except Exception:
        pass


def _escena_automl(pagina, archivos: dict) -> None:
    """AutoML EN VIVO: subir el histórico, elegir `pago` y entrenar en
    cámara. La métrica que aparece es la del holdout real — el mismo número
    que muestra la verificación punta a punta."""
    try:
        pagina.wait_for_timeout(1200)
        pagina.set_input_files("input[type=file]", archivos["historico"])
        pagina.wait_for_timeout(1800)
        tarjeta = pagina.locator(".card", has_text="Elegí qué predecir")
        # `.first`: la tarjeta tiene DOS selects (objetivo y columna de
        # fecha) y el modo estricto de Playwright aborta con ambos — en la
        # toma anterior el except lo tragó y el video quedó sin entrenar.
        tarjeta.locator("select").first.select_option("pago")
        pagina.wait_for_timeout(600)
        tarjeta.get_by_role("button").click()
    except Exception:
        pass


def _escena_llamada(pagina) -> None:
    """La escena de la llamada, en dos tiempos: primero el caso y el guion
    del agente quietos en pantalla (ahí se lee el número al que disca), y
    recién después se genera el cobro en vivo (transferencia — checkout
    simulado, sin tocar servicios externos) y se baja hasta la mesa de
    negociación. El clic de Playwright ya lleva la vista hasta el botón, así
    que no hace falta scrollear antes. Si algo falla, la escena queda quieta:
    mejor eso que cortar la película."""
    try:
        pagina.wait_for_timeout(3500)        # el guion de la llamada, legible
        pagina.get_by_role("button", name="Datos de transferencia").click(
            timeout=3000)
        pagina.wait_for_timeout(1500)
        pagina.mouse.wheel(0, 700)
    except Exception:
        pass


def grabar(salida: str) -> str:
    """Screencast crudo (sin audio) del recorrido completo."""
    from playwright.sync_api import sync_playwright

    puerto = _puerto_libre()
    tmp = tempfile.mkdtemp(prefix="pelicula_")
    archivos = _preparar_datos(os.path.join(tmp, "datos"))

    entorno = {**os.environ,
               "KOBRA_CONFIG_DIR": os.path.join(tmp, "config"),
               "KOBRA_DATA_DIR": os.path.join(tmp, "datos"),
               "KOBRA_MODO_STANDALONE": "1",
               "KOBRA_LICENSE_SECRET": _SECRETO_GRABACION}
    entorno.pop("KOBRA_OWNER", None)
    # La URL local como URL "pública": la pantalla de la llamada no muestra el
    # aviso de configuración pendiente. Ningún paso de la grabación dispara
    # una llamada real — el botón «Llamar» no se toca.
    entorno.setdefault("PUBLIC_BASE_URL", f"http://127.0.0.1:{puerto}")
    servidor = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "webapp.backend.api:app",
         "--port", str(puerto), "--log-level", "warning"],
        cwd=RAIZ, env=entorno,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{puerto}"
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"{base}/api/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("el servidor no arrancó")

        # El MISMO flujo del cliente, hecho por programa: activar la licencia
        # devuelve la sesión de admin que el frontend guarda en localStorage.
        sesion = _post_json(f"{base}/api/licencia/activar",
                            {"token": _licencia_full()})
        _configurar_caso_demo(base, sesion["token"])

        with sync_playwright() as p:
            eje = shutil.which("chromium", path="/opt/pw-browsers") or None
            navegador = p.chromium.launch(executable_path=eje)

            # Antes de cargar la app: el tour marcado como visto (el modal
            # taparía todas las pantallas) y la sesión ya iniciada (si no, la
            # película entera sería la pantalla de activación).
            inits = ["localStorage.setItem('kobra_tour_visto','1')",
                     "localStorage.setItem('kobra_token', "
                     f"{json.dumps(json.dumps(sesion))})"]

            # Calentamiento SIN video: el primer load dispara todas las APIs
            # frías del backend (medido: ~8 s) y Playwright graba el contexto
            # desde que nace — hecho en el contexto grabado, esos 8 s
            # quedaban DELANTE de la escena 1 y corrían toda la narración.
            warm = navegador.new_context(viewport=VIEWPORT)
            pw = warm.new_page()
            for script in inits:
                pw.add_init_script(script)
            pw.goto(f"{base}/#/", wait_until="networkidle")
            warm.close()

            ctx = navegador.new_context(viewport=VIEWPORT,
                                        record_video_dir=tmp,
                                        record_video_size=VIEWPORT)
            pagina = ctx.new_page()
            for script in inits:
                pagina.add_init_script(script)
            for ruta, segundos in RECORRIDO:
                # El reloj arranca ANTES del goto: la navegación también es
                # tiempo de la escena. Medido: con el reloj después del goto,
                # 18 navegaciones acumularon 8 s y los subtítulos del final
                # quedaban hablando de la pantalla anterior.
                t0 = time.monotonic()
                pagina.goto(f"{base}/#{ruta}")
                try:
                    # 3 s y no 8: con el servidor ya caliente las APIs vuelven
                    # en milisegundos, y en las pantallas con tráfico continuo
                    # `networkidle` no llega nunca — cada timeout de 8 s
                    # desbordaba el presupuesto de su escena y el total daba
                    # 169 s para un guion de 162 (medido en dos tomas).
                    pagina.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass                     # una pantalla lenta no corta el video
                if ruta == "/demo-vivo":
                    _escena_llamada(pagina)
                elif ruta == "/ingenieria-datos":
                    _escena_ingenieria(pagina, archivos)
                elif ruta == "/automl":
                    _escena_automl(pagina, archivos)
                # Cada escena dura lo que declara el guion, interacciones
                # incluidas: si esto no se descuenta, cada clic corre TODOS
                # los subtítulos siguientes y la narración se adelanta a la
                # pantalla.
                resto = segundos - (time.monotonic() - t0)
                if resto > 0:
                    pagina.wait_for_timeout(int(resto * 1000))
            video = pagina.video
            ctx.close()                      # cierra y vuelca el webm
            crudo = video.path()
            navegador.close()

        os.makedirs(os.path.dirname(salida), exist_ok=True)
        shutil.move(crudo, salida)
        return salida
    finally:
        servidor.terminate()


def construir(salida: str = SALIDA_DEFAULT, motor: str | None = None,
              voz: str | None = None, con_voz: bool = True,
              crudo: str | None = None) -> dict:
    """Graba la película (o toma `crudo` ya grabado) y le monta la narración
    con los cues ESCALADOS a la duración real del video — el screencast sale
    con el reloj estirado (~4,5%, ver subtitulos._escala_pelicula) y sin el
    escalado la voz del final habla de la pantalla anterior. Al terminar
    regenera los .vtt con la misma escala."""
    if not con_voz:
        return {"salida": grabar(salida), "motor": None}
    from marketing import audio_suite, subtitulos
    if crudo is None:
        crudo = os.path.join(tempfile.mkdtemp(prefix="pelicula_cruda_"),
                             "pelicula_cruda.webm")
        grabar(crudo)
    escala = audio_suite.duracion(crudo) / PELICULA_CUES[-1][1]
    inf = audio_suite.construir(salida=salida, motor=motor, entrada=crudo,
                                voz=voz,
                                cues=subtitulos.cues_pelicula_escalados(escala))
    inf["escala_cues"] = round(escala, 4)
    subtitulos.generar()
    return inf


def main(argv=None) -> int:
    from marketing.audio_suite import VOCES
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--motor", choices=("elevenlabs", "piper"), default=None)
    p.add_argument("--voz", choices=sorted(VOCES), default=None,
                   help="voz de piper (por defecto la rioplatense)")
    p.add_argument("--salida", default=SALIDA_DEFAULT)
    p.add_argument("--sin-voz", action="store_true",
                   help="solo el screencast, sin narración")
    a = p.parse_args(argv)

    inf = construir(salida=a.salida, motor=a.motor, voz=a.voz,
                    con_voz=not a.sin_voz)
    mb = os.path.getsize(inf["salida"]) / 1e6
    print(f"[OK] {inf['salida']}  ({mb:.1f} MB)")
    if inf.get("motor"):
        print(f"     motor={inf['motor']} voz={inf['voz']} cues={inf['cues']}")
        print(f"     video {inf['duracion_video_original']}s -> "
              f"{inf['duracion_final']}s (congelado {inf['congelado_s']}s) · "
              f"ritmo {inf['wpm_promedio']} pal/min")
        for av in inf["avisos"]:
            print(f"     [aviso] {av}")
    print("Subtítulos: python3 -m marketing.subtitulos  (pelicula.*.vtt)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
