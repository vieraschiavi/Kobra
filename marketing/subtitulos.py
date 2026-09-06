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


# Subtítulos del screencast de la suite (MVKobraAI_Suite_Demo.webm).
# Los tiempos siguen el RECORRIDO de marketing/screencast_suite.py: cada
# pantalla dura lo que declara ahí (más ~1 s de navegación). Si se cambia el
# recorrido, se cambian estos tiempos — son la misma decisión en dos archivos,
# y el guion de la voz (marketing/voz_suite.py) lee estos mismos textos, así
# que subtítulo y narración no se pueden desincronizar.
SUITE_CUES = [
    (0.0, 6.0, {
        "es": "MV Kobra AI ya no es un producto: es una plataforma.\nEsto es lo que se sumó.",
        "pt": "A MV Kobra AI já não é um produto: é uma plataforma.\nIsto é o que foi adicionado.",
        "en": "MV Kobra AI is no longer one product: it is a platform.\nHere is what was added."}),
    (6.0, 14.5, {
        "es": "El tablero conversacional: preguntá en tu idioma.\nLos números salen de tus datos, no de una estimación.",
        "pt": "O painel conversacional: pergunte no seu idioma.\nOs números vêm dos seus dados, não de uma estimativa.",
        "en": "The conversational board: ask in your own words.\nEvery number comes from your data, not a guess."}),
    (14.5, 23.0, {
        "es": "Gobernanza de datos: qué es personal, quién lo ve,\ncalidad en las seis dimensiones DAMA y linaje auditable.",
        "pt": "Governança de dados: o que é pessoal, quem vê,\nqualidade nas seis dimensões DAMA e linhagem auditável.",
        "en": "Data governance: what is personal, who can see it,\nquality across the six DAMA dimensions and auditable lineage."}),
    (23.0, 29.5, {
        "es": "Frecuencia de cargas: cuándo se actualizó cada tabla.\nUn tablero con datos viejos se ve igual que uno correcto.",
        "pt": "Frequência de cargas: quando cada tabela foi atualizada.\nUm painel com dados velhos parece igual a um correto.",
        "en": "Load freshness: when each table was last updated.\nA dashboard on stale data looks just like a correct one."}),
    (29.5, 37.0, {
        "es": "KPIs propios: definilos con una fórmula,\nsin tocar una línea de código.",
        "pt": "KPIs próprios: defina-os com uma fórmula,\nsem tocar numa linha de código.",
        "en": "Custom KPIs: define them with a formula,\nwithout touching a line of code."}),
    (37.0, 44.5, {
        "es": "AutoML: entrená un modelo con tu propio dataset.\nLa métrica sale de un holdout que no se usó para elegir nada.",
        "pt": "AutoML: treine um modelo com o seu próprio dataset.\nA métrica vem de um holdout que não foi usado para escolher nada.",
        "en": "AutoML: train a model on your own dataset.\nThe metric comes from a holdout never used to choose anything."}),
    (44.5, 53.0, {
        "es": "Proyección de cobranza: si la serie no tiene señal,\nte muestra el promedio y te lo dice. No dibuja una curva.",
        "pt": "Projeção de cobrança: se a série não tem sinal,\nmostra a média e te avisa. Não desenha uma curva.",
        "en": "Collection forecast: when the series carries no signal,\nit shows the average and says so. It draws no curve."}),
    (53.0, 59.5, {
        "es": "Memoria técnica: el pipeline en técnico y en criollo,\nexportable en HTML, Word o PDF.",
        "pt": "Memória técnica: o pipeline em técnico e em linguagem simples,\nexportável em HTML, Word ou PDF.",
        "en": "Technical memo: the pipeline in technical and plain language,\nexportable as HTML, Word or PDF."}),
    (59.5, 68.0, {
        "es": "Logística, un módulo que se compra aparte:\nqué ofertar, qué reponer y a qué cliente recuperar.",
        "pt": "Logística, um módulo comprado à parte:\no que ofertar, o que repor e qual cliente recuperar.",
        "en": "Logistics, a module sold separately:\nwhat to discount, what to restock, which customer to win back."}),
    (68.0, 76.5, {
        "es": "Y Proyectos: salud del portafolio en seis dimensiones\ny el backlog ordenado por valor esperado.",
        "pt": "E Projetos: saúde do portfólio em seis dimensões\ne o backlog ordenado por valor esperado.",
        "en": "And Projects: portfolio health across six dimensions\nand the backlog ranked by expected value."}),
    (76.5, 79.5, {
        "es": "Cada módulo, con tu plan o suelto. mvkobranzaia.com",
        "pt": "Cada módulo, com o seu plano ou avulso. mvkobranzaia.com",
        "en": "Each module, with your plan or on its own. mvkobranzaia.com"}),
]


