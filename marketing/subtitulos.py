# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Subtítulos del video de la landing
=================================================
El video del Copiloto está narrado en castellano. Elegir portugués o inglés en
el sitio no lo cambiaba en nada: el visitante que no habla español se quedaba
sin entender la pieza principal de la landing.

Doblarlo no sería una solución honesta — la interfaz que se ve *dentro* del
video también está en castellano, así que una narración en inglés sobre una
pantalla en español confunde más de lo que ayuda. Los subtítulos sí son la
respuesta estándar: acompañan el audio original, se activan solos con el
idioma elegido y encima suman accesibilidad para quien mira sin sonido.

Sobre el texto
--------------
Los tiempos salen de transcribir el audio real del video, no de estimar. El
texto en castellano es esa transcripción **corregida a mano**: el reconocedor
confunde el nombre del producto ("cobra" por "Kobra") y varias palabras
sueltas ("estores" por "gestores", "Espetaurarios" por "Respeta horarios").
Publicar el crudo hubiera puesto el nombre de la marca mal escrito en pantalla.

Uso:
    python3 -m marketing.subtitulos
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VIDEO_DIR = os.path.join(ROOT, "landing", "video")

IDIOMAS = ("es", "pt", "en")

# (inicio, fin, {idioma: texto}) — tiempos en segundos, medidos sobre el audio.
CUES = [
    (0.00, 4.76, {
        "es": "¿Y si un agente de inteligencia artificial cobrara tu cartera,\nnegociando como una persona",
        "pt": "E se um agente de inteligência artificial cobrasse a sua carteira,\nnegociando como uma pessoa",
        "en": "What if an AI agent collected your portfolio,\nnegotiating like a person"}),
    (4.76, 6.26, {"es": "las 24 horas?", "pt": "24 horas por dia?",
                  "en": "around the clock?"}),
    (6.26, 7.26, {"es": "Esto es MV Kobra AI.", "pt": "Isto é a MV Kobra AI.",
                  "en": "This is MV Kobra AI."}),
    (7.26, 10.70, {
        "es": "Kobra analiza tu cartera y predice quién va a pagar,\npara que gestiones primero lo que",
        "pt": "A Kobra analisa a sua carteira e prevê quem vai pagar,\npara você priorizar o que",
        "en": "Kobra analyses your portfolio and predicts who will pay,\nso you work first on what"}),
    (10.70, 11.70, {"es": "más recuperás.", "pt": "mais recupera.",
                    "en": "recovers the most."}),
    (11.70, 16.34, {
        "es": "El agente negociador decide la estrategia, el descuento justo\ny el guion para cada deudor.",
        "pt": "O agente negociador define a estratégia, o desconto certo\ne o roteiro para cada devedor.",
        "en": "The negotiating agent sets the strategy, the right discount\nand the script for each debtor."}),
    (16.34, 20.42, {
        "es": "El gestor de inteligencia artificial llama por teléfono\ny negocia con voz natural.",
        "pt": "O agente de inteligência artificial liga por telefone\ne negocia com voz natural.",
        "en": "The AI agent calls on the phone\nand negotiates with a natural voice."}),
    (20.42, 21.42, {"es": "Escuchá.", "pt": "Escute.", "en": "Listen."}),
    (21.42, 26.38, {
        "es": "Le ofrezco pagar hoy 5.700 y cancela los 6.000,\no lo armamos en 3 cuotas.",
        "pt": "Posso oferecer pagar hoje 5.700 e quitar os 6.000,\nou dividir em 3 parcelas.",
        "en": "I can offer you 5,700 today to settle the 6,000,\nor split it into 3 instalments."}),
    (26.38, 27.90, {"es": "¿No quiere hablar por teléfono?",
                    "pt": "Não quer falar por telefone?",
                    "en": "Doesn't want to talk on the phone?"}),
    (27.90, 30.92, {
        "es": "El mismo agente negocia por WhatsApp\ny registra todo solo.",
        "pt": "O mesmo agente negocia pelo WhatsApp\ne registra tudo sozinho.",
        "en": "The same agent negotiates over WhatsApp\nand logs everything on its own."}),
    (30.92, 32.42, {"es": "¿Preferís gestores humanos?",
                    "pt": "Prefere atendentes humanos?",
                    "en": "Prefer human agents?"}),
    (32.42, 33.62, {"es": "Kobra los asiste en vivo.",
                    "pt": "A Kobra assiste em tempo real.",
                    "en": "Kobra assists them live."}),
    (33.62, 36.02, {"es": "Detecta el ánimo del cliente y sugiere qué decir.",
                    "pt": "Detecta o humor do cliente e sugere o que dizer.",
                    "en": "It reads the customer's mood and suggests what to say."}),
    (36.02, 37.02, {"es": "Respeta horarios,", "pt": "Respeita horários,",
                    "en": "It respects calling hours,"}),
    (37.02, 38.82, {"es": "la lista de no contactar y los topes.",
                    "pt": "a lista de não contatar e os limites.",
                    "en": "the do-not-contact list and the caps."}),
    (38.82, 41.30, {"es": "Y cada decisión es transparente y explicable.",
                    "pt": "E cada decisão é transparente e explicável.",
                    "en": "And every decision is transparent and explainable."}),
    (41.30, 43.30, {"es": "Y todo se mide en un tablero gerencial.",
                    "pt": "E tudo é medido em um painel gerencial.",
                    "en": "And everything is measured in a management dashboard."}),
    (43.30, 44.30, {"es": "Cartera,", "pt": "Carteira,", "en": "Portfolio,"}),
    (44.30, 45.30, {"es": "recupero esperado,", "pt": "recuperação esperada,",
                    "en": "expected recovery,"}),
    (45.30, 46.30, {"es": "propensión y mora,", "pt": "propensão e inadimplência,",
                    "en": "propensity and arrears,"}),
    (46.30, 47.30, {"es": "de un vistazo.", "pt": "num relance.",
                    "en": "at a glance."}),
    (47.30, 48.46, {"es": "Con reportes por gestor y por mes,",
                    "pt": "Com relatórios por atendente e por mês,",
                    "en": "With reports by agent and by month,"}),
    (48.46, 49.46, {"es": "filtros", "pt": "filtros", "en": "filters"}),
    (49.46, 51.02, {"es": "y exportación a Excel con un clic.",
                    "pt": "e exportação para Excel com um clique.",
                    "en": "and one-click export to Excel."}),
    (51.02, 54.98, {
        "es": "Y cada resultado —pago, arreglo, promesa o no contactado—\ncon sus fechas,",
        "pt": "E cada resultado —pagamento, acordo, promessa ou não contatado—\ncom suas datas,",
        "en": "And every outcome —payment, plan, promise or not reached—\nwith its dates,"}),
    (54.98, 55.98, {"es": "montos y notas.", "pt": "valores e observações.",
                    "en": "amounts and notes."}),
    (55.98, 59.58, {
        "es": "Se exporta y sincroniza solo a tu ERP\no base de datos, por API.",
        "pt": "Exporta e sincroniza sozinho com o seu ERP\nou banco de dados, por API.",
        "en": "It exports and syncs on its own to your ERP\nor database, over API."}),
    (59.58, 61.14, {"es": "MV Kobra AI.", "pt": "MV Kobra AI.", "en": "MV Kobra AI."}),
    (61.14, 63.34, {"es": "Cobranzas inteligentes que trabajan solas.",
                    "pt": "Cobrança inteligente que trabalha sozinha.",
                    "en": "Smart collections that run themselves."}),
    (63.34, 63.86, {"es": "Probalo hoy.", "pt": "Experimente hoje.",
                    "en": "Try it today."}),
]


