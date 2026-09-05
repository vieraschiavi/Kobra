# © 2026 Martín Viera. Todos los derechos reservados.

"""
MV Kobra AI · Memoria técnica del pipeline
===========================================
Qué hace el programa, en orden, contado dos veces: una para quien va a leer el
código y otra para quien va a firmar la compra.

Por qué dos registros y no un resumen
--------------------------------------
Un solo texto no sirve a los dos lectores. El técnico necesita saber qué
modelo, con qué validación y qué pasa si falla; el gerente necesita saber qué
problema resuelve y qué cambia en su operación. Escribir "en el medio" produce
un documento que no le alcanza a ninguno: al programador le falta precisión y
al gerente le sobra jerga.

Acá cada etapa lleva los dos textos completos. La pantalla y los exports los
muestran juntos, y el lector elige.

Por qué es DATO y no un .md suelto
-----------------------------------
Un documento en Markdown se desactualiza en silencio: el código cambia, nadie
lo lee, y a los seis meses describe un programa que ya no existe. Acá cada
etapa nombra los módulos reales que la implementan, y
`tests/test_memoria_tecnica.py` falla si alguno deja de existir. No garantiza
que el texto sea verdad —eso no lo puede verificar una máquina—, pero sí que
no quede describiendo módulos borrados.

El orden es el del pipeline real (`kobra/pipeline.py` y lo que la app llama
después), no un orden temático: la pregunta que este documento contesta es
"¿qué le pasa a un dato desde que entra hasta que sale?".
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Etapa:
    """Una etapa del pipeline, contada para los dos lectores.

    `frozen=True`: el catálogo se lee desde la API, los exports y los tests a
    la vez. Que nadie pueda mutarlo al pasar evita que un export salga distinto
    de la pantalla que lo generó.
    """
    orden: int
    id: str
    titulo: str
    # Para quien lee el código: qué hace, con qué, y qué pasa si falla.
    tecnico: str
    # Para quien firma la compra: qué problema resuelve, en castellano llano.
    criollo: str
    # Por qué existe. Casi siempre: qué se rompía antes.
    por_que: str
    # Qué cambia aguas abajo. Es lo que convierte una lista en un pipeline.
    repercusion: str
    modulos: tuple[str, ...]
    entradas: str
    salidas: str
    # Lo que esta etapa NO hace. Un documento de venta que solo suma es
    # publicidad; los límites son lo que lo vuelve creíble en una auditoría.
    limites: str = ""
    etiquetas: tuple[str, ...] = field(default_factory=tuple)


ETAPAS: tuple[Etapa, ...] = (
    Etapa(
        orden=1,
        id="ingesta",
        titulo="Ingesta de datos",
        tecnico=(
            "Lee la cartera desde tres orígenes distintos y los normaliza a un "
            "único DataFrame: archivo (CSV/XLSX subido por pantalla), base de "
            "datos (SQLite, PostgreSQL, MySQL o SQL Server vía SQLAlchemy) y el "
            "generador sintético con semilla fija. La detección de separador, "
            "encoding y tipos es automática; las columnas se mapean a nombres "
            "canónicos antes de seguir. Un archivo que no es tabla se rechaza "
            "con 400 y un mensaje que dice qué se esperaba, no con un 500."),
        criollo=(
            "Es la puerta de entrada. Le das tu cartera como venga —un Excel, "
            "un CSV, o conectando directo a tu base— y el programa la entiende "
            "sola: se da cuenta de si el archivo usa comas o punto y coma, si "
            "los acentos vienen rotos, y qué columna es cuál. No hay que "
            "preparar nada antes ni pedirle a sistemas que te arme un formato "
            "especial."),
        por_que=(
            "Ninguna empresa tiene la cartera en el formato que espera un "
            "programa nuevo. Si la primera pantalla exige un CSV con 27 "
            "columnas en orden, la prueba se muere ahí: nadie va a pedirle a "
            "IT que lo prepare para evaluar un producto que todavía no compró."),
        repercusion=(
            "Todo lo que sigue asume nombres de columna canónicos. Si esta "
            "etapa mapea mal, el modelo entrena con la columna equivocada y "
            "nada aguas abajo lo nota: por eso el perfilado de la etapa 2 corre "
            "inmediatamente después y no al final."),
        modulos=("kobra/fuentes_datos.py", "kobra/cartera_manual.py",
                 "kobra/consulta_bd.py", "data/generate_dataset.py"),
        entradas="CSV / XLSX / conexión a base / generador sintético",
        salidas="DataFrame de cartera con nombres de columna canónicos",
        limites=(
            "No adivina una columna que no está. Si falta el monto de deuda o "
            "los días de mora, lo dice y corta: inventar ese dato sería peor "
            "que no tenerlo."),
        etiquetas=("datos", "entrada"),
    ),
    Etapa(
        orden=2,
        id="ingenieria",
        titulo="Ingeniería de datos y perfilado",
        tecnico=(
            "Perfila cada columna (tipo inferido, nulos, cardinalidad, rango, "
            "outliers), propone el rol de cada una (identificador, categórica, "
            "numérica, fecha, objetivo), detecta claves candidatas y sugiere "
            "joins entre tablas. Deriva features: antigüedad de mora en tramos, "
            "ratios monto/ingreso, agregados por deudor y variables de "
            "contactabilidad histórica."),
        criollo=(
            "Antes de calcular nada, el programa mira tus datos y te dice qué "
            "tiene entre manos: cuántos vacíos hay, qué columnas son sospechosas, "
            "cuáles sirven para predecir y cuáles no. Es el paso que en una "
            "consultora te cobran como 'diagnóstico de datos' y que acá sale "
            "automático y en pantalla."),
        por_que=(
            "El 80% de los proyectos de scoring fracasan por datos, no por "
            "modelo. Mostrar el perfilado ANTES de entrenar hace que el problema "
            "aparezca cuando todavía es barato arreglarlo — y le da al cliente "
            "una foto honesta de su propia cartera, que muchas veces es la "
            "primera vez que la ve."),
        repercusion=(
            "Las features que se derivan acá son las que el modelo va a usar. "
            "Una columna mal tipada convierte una variable predictiva en ruido, "
            "y el efecto se ve recién en el AUC de la etapa 4."),
        modulos=("kobra/ingenieria_datos.py",),
        entradas="DataFrame de cartera",
        salidas="Perfil por columna + features derivadas",
        limites=(
            "Sugiere roles y joins; no los aplica solo. La decisión sobre qué "
            "columna es el objetivo la toma una persona."),
        etiquetas=("datos", "calidad"),
    ),
    Etapa(
        orden=3,
        id="gobernanza",
        titulo="Gobernanza, linaje y datos personales",
        tecnico=(
            "Clasifica cada columna por sensibilidad (pública, interna, "
            "confidencial, personal), aplica seudonimización y enmascarado "
            "según el rol del usuario, y registra el linaje de cada "
            "transformación y export en un log consultable: qué salió, quién, "
            "cuándo y sobre cuántas filas."),
        criollo=(
            "El programa sabe qué datos son personales y quién puede verlos. "
            "Un gestor no ve el documento completo del deudor; un auditor sí, y "
            "queda registrado que lo miró. Cada archivo que sale del sistema "
            "deja rastro: qué se llevó, quién y cuándo."),
        por_que=(
            "Cobranzas trabaja con datos personales de gente que debe plata: es "
            "el escenario donde una filtración duele más. Y sin linaje, la "
            "primera pregunta de una auditoría —'¿quién exportó esto?'— no "
            "tiene respuesta."),
        repercusion=(
            "El enmascarado se aplica en la capa de datos, no en la pantalla: "
            "por eso también protege los exports de las etapas 12 y 13, que es "
            "por donde un dato realmente se va de la empresa."),
        modulos=("kobra/gobernanza.py", "kobra/auditoria.py"),
        entradas="DataFrame + rol del usuario",
        salidas="Vista autorizada del dato + registro de linaje",
        limites=(
            "Protege contra el acceso indebido dentro del programa. No cifra la "
            "base de datos del cliente ni reemplaza sus controles de red."),
        etiquetas=("seguridad", "cumplimiento"),
    ),
    Etapa(
        orden=4,
        id="probpago",
        titulo="ProbPago — modelo de probabilidad de pago",
        tecnico=(
            "Entrena y compara varios clasificadores (Gradient Boosting, "
            "Random Forest, regresión logística), selecciona por AUC-ROC sobre "
            "validación y calibra las probabilidades para que un 0,30 signifique "
            "de verdad 30% de casos que pagan. Reporta AUC-ROC, average "
            "precision y lift del decil 10. Si no hay modelo entrenado "
            "previamente, cae a un Gradient Boosting ad-hoc en la misma corrida."),
        criollo=(
            "Le pone a cada deudor un número del 0 al 100%: qué chance hay de "
            "que pague. No es una opinión ni una regla fija tipo 'más de 90 días "
            "es incobrable': sale de los patrones de tu propia cartera histórica. "
            "Con eso podés ordenar a quién llamar primero, que es donde se gana "
            "o se pierde el mes."),
        por_que=(
            "Sin score, la cartera se gestiona por antigüedad o por monto, que "
            "es lo que hace todo el mundo y por eso todos recuperan parecido. "
            "El lift del decil 10 dice cuánto mejor es llamar al 10% que el "
            "modelo elige, contra llamar al azar."),
        repercusion=(
            "La ProbPago es la entrada de TODO lo que sigue: la estrategia de la "
            "etapa 6, la priorización de la 8 y el valor esperado de recupero de "
            "la 12 se calculan a partir de este número. Un modelo mal calibrado "
            "no da 'un poco peor': desordena la cola de llamado entera."),
        modulos=("kobra/probpago.py", "kobra/train.py"),
        entradas="Cartera con features derivadas",
        salidas="probpago (0-1), decil, segmento de propensión, métricas",
        limites=(
            "Predice sobre la población que se le enseñó. Una cartera de otro "
            "producto o de otro país necesita reentrenar; los números de la demo "
            "salen de datos SINTÉTICOS y son ilustrativos."),
        etiquetas=("ml", "núcleo"),
    ),
    Etapa(
        orden=5,
        id="explicabilidad",
        titulo="Explicabilidad — por qué ese número",
        tecnico=(
            "Genera reason codes por deudor: compara el caso contra la línea "
            "base de la cartera y devuelve las variables que más empujaron la "
            "predicción hacia arriba o hacia abajo, en texto legible y no como "
            "un vector de contribuciones."),
        criollo=(
            "Al lado de cada score dice POR QUÉ. 'Probabilidad baja: 180 días de "
            "mora y tres promesas incumplidas'. Sin eso, el gestor no le cree al "
            "número y sigue usando su criterio — y el sistema más caro es el que "
            "se compra y no se usa."),
        por_que=(
            "Un modelo que no se puede explicar no se puede defender: ni ante el "
            "gestor que lo usa, ni ante el gerente que lo aprueba, ni ante un "
            "regulador que pregunta por qué a esa persona se la trató distinto."),
        repercusion=(
            "El motivo viaja pegado al deudor hasta el guion de la etapa 9: el "
            "Agente IA arranca sabiendo por qué este caso es difícil, en vez de "
            "abrir con un texto genérico."),
        modulos=("kobra/explicabilidad.py",),
        entradas="Modelo entrenado + cartera scoreada",
        salidas="motivo_probpago (texto) por deudor",
        limites=(
            "Explica la predicción del modelo, no la causa real del "
            "incumplimiento. Son cosas distintas y el texto no las confunde."),
        etiquetas=("ml", "confianza"),
    ),
    Etapa(
        orden=6,
        id="negociador",
        titulo="Agente Negociador — estrategia por deudor",
        tecnico=(
            "Cruza ProbPago, monto, tramo de mora y contactabilidad para "
            "asignar estrategia (quita, plan de cuotas, seguimiento, gestión "
            "intensiva), y calcula descuento recomendado, cantidad de cuotas y "
            "valor esperado de recupero por caso. Devuelve también el resumen "
            "agregado por estrategia."),
        criollo=(
            "Decide qué ofrecerle a cada uno. A quien puede pagar y está por "
            "hacerlo, no le regala descuento; a quien no va a pagar nunca sin "
            "una quita, se la ofrece antes de gastar diez llamadas. Es la "
            "diferencia entre una política igual para todos y una decisión por "
            "cliente."),
        por_que=(
            "El descuento es plata que se resigna. Darlo parejo cuesta margen "
            "con los que iban a pagar igual, y no alcanza con los que necesitan "
            "más. Repartirlo según la probabilidad de pago es lo que hace que la "
            "misma cartera rinda distinto."),
        repercusion=(
            "La estrategia define el guion de la etapa 9 y la prioridad con la "
            "que el caso entra en la agenda de la etapa 8. Es la traducción de "
            "'este deudor tiene 0,42' a 'a este deudor hacele esta oferta'."),
        modulos=("kobra/negociador.py",),
        entradas="Cartera scoreada",
        salidas="estrategia, descuento, plan de cuotas, valor esperado, prioridad",
        limites=(
            "Recomienda dentro de los límites que configura la empresa. No "
            "aprueba quitas solo: el tope de descuento es un parámetro, no una "
            "decisión del modelo."),
        etiquetas=("negocio", "núcleo"),
    ),
    Etapa(
        orden=7,
        id="cumplimiento",
        titulo="Motor de cumplimiento legal",
        tecnico=(
            "Antes de habilitar cualquier contacto evalúa: franja horaria legal "
            "por país, feriados, día hábil, tope de intentos por período y "
            "pedidos de no-contactar. Devuelve la decisión con el motivo "
            "codificado y traducido, no un booleano pelado."),
        criollo=(
            "El programa no deja llamar fuera de hora, ni en feriado, ni al que "
            "pidió que no lo llamen más. Y cuando bloquea, dice por qué. Es lo "
            "que separa 'el sistema está cumpliendo la ley' de 'el sistema no "
            "anda'."),
        por_que=(
            "Una multa por gestión fuera de horario cuesta más que el software. "
            "Y el riesgo no es teórico: el gestor con presión de cierre de mes "
            "llama igual si el sistema se lo permite."),
        repercusion=(
            "Corta antes que la campaña de la etapa 8: un deudor bloqueado no "
            "entra en el plan del día. Cuando el plan sale vacío, la pantalla "
            "muestra el motivo en vez de una tabla en blanco."),
        modulos=("kobra/cumplimiento.py",),
        entradas="Deudor + fecha y hora + país + historial de intentos",
        salidas="Decisión de contacto + motivo codificado",
        limites=(
            "Cubre horarios, feriados, tope de intentos y no-contactar. No "
            "reemplaza asesoramiento legal ni la política interna de la empresa."),
        etiquetas=("cumplimiento", "riesgo"),
    ),
    Etapa(
        orden=8,
        id="campana",
        titulo="Campaña y elección del canal",
        tecnico=(
            "Arma el plan de contacto del día. El canal sale de la "
            "contactabilidad REAL del deudor —dónde se lo contactó o dónde cerró "
            "en los últimos 90 días— y, sin historial, de la regla de negocio. "
            "Cada fila expone el canal, su origen (historial o regla) y la hora "
            "preferida, para que se vea cuál de las dos decidió."),
        criollo=(
            "Arma la lista de a quién contactar hoy y por dónde. Si a alguien "
            "siempre le respondieron por WhatsApp, va por WhatsApp; si nunca se "
            "lo pudo ubicar por teléfono, no se gastan llamadas. Y la pantalla "
            "marca cuándo la decisión salió del historial y cuándo de la regla, "
            "para que el operador sepa cuánto confiar."),
        por_que=(
            "Elegir el canal por costumbre gasta el recurso más caro —el tiempo "
            "del gestor— en el medio que menos responde. La contactabilidad ya "
            "estaba en los datos; solo no se estaba usando para decidir."),
        repercusion=(
            "Define por dónde entra el Agente IA de la etapa 9: mismo caso, "
            "guion distinto según sea llamada o WhatsApp. Y filtra por lo que "
            "decidió la etapa 7."),
        modulos=("kobra/campana.py",),
        entradas="Cartera priorizada + historial de contactabilidad + cumplimiento",
        salidas="Plan de contacto del día (deudor, canal, origen, hora, motivo)",
        limites=(
            "Propone; no disca solo. La integración telefónica y de WhatsApp "
            "requiere las credenciales del cliente."),
        etiquetas=("negocio", "operación"),
    ),
    Etapa(
        orden=9,
        id="gestor_ia",
        titulo="Agente IA negociador (chat y voz)",
        tecnico=(
            "Interpreta lo que dice el deudor, evalúa la oferta contra los "
            "límites configurados y produce la respuesta y el guion turno a "
            "turno. La conversación queda como estructura (quién dice qué), no "
            "como texto plano, para poder evaluarla después."),
        criollo=(
            "Negocia. Entiende lo que contesta el deudor —'no tengo trabajo', "
            "'pago la mitad ahora'— y responde con una oferta que está dentro de "
            "lo que la empresa autorizó. Se puede leer la conversación entera y "
            "también escucharla."),
        por_que=(
            "El cuello de botella de cobranzas es la cantidad de conversaciones "
            "que un equipo puede sostener por día. Y la calidad de esas "
            "conversaciones depende de quién esté de turno."),
        repercusion=(
            "Lo que pasa acá alimenta la evaluación de calidad de la etapa 11 y "
            "los KPIs de la 12: la conversación es el dato, no un subproducto."),
        modulos=("kobra/gestor_ia.py", "kobra/llm.py",
                 "webapp/frontend/src/pages/Asistente.jsx"),
        entradas="Deudor + estrategia + canal + mensaje del deudor",
        salidas="Turnos de negociación + oferta propuesta + resultado",
        limites=(
            "No cierra un acuerdo por fuera de los límites configurados. En la "
            "demo la voz es la del navegador; en producción habla la voz neural, "
            "y la pantalla lo aclara."),
        etiquetas=("ia", "núcleo"),
    ),
    Etapa(
        orden=10,
        id="copiloto",
        titulo="Copiloto en vivo — sentimiento y técnicas",
        tecnico=(
            "Sobre la conversación en curso analiza sentimiento, detecta "
            "técnicas de negociación (evasiva, promesa vaga, pedido de quita) y "
            "sugiere el siguiente movimiento. Funciona sobre texto y sobre voz "
            "transcripta."),
        criollo=(
            "Mientras el gestor habla, el programa escucha y le sopla: 'está "
            "enojándose, bajá el tono', 'te está dando una promesa sin fecha, "
            "pedile día'. Es el supervisor que no puede estar en las 40 llamadas "
            "a la vez."),
        por_que=(
            "La diferencia entre el mejor gestor y el promedio es enorme y no se "
            "transfiere con capacitación anual. Sugerir en el momento es lo "
            "único que cambia la llamada que está pasando."),
        repercusion=(
            "Las señales detectadas quedan en la gestión y suben a la analítica "
            "de la etapa 12: se puede medir si el equipo mejora."),
        modulos=("kobra/copiloto.py", "kobra/voz.py", "realtime/"),
        entradas="Conversación en curso (texto o voz transcripta)",
        salidas="Sentimiento, técnicas detectadas, sugerencia siguiente",
        limites=(
            "Sugiere; no interrumpe ni corta la llamada. La transcripción de voz "
            "depende del motor configurado."),
        etiquetas=("ia", "operación"),
    ),
    Etapa(
        orden=11,
        id="calidad",
        titulo="Calidad de gestión",
        tecnico=(
            "Evalúa cada gestión contra criterios ponderados (identificación, "
            "escucha, manejo de objeciones, cierre, cumplimiento normativo) y "
            "produce nota por gestión, perfil por criterio, evolución temporal y "
            "ranking. La comparación del equipo se hace contra una referencia "
            "externa, no contra su propio promedio."),
        criollo=(
            "Le pone nota a cada gestión y dice en qué falla cada gestor: uno no "
            "cierra, otro no maneja objeciones. Reemplaza la escucha de tres "
            "llamadas al azar por mes con una foto de todas."),
        por_que=(
            "Comparar al equipo contra su propio promedio da siempre cero: la "
            "mitad está arriba y la mitad abajo, y no se ve si el equipo entero "
            "es bueno o malo. Contra una referencia externa el número dice algo."),
        repercusion=(
            "Alimenta el impacto de calidad sobre recupero en la etapa 12: "
            "permite mostrar que las gestiones mejor evaluadas cobran más, que "
            "es el argumento para invertir en formación."),
        modulos=("kobra/calidad_gestion.py",),
        entradas="Gestiones registradas + conversaciones",
        salidas="Nota por gestión, perfil por criterio, ranking, evolución",
        limites=(
            "Evalúa lo que quedó registrado. Una gestión que no se registró no "
            "existe para el sistema."),
        etiquetas=("calidad", "gestión"),
    ),
    Etapa(
        orden=12,
        id="analitica",
        titulo="Analítica, KPIs e impacto",
        tecnico=(
            "Consolida KPIs de cartera (deudores, monto total, recupero "
            "esperado, ProbPago promedio, cartera en riesgo), evolución mensual, "
            "ranking de gestores, matriz de emociones e impacto de la calidad "
            "sobre el recupero. El ROI se estima con supuestos explícitos y "
            "editables, no con un número fijo."),
        criollo=(
            "El tablero que mira el gerente: cuánto hay, cuánto se espera "
            "recuperar, quién está rindiendo y qué pasó respecto del mes pasado. "
            "Y la estimación de retorno se puede tocar: si no estás de acuerdo "
            "con un supuesto, lo cambiás y ves el número nuevo."),
        por_que=(
            "Un ROI con los supuestos escondidos no se puede discutir, y lo que "
            "no se puede discutir no se aprueba. Mostrarlos convierte una "
            "promesa en una conversación."),
        repercusion=(
            "Es la capa que consume todo lo anterior. Si una etapa de arriba "
            "cambia, el efecto se ve acá — y por eso los números de esta pantalla "
            "son el primer lugar donde se nota una regresión."),
        modulos=("kobra/analitica.py", "kobra/roi.py", "kobra/medidas.py"),
        entradas="Cartera scoreada + gestiones + evaluaciones de calidad",
        salidas="KPIs, series mensuales, rankings, estimación de ROI",
        limites=(
            "En la demo los datos son sintéticos y las cifras de impacto son "
            "ILUSTRATIVAS. Con datos del cliente, los KPIs son reales y el ROI "
            "sigue siendo una estimación con supuestos a la vista."),
        etiquetas=("negocio", "gerencia"),
    ),
    Etapa(
        orden=13,
        id="exports",
        titulo="Informes y salida de datos",
        tecnico=(
            "Exporta cartera scoreada (CSV/XLSX con hojas de resumen y drivers "
            "del modelo), promesas vencidas, calidad, informe ejecutivo en PDF y "
            "esta memoria técnica en HTML/Word/PDF. Todo export pasa por la "
            "capa de gobernanza y queda en el linaje. Un error nunca se descarga "
            "como archivo: se muestra como error."),
        criollo=(
            "Todo lo que se ve en pantalla se puede bajar: Excel para trabajarlo, "
            "PDF para llevar al directorio. Y si algo falla, te lo dice — antes "
            "el error se bajaba como si fuera el archivo y Excel no lo abría."),
        por_que=(
            "El informe que no sale del programa no llega a la reunión donde se "
            "decide. Y un export que descarga un error disfrazado de Excel es la "
            "peor forma de fallar, porque parece que anduvo."),
        repercusion=(
            "Es la última etapa y la única por donde un dato se va de la "
            "empresa: por eso el enmascarado de la etapa 3 se aplica en la capa "
            "de datos y no en la pantalla."),
        modulos=("kobra/informe_ejecutivo.py", "kobra/memoria_tecnica.py",
                 "kobra/memoria_tecnica_export.py", "kobra/pipeline.py"),
        entradas="Todo lo anterior",
        salidas="CSV, XLSX, PDF, HTML, DOCX + registro de linaje",
        limites=(
            "El contenido de un export es la foto del momento en que se pidió. "
            "No se actualiza solo."),
        etiquetas=("salida", "gerencia"),
    ),
)


def etapas() -> tuple[Etapa, ...]:
    """El catálogo completo, en orden de pipeline."""
    return ETAPAS


def por_id(id_etapa: str) -> Etapa | None:
    return next((e for e in ETAPAS if e.id == id_etapa), None)


def como_dicts() -> list[dict]:
    """Para la API y el frontend. `dataclasses.asdict` convierte las tuplas en
    listas, que es lo que espera JSON."""
    from dataclasses import asdict
    return [asdict(e) for e in ETAPAS]


def etiquetas_disponibles() -> list[str]:
    """Las etiquetas usadas, ordenadas — la pantalla filtra por acá."""
    return sorted({t for e in ETAPAS for t in e.etiquetas})