# La película: la demo completa, contada como una historia — arranca en el
# problema (la mora creciendo en el panel) y termina en el resultado (/roi).
#
# Cada escena es (ruta del hash router, {idioma: texto}). Fijate que NO trae
# duración: cuánto dura cada pantalla lo decide la NARRACIÓN MEDIDA de ese
# idioma (`marketing/pelicula_demo.py`). Antes la duración se declaraba acá a
# ojo y pasaban las dos cosas que se ven feo: una frase corta dejaba 5,4 s de
# silencio con la pantalla quieta —el "lag" que se escucha—, y el mismo número
# no podía servir para tres idiomas, porque la misma frase dura distinto en
# cada uno (el inglés es más corto que el castellano). Ahora se sintetiza
# primero, se mide, y la pantalla dura lo que dura la frase más un respiro.
PELICULA_ESCENAS = [
    ("/", {
        "es": "Así arranca una cobranza real: la mora crece,\nel panel lo muestra y el tiempo no alcanza.",
        "pt": "Assim começa uma cobrança real: a inadimplência cresce,\no painel mostra e o tempo não alcança.",
        "en": "This is where every collections story starts: arrears growing,\nthe dashboard shows it, and time runs short."}),
    ("/cuentas-por-cobrar", {
        "es": "Primero, medir el problema en serio: antigüedad de saldos,\nDSO y efectividad, calculados sobre la cartera.",
        "pt": "Primeiro, medir o problema a sério: aging de saldos,\nDSO e efetividade, calculados sobre a carteira.",
        "en": "First, measure the problem properly: an aging report,\nDSO and effectiveness, computed from the portfolio."}),
    ("/originacion", {
        "es": "El cambio empieza acá: subís tu cartera y Kobra la scorea\nal instante, con la probabilidad de pago y sus razones.",
        "pt": "A mudança começa aqui: você sobe a sua carteira e a Kobra\npontua na hora, com a probabilidade de pagamento e as razões.",
        "en": "The turnaround starts here: upload your portfolio and Kobra\nscores it instantly, with each payment probability and its reasons."}),
    ("/cartera", {
        "es": "ProbPago ordena la cartera por lo que de verdad se puede recuperar:\nestrategia, descuento justo y guion para cada deudor.",
        "pt": "O ProbPago ordena a carteira pelo que de fato dá para recuperar:\nestratégia, desconto certo e roteiro para cada devedor.",
        "en": "ProbPago ranks the portfolio by what can actually be recovered:\nstrategy, the right discount and a script for every debtor."}),
    ("/agenda", {
        "es": "La agenda arma el día sola:\na quién contactar, cuándo y por qué canal.",
        "pt": "A agenda monta o dia sozinha:\nquem contatar, quando e por qual canal.",
        "en": "The agenda builds the day on its own:\nwho to contact, when, and over which channel."}),
    # Las escenas donde el producto HACE algo en cámara llevan dos frases: la
    # acción tarda lo que tarda (subir un archivo, entrenar, generar un cobro)
    # y con una sola frase quedaban seis segundos de silencio mirando trabajar
    # a la máquina. La segunda frase cuenta lo que está pasando.
    ("/demo-vivo", [{
        "es": "Y el gestor de inteligencia artificial ejecuta: llama con voz natural\nal número del caso y negocia por WhatsApp.",
        "pt": "E o agente de inteligência artificial executa: liga com voz natural\npara o número do caso e negocia pelo WhatsApp.",
        "en": "Then the AI agent executes: it calls the case's number\nwith a natural voice and negotiates over WhatsApp."}, {
        "es": "Acá genera el cobro delante tuyo, con su QR para escanear,\ny el saldo que queda se negocia en la misma pantalla.",
        "pt": "Aqui gera a cobrança na sua frente, com QR para escanear,\ne o saldo restante se negocia na mesma tela.",
        "en": "Here it generates the charge in front of you, with a QR to scan,\nand the remaining balance is negotiated on the same screen."}]),
    ("/portal-cobros", {
        "es": "El deudor también puede pagar solo:\nentra al portal con un QR o un link, y paga.",
        "pt": "O devedor também pode pagar sozinho:\nentra no portal com um QR ou um link, e paga.",
        "en": "Debtors can also pay on their own:\nthey open the portal from a QR code or a link, and pay."}),
    ("/tablero", {
        "es": "El tablero conversacional responde en tu idioma:\ncada número sale de tus datos, no de una estimación.",
        "pt": "O painel conversacional responde no seu idioma:\ncada número vem dos seus dados, não de uma estimativa.",
        "en": "The conversational board answers in your own words:\nevery number comes from your data, not from a guess."}),
    ("/asistente", {
        "es": "¿Una duda sobre el producto? El asistente contesta al lado,\ncon la documentación adentro.",
        "pt": "Uma dúvida sobre o produto? O assistente responde ali mesmo,\ncom a documentação dentro.",
        "en": "A question about the product? The assistant answers right there,\nwith the documentation built in."}),
    ("/gestores", {
        "es": "El equipo humano se mide acá:\nrecupero por gestor, por mes y por canal.",
        "pt": "A equipe humana é medida aqui:\nrecuperação por atendente, por mês e por canal.",
        "en": "The human team is measured here:\nrecovery by agent, by month and by channel."}),
    ("/calidad", {
        "es": "Y calidad revisa cada gestión:\nhorarios, topes y lista de no contactar, siempre.",
        "pt": "E a qualidade revisa cada atendimento:\nhorários, limites e lista de não contatar, sempre.",
        "en": "And quality reviews every interaction:\ncalling hours, caps and the do-not-contact list, always."}),
    ("/ingenieria-datos", [{
        "es": "Ingeniería de datos incluida: conectá SQL, CSV o Excel.",
        "pt": "Engenharia de dados incluída: conecte SQL, CSV ou Excel.",
        "en": "Data engineering included: connect SQL, CSV or Excel."}, {
        "es": "Subimos la cartera y la perfila sola: tipos, claves, calidad\ny features listas — sin escribir una línea de código.",
        "pt": "Subimos a carteira e ela é perfilada sozinha: tipos, chaves,\nqualidade e features prontas — sem escrever uma linha de código.",
        "en": "We upload the portfolio and it profiles itself: types, keys,\nquality and ready features — without writing a line of code."}]),
    ("/gobernanza", {
        "es": "Gobernanza responde qué dato es personal, quién lo ve\ny qué calidad tiene, en las seis dimensiones DAMA.",
        "pt": "A governança responde qual dado é pessoal, quem vê\ne qual a qualidade, nas seis dimensões DAMA.",
        "en": "Governance answers which data is personal, who can see it\nand how good it is, across the six DAMA dimensions."}),
    ("/medidas", {
        "es": "KPIs propios: definí tu indicador con una fórmula\ny usalo en todo el tablero.",
        "pt": "KPIs próprios: defina o seu indicador com uma fórmula\ne use em todo o painel.",
        "en": "Custom KPIs: define your own indicator with a formula\nand use it across the board."}),
    ("/automl", [{
        "es": "AutoML entrena acá mismo con tu propio dataset. Mirá:\nsubimos el histórico y elegimos qué predecir.",
        "pt": "O AutoML treina aqui mesmo com o seu próprio dataset. Veja:\nsubimos o histórico e escolhemos o que prever.",
        "en": "AutoML trains right here on your own dataset. Watch:\nwe upload the history and choose what to predict."}, {
        "es": "Prueba varios modelos y se queda con el mejor. La métrica que muestra\nsale de un holdout que no se usó para elegir nada.",
        "pt": "Testa vários modelos e fica com o melhor. A métrica que mostra\nvem de um holdout que não foi usado para escolher nada.",
        "en": "It tries several models and keeps the best. The metric it shows\ncomes from a holdout never used to choose anything."}]),
    ("/logistica", {
        "es": "Logística, un módulo aparte: qué ofertar,\nqué reponer y a qué cliente recuperar.",
        "pt": "Logística, um módulo à parte: o que ofertar,\no que repor e qual cliente recuperar.",
        "en": "Logistics, sold separately: what to discount,\nwhat to restock and which customer to win back."}),
    ("/proyectos", {
        "es": "Y Proyectos: salud del portafolio\ny backlog ordenado por valor esperado.",
        "pt": "E Projetos: saúde do portfólio\ne backlog ordenado por valor esperado.",
        "en": "And Projects: portfolio health\nand the backlog ranked by expected value."}),
    ("/roi", {
        "es": "El resultado se mide acá: más recupero con menos gestiones.\nMV Kobra AI, de punta a punta. mvkobranzaia.com",
        "pt": "O resultado se mede aqui: mais recuperação com menos gestões.\nMV Kobra AI, de ponta a ponta. mvkobranzaia.com",
        "en": "The result is measured here: more recovery with less effort.\nMV Kobra AI, end to end. mvkobranzaia.com"}),
]


