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
  lista define el recorrido de la grabación, los subtítulos y la narración.
  No hay tres copias que desincronizar.
* **Una película POR IDIOMA, completa.** No es un video en castellano con
  subtítulos pegados: se graba el programa con la interfaz en ese idioma
  (menú incluido) y se narra con una voz de ese idioma. Un gerente en San
  Pablo ve el producto en portugués, hablado en portugués.
* **La duración de cada escena la decide la voz, no una estimación.** Primero
  se sintetiza y se MIDE la narración de cada escena; recién ahí se sabe
  cuánto tiene que durar la pantalla. Así se acaban los silencios largos
  —hasta 5,4 s medidos en la versión anterior, que es el "lag" que se
  escucha— y el mismo guion sirve para tres idiomas que hablan a ritmos
  distintos.

Uso:
    python3 -m marketing.pelicula_demo                   # los tres idiomas
    python3 -m marketing.pelicula_demo --idioma pt       # uno solo
    python3 -m marketing.pelicula_demo --sin-voz         # solo el screencast
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

from marketing.subtitulos import IDIOMAS, PELICULA_ESCENAS

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO_DIR = os.path.join(RAIZ, "landing", "video")

# El recorrido sale del guion: misma fuente que subtítulos y narración.
RECORRIDO = [ruta for ruta, _ in PELICULA_ESCENAS]
ESCENARIO = "financiera"
VIEWPORT = {"width": 1280, "height": 800}   # igual que los otros videos

# Aire entre el final de una frase y el cambio de pantalla. Es lo único que
# se "estima" del tiempo, y es chico a propósito: con 1,4 s la película
# respira sin que se sienta que quedó colgada. El resto lo pone la voz.
RESPIRO_S = 1.4
# Entre dos frases de la misma escena: lo que dura una coma larga.
PAUSA_ENTRE_FRASES_S = 0.5
# Piso por escena: una pantalla que aparece menos de esto no se llega a
# mirar, aunque su frase sea corta.
MINIMO_ESCENA_S = 6.0
# Las escenas con interacción en cámara necesitan su tiempo propio, que no
# tiene nada que ver con lo que dura la frase: subir un archivo, entrenar un
# modelo o generar un cobro tardan lo que tardan.
PISO_POR_ESCENA = {"/demo-vivo": 13.0, "/ingenieria-datos": 12.0,
                   "/automl": 14.0}


def salida_de(idioma: str) -> str:
    """Un archivo por idioma: la landing sirve el que corresponda."""
    return os.path.join(VIDEO_DIR, f"MVKobraAI_Pelicula_Demo.{idioma}.webm")


def subtitulo_de(idioma: str) -> str:
    return os.path.join(VIDEO_DIR, f"pelicula.{idioma}.vtt")


def _textos_ui(idioma: str) -> dict:
    """El diccionario de la interfaz, para que la grabación busque los
    botones por su nombre EN EL IDIOMA que se está filmando. Buscar
    «Datos de transferencia» en la película en inglés no encuentra nada, y la
    escena queda quieta sin que nadie se entere."""
    archivo = {"es": "es.json", "pt": "pt-BR.json", "en": "en.json"}[idioma]
    with open(os.path.join(RAIZ, "webapp", "frontend", "src", "i18n", archivo),
              encoding="utf-8") as f:
        return json.load(f)


def frases_de(textos, idioma: str) -> list[str]:
    """Las frases de una escena en un idioma. Una escena normal tiene una;
    las que muestran al producto trabajando tienen dos, para que la voz
    acompañe la acción en vez de dejar el silencio de la máquina pensando."""
    if isinstance(textos, list):
        return [t[idioma] for t in textos]
    return [textos[idioma]]


def _t(dic: dict, ruta: str) -> str:
    valor = dic
    for parte in ruta.split("."):
        valor = valor[parte]
    return valor


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


def _escena_ingenieria(pagina, archivos: dict, ui: dict) -> None:
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


def _escena_automl(pagina, archivos: dict, ui: dict) -> None:
    """AutoML EN VIVO: subir el histórico, elegir `pago` y entrenar en
    cámara. La métrica que aparece es la del holdout real — el mismo número
    que muestra la verificación punta a punta."""
    try:
        pagina.wait_for_timeout(1200)
        pagina.set_input_files("input[type=file]", archivos["historico"])
        pagina.wait_for_timeout(1800)
        tarjeta = pagina.locator(".card", has_text=_t(ui, "automl.paso2"))
        # `.first`: la tarjeta tiene DOS selects (objetivo y columna de
        # fecha) y el modo estricto de Playwright aborta con ambos — en una
        # toma anterior el except lo tragó y el video quedó sin entrenar.
        tarjeta.locator("select").first.select_option("pago")
        pagina.wait_for_timeout(600)
        tarjeta.get_by_role("button").click()
    except Exception:
        pass