def _marca(segundos: float) -> str:
    """Segundos → `HH:MM:SS.mmm`, el formato que exige WebVTT."""
    ms = int(round(segundos * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def vtt(idioma: str) -> str:
    """Pista WebVTT completa para un idioma."""
    faltan = [i for i, c in enumerate(CUES) if idioma not in c[2]]
    if faltan:
        raise ValueError(f"faltan cues en {idioma!r}: {faltan}")
    partes = ["WEBVTT", ""]
    for n, (ini, fin, textos) in enumerate(CUES, start=1):
        partes += [str(n), f"{_marca(ini)} --> {_marca(fin)}",
                   textos[idioma], ""]
    return "\n".join(partes)


def generar(destino: str | None = None) -> dict[str, str]:
    """Escribe `copiloto.<idioma>.vtt` en `landing/video/`."""
    destino = destino or VIDEO_DIR
    os.makedirs(destino, exist_ok=True)
    salida = {}
    for idioma in IDIOMAS:
        ruta = os.path.join(destino, f"copiloto.{idioma}.vtt")
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(vtt(idioma))
        salida[idioma] = ruta
    return salida


if __name__ == "__main__":
    for idioma, ruta in generar().items():
        print(f"[OK] {idioma}  {len(CUES)} subtítulos  "
              f"{os.path.relpath(ruta, ROOT)}")
