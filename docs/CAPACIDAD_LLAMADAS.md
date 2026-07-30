# Capacidad: cuántas llamadas simultáneas aguanta

Respuesta corta: **50 conversaciones simultáneas por proceso, entrantes y
salientes, sin un solo error.** Ese es el tope configurado (`KOBRA_MAX_LLAMADAS`,
default 50 = el plan de 50 gestores) y está medido, no estimado.

Todo lo que sigue sale de correr el servidor de verdad y pegarle carga.
Máquina de la medición: 4 núcleos, 16 GB, un solo worker de uvicorn, sin key de
LLM (motor 100% local).

## Entrantes (chatvoice TwiML + chatbot WhatsApp)

Cada "conversación" es completa: saludo + 3 turnos + cierre.

| Simultáneas | Atendidas | Rechazadas | Errores | p50 | p95 |
|---|---|---|---|---|---|
| 1  | 1  | 0   | 0 | 0,16 s | 0,16 s |
| 10 | 10 | 0   | 0 | 0,88 s | 1,74 s |
| 25 | 25 | 0   | 0 | 1,07 s | 2,35 s |
| **50** | **50** | **0** | **0** | **2,19 s** | **3,46 s** |
| 100 | 50 | 50  | 0 | 4,77 s | 6,12 s |
| 200 | 50 | 150 | 0 | 12,08 s | 13,77 s |

Pasado el tope, la llamada 51 **se rechaza con un mensaje**, no se acepta y se
hace esperar: por voz escucha *"en este momento todas nuestras líneas están
ocupadas, lo volvemos a llamar en unos minutos"*, y por WhatsApp el proxy del
canal recibe `503` con `Retry-After: 5` y reintenta. Verificado con 70 llamadas
entrantes que no cierran nunca: **50 atendidas, 20 rechazadas, 0 errores HTTP,
0 excepciones.**

Es a propósito. Una llamada rechazada se reintenta; una llamada aceptada y
degradada se pierde con el cliente adentro.

## Salientes (campaña del voicebot)

| Líneas | Llamadas | Segundos | Pico | OK | Errores |
|---|---|---|---|---|---|
| 1  | 1  | 0,07 | 1  | 1  | 0 |
| 10 | 10 | 0,28 | 10 | 10 | 0 |
| 25 | 25 | 0,69 | 25 | 25 | 0 |
| **50** | **50** | **1,32** | **50** | **50** | **0** |

El throughput satura en ~37 llamadas/s desde las 10 líneas: el cuello es CPU,
no el canal. Con 50 líneas la campaña cierra 50 negociaciones completas en 1,3
segundos.

## Cómo subir de 50

`KOBRA_MAX_LLAMADAS` sube el tope por proceso, pero el límite real es la CPU.
Para crecer de verdad se suman procesos:

```
KOBRA_WORKERS=4 python -m realtime.server      # 4 × 50 = 200 simultáneas
```

`GET /capacidad` dice en vivo cuántas hay en curso y cuántas entran todavía —
es la señal para decidir cuándo sumar workers:

```json
{"limite_por_worker": 50,
 "voz": {"en_curso": 37, "libres": 13, "pico": 50, "rechazadas": 12, ...}}
```

Ojo: el tope es **por worker**. `kobra.concurrencia.capacidad_total(workers)` lo
deja explícito para no vender 4× de capacidad sin la RAM detrás.

## Con LLM la cuenta es otra

Todo lo de arriba es con el motor local. Con `ANTHROPIC_API_KEY` puesta, cada
turno del Gestor IA espera a la API del modelo, y esa espera **es tiempo de
red**: la capacidad ya no la fija la CPU sino cuántas esperas se pueden tener
abiertas a la vez. Por eso el diálogo corre en el threadpool y no en el event
loop — ver abajo.

Medido con un LLM simulado de 300 ms y 50 conversaciones simultáneas:

| Dónde corre la espera | 1 | 10 | 50 |
|---|---|---|---|
| En el event loop (como estaba) | 0,30 s | 3,03 s | **15,10 s** |
| En el threadpool (como está ahora) | 0,31 s | 0,32 s | **0,66 s** |

15,10 s = 50 × 0,30: serialización perfecta. Con la plataforma de telefonía
esperando el TwiML del turno, una demora así corta la llamada. Es decir: **con
Claude activado el techo real no eran 50 llamadas, eran 2 o 3.**

## Qué se arregló para llegar a esto

| Defecto | Cómo se veía | Evidencia |
|---|---|---|
| El diálogo corría en el event loop | Con LLM, las llamadas se atendían de a una | 15,10 s vs 0,66 s con 50 simultáneas |
| `timeout_keep_alive` de uvicorn en 5 s | Llamadas caídas a mitad de la negociación cuando el servidor estaba ocupado | 100 simultáneas: 5 a 13 caídas con 5 s, **0 con 120 s** |
| Sin tope de sesiones | La llamada 51 entraba igual y degradaba a las 50 en curso | 70 entrantes → 50 atendidas + 20 rechazadas |
| Sesiones sin vencimiento | 500 llamadas abandonadas = 500 sesiones vivas para siempre | ahora vencen a los 900 s de inactividad |
| Uploads a `/tmp/<nombre del cliente>` | Dos gestores subiendo `grabacion.wav` a la vez | con 4 workers: 7 de 30 respuestas mal (HTTP 400, o el análisis de OTRA llamada); con nombres únicos, 30/30 |
| `--lineas` solo se recortaba en el CLI | Llamando la función entraban 200 líneas | ahora el tope está en `correr_campania` |

El de `/tmp` merece una nota: con **un** worker no se reproducía, porque el
análisis es sincrónico y ninguna otra petición se mete en el medio. Aparece
apenas hay varios workers — que es justamente el despliegue que este documento
recomienda para pasar de 50. Era una bomba con temporizador.

## Reproducir las mediciones

```
python -m realtime.server                 # o KOBRA_WORKERS=4
python -m pytest -q tests/test_concurrencia.py
```

Los tests fijan las conductas (tope, vencimiento, threadpool, nombres únicos);
las tablas de arriba salen de pegarle carga real al servidor.

## Variables de entorno

| Variable | Default | Qué hace |
|---|---|---|
| `KOBRA_MAX_LLAMADAS` | 50 | Conversaciones simultáneas por proceso |
| `KOBRA_TTL_SESION_SEG` | 900 | Inactividad tras la cual se libera la sesión |
| `KOBRA_KEEPALIVE_SEG` | 120 | `timeout_keep_alive` de uvicorn |
| `KOBRA_WORKERS` | 1 | Procesos de uvicorn |