def _escena_llamada(pagina, archivos: dict, ui: dict) -> None:
    """La escena de la llamada, en dos tiempos: primero el caso y el guion
    del agente quietos en pantalla (ahí se lee el número al que disca), y
    recién después se genera el cobro en vivo (transferencia — checkout
    simulado, sin tocar servicios externos) y se baja hasta la mesa de
    negociación. El clic de Playwright ya lleva la vista hasta el botón, así
    que no hace falta scrollear antes. Si algo falla, la escena queda quieta:
    mejor eso que cortar la película."""
    try:
        pagina.wait_for_timeout(3500)        # el guion de la llamada, legible
        pagina.get_by_role(
            "button", name=_t(ui, "demo.cobrar_transferencia")).click(timeout=3000)
        pagina.wait_for_timeout(1500)
        pagina.mouse.wheel(0, 700)
    except Exception:
        pass


# Qué hace la cámara en las escenas que no son una pantalla quieta.
INTERACCIONES = {"/demo-vivo": _escena_llamada,
                 "/ingenieria-datos": _escena_ingenieria,
                 "/automl": _escena_automl}


def narracion(idioma: str, motor: str, voz: str, destino: str) -> list[dict]:
    """Primera pasada: sintetiza la narración escena por escena y la MIDE.

    De acá sale todo lo demás — cuánto dura cada pantalla en la grabación, en
    qué segundo entra cada frase y qué dice cada subtítulo. Es el orden
    inverso al de antes (declarar la duración y encajarle la voz), y es el que
    hace que no queden silencios: la pantalla dura lo que dura la frase.
    """
    from marketing import audio_suite
    plan, t, n = [], 0.0, 0
    for ruta, textos in PELICULA_ESCENAS:
        frases = frases_de(textos, idioma)
        cues, hablado = [], 0.0
        for texto in frases:
            audio, dur, _escala = audio_suite._a_ritmo(texto, 0.0, motor, voz)
            wav = os.path.join(destino, f"cue_{n:02d}.wav")
            n += 1
            with open(wav, "wb") as f:
                f.write(audio)
            if dur <= 0:                      # motor que no devuelve WAV
                dur = audio_suite.duracion(wav)
            cues.append({"texto": texto, "wav": wav, "voz_s": dur})
            hablado += dur + PAUSA_ENTRE_FRASES_S
        hablado -= PAUSA_ENTRE_FRASES_S       # la última no lleva pausa detrás
        escena = max(hablado + RESPIRO_S, MINIMO_ESCENA_S,
                     PISO_POR_ESCENA.get(ruta, 0.0))
        inicio = t
        for cue in cues:                      # cada frase, en su segundo
            cue.update({"ruta": ruta, "inicio": inicio, "escena_s": escena})
            inicio += cue["voz_s"] + PAUSA_ENTRE_FRASES_S
        plan.extend(cues)
        t += escena
    return plan