def _marca(segundos: float) -> str:
    """Segundos → `HH:MM:SS.mmm`, el formato que exige WebVTT."""
    ms = int(round(segundos * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def vtt(idioma: str, cues=None) -> str:
    """Pista WebVTT completa para un idioma."""
    cues = CUES if cues is None else cues
    faltan = [i for i, c in enumerate(cues) if idioma not in c[2]]
    if faltan:
        raise ValueError(f"faltan cues en {idioma!r}: {faltan}")
    partes = ["WEBVTT", ""]
    for n, (ini, fin, textos) in enumerate(cues, start=1):
        partes += [str(n), f"{_marca(ini)} --> {_marca(fin)}",
                   textos[idioma], ""]
    return "\n".join(partes)


def generar(destino: str | None = None) -> dict[str, str]:
    """Escribe `copiloto.*.vtt` y `suite.*.vtt` en `landing/video/`.

    La película NO se genera acá: sus tiempos salen de la narración medida de
    cada idioma, así que los escribe `marketing/pelicula_demo.py` junto con el
    video que le corresponde. Escribirlos desde dos lados era justamente lo
    que los desincronizaba.
    """
    destino = destino or VIDEO_DIR
    os.makedirs(destino, exist_ok=True)
    salida = {}
    for nombre, cues in (("copiloto", CUES), ("suite", SUITE_CUES)):
        for idioma in IDIOMAS:
            ruta = os.path.join(destino, f"{nombre}.{idioma}.vtt")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(vtt(idioma, cues))
            salida[f"{nombre}.{idioma}"] = ruta
    return salida


if __name__ == "__main__":
    _CUES_POR_NOMBRE = {"copiloto": CUES, "suite": SUITE_CUES}
    for clave, ruta in generar().items():
        n = len(_CUES_POR_NOMBRE[clave.split(".")[0]])
        print(f"[OK] {clave}  {n} subtítulos  {os.path.relpath(ruta, ROOT)}")