def grabar(salida: str, plan: list[dict] | None = None,
           idioma: str = "es") -> str:
    """Screencast crudo (sin audio) del recorrido completo, con la interfaz
    del programa en `idioma` y cada pantalla durando lo que dura su frase."""
    from playwright.sync_api import sync_playwright
    ui = _textos_ui(idioma)
    if plan is None:                          # modo `--sin-voz`: tiempos fijos
        plan = [{"ruta": r, "escena_s": MINIMO_ESCENA_S + 2,
                 **({"escena_s": PISO_POR_ESCENA[r]} if r in PISO_POR_ESCENA else {})}
                for r in RECORRIDO]

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
            # taparía todas las pantallas), la sesión ya iniciada (si no, la
            # película entera sería la pantalla de activación) y el idioma de
            # la interfaz — el mismo `kobra_idioma` que guarda el selector de
            # la barra lateral, así que lo que se filma es exactamente lo que
            # ve un cliente que elige ese idioma.
            inits = ["localStorage.setItem('kobra_tour_visto','1')",
                     f"localStorage.setItem('kobra_idioma','{idioma}')",
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
            for escena in plan:
                ruta, segundos = escena["ruta"], escena["escena_s"]
                # El reloj arranca ANTES del goto: la navegación también es
                # tiempo de la escena. Medido: con el reloj después del goto,
                # 18 navegaciones acumularon 8 s y los subtítulos del final
                # quedaban hablando de la pantalla anterior.
                t0 = time.monotonic()
                pagina.goto(f"{base}/?lang={idioma}#{ruta}")
                try:
                    # 3 s y no 8: con el servidor ya caliente las APIs vuelven
                    # en milisegundos, y en las pantallas con tráfico continuo
                    # `networkidle` no llega nunca — cada timeout de 8 s
                    # desbordaba el presupuesto de su escena.
                    pagina.wait_for_load_state("networkidle", timeout=3000)
                except Exception:
                    pass                     # una pantalla lenta no corta el video
                accion = INTERACCIONES.get(ruta)
                if accion:
                    accion(pagina, archivos, ui)
                # Cada escena dura lo que dura su frase, interacciones
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


def _escribir_vtt(plan: list[dict], idioma: str, escala: float) -> str:
    """Los subtítulos de ESTE video, con los tiempos de ESTA narración.

    `escala` corrige la diferencia entre el reloj del guion y el del webm que
    escupe Playwright (medido: ~4,5% de más, constante entre tomas). Sin eso
    el último subtítulo cae antes de la última pantalla.
    """
    from marketing.subtitulos import _marca
    partes = ["WEBVTT", ""]
    for n, escena in enumerate(plan, start=1):
        ini = escena["inicio"] * escala
        # El subtítulo se va con la voz (más un respiro), no se queda pegado
        # hasta el cambio de pantalla: leer un texto que ya nadie está
        # diciendo distrae de lo que se ve.
        fin = ini + (escena["voz_s"] + 0.6) * escala
        partes += [str(n), f"{_marca(ini)} --> {_marca(fin)}",
                   escena["texto"], ""]
    ruta = subtitulo_de(idioma)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write("\n".join(partes))
    return ruta


def construir(idioma: str = "es", motor: str | None = None,
              voz: str | None = None, con_voz: bool = True,
              salida: str | None = None) -> dict:
    """La película completa de un idioma: narración medida → grabación con la
    interfaz en ese idioma → montaje → subtítulos."""
    from marketing import audio_suite
    salida = salida or salida_de(idioma)
    if not con_voz:
        return {"salida": grabar(salida, idioma=idioma), "idioma": idioma}

    motor = motor or audio_suite.motor_disponible()
    voz = voz or audio_suite.VOZ_POR_IDIOMA[idioma]
    tmp = tempfile.mkdtemp(prefix=f"pelicula_{idioma}_")

    plan = narracion(idioma, motor, voz, tmp)
    crudo = os.path.join(tmp, "crudo.webm")
    grabar(crudo, plan=plan, idioma=idioma)

    # El webm sale con el reloj estirado respecto del guion; se mide y se
    # corrige de una vez, para el audio y para los subtítulos.
    guion_s = plan[-1]["inicio"] + plan[-1]["escena_s"]
    real_s = audio_suite.duracion(crudo)
    escala = real_s / guion_s if guion_s else 1.0
    pistas = [(e["wav"], e["inicio"] * escala) for e in plan]
    inf = audio_suite.montar(crudo, salida, pistas, dur_video=real_s)

    huecos = [round(e["escena_s"] * escala - e["voz_s"], 2) for e in plan]
    palabras = sum(audio_suite.palabras(e["texto"]) for e in plan)
    voz_total = sum(e["voz_s"] for e in plan)
    inf.update({
        "idioma": idioma, "motor": motor, "voz": voz,
        "licencia": audio_suite.VOCES[voz]["licencia"] if motor == "piper" else "-",
        "escenas": len(plan), "escala": round(escala, 4),
        "hueco_max_s": max(huecos), "hueco_medio_s": round(sum(huecos) / len(huecos), 2),
        "wpm_promedio": round(palabras / voz_total * 60, 1) if voz_total else 0.0,
        "subtitulos": _escribir_vtt(plan, idioma, escala),
    })
    return inf


def main(argv=None) -> int:
    from marketing.audio_suite import VOCES
    p = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    p.add_argument("--idioma", choices=(*IDIOMAS, "todos"), default="todos")
    p.add_argument("--motor", choices=("elevenlabs", "piper"), default=None)
    p.add_argument("--voz", choices=sorted(VOCES), default=None,
                   help="fuerza una voz (por defecto, la del idioma)")
    p.add_argument("--sin-voz", action="store_true",
                   help="solo el screencast, sin narración")
    a = p.parse_args(argv)

    idiomas = IDIOMAS if a.idioma == "todos" else (a.idioma,)
    for idioma in idiomas:
        inf = construir(idioma=idioma, motor=a.motor, voz=a.voz,
                        con_voz=not a.sin_voz)
        mb = os.path.getsize(inf["salida"]) / 1e6
        print(f"[OK] {os.path.basename(inf['salida'])}  ({mb:.1f} MB)")
        if inf.get("motor"):
            print(f"     idioma={inf['idioma']} voz={inf['voz']} "
                  f"({inf['licencia']}) escenas={inf['escenas']}")
            print(f"     duración {inf['duracion_final']}s · ritmo "
                  f"{inf['wpm_promedio']} pal/min · silencio entre frases: "
                  f"medio {inf['hueco_medio_s']}s, máximo {inf['hueco_max_s']}s")
            print(f"     subtítulos: {os.path.basename(inf['subtitulos'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
