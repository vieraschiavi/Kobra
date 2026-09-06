# Proyección de cobranza — qué se evaluó, con qué resultado y qué se decidió

> Backtest corrido el 2026-09-06 sobre la cartera de demostración
> (331 días de cobranza diaria, 100% sintética). Reproducible con
> `python3 -m kobra.proyeccion` no: se corre desde el endpoint
> `/api/proyeccion-cobranza` o con el script de `tests/test_proyeccion.py`.

## La pregunta

¿Sirve meter un modelo fundacional de series de tiempo (TimesFM, de Google)
para proyectar cuánto se va a cobrar?

La respuesta corta: **el modelo anda, la serie de la demo no da**. Y esa
distinción es el producto.

## Qué es TimesFM y por qué se lo miró

Es un modelo preentrenado sobre cientos de miles de millones de puntos de
series temporales: predice una serie que nunca vio, sin entrenarlo. En los
benchmarks públicos (GIFT-Eval, fev-bench) sale primero entre los modelos
fundacionales.

### La licencia decidió la versión antes que la técnica

| Versión | Código | Pesos | ¿Se puede usar acá? |
|---|---|---|---|
| 3.0 | Apache-2.0 | `timesfm-non-commercial-license-v1.0` | **No.** Prohíbe uso comercial y en producción |
| **2.5** | Apache-2.0 | **Apache-2.0** | **Sí** |
| 1.0 / 2.0 | Apache-2.0 | Apache-2.0 | Sí, pero superadas por la 2.5 |

MV Kobra AI se vende. Usar los pesos de la 3.0 sería incumplir su licencia, así
que el adaptador carga **solamente** `google/timesfm-2.5-200m-pytorch` y hay un
test que falla si alguien lo apunta a la 3.0.

## El método: doble ventana, sin excepciones

Origen rodante sobre dos tramos que no se tocan:

1. **Ventana de selección** (6 orígenes) — acá se elige el modelo.
2. **Holdout ciego** (4 orígenes) — no se usó para elegir nada. **Es el único
   número que se reporta como performance esperada.**

La vara es el **MASE**: el error dividido por el del ingenuo estacional.
Menos de 1 = mejor que repetir la semana pasada. Un MAE en pesos no dice nada
solo: $400.000 de error es excelente en una cartera que cobra 8 millones por
día y ridículo en una que cobra 500.000.

## Resultados sobre la cartera de demostración

Serie: cobranza diaria por fecha de pago, n=331, media $825.333, sd $1.068.884.

### Horizonte 14 días

| Modelo | MASE selección | **MASE holdout** | sMAPE | MAE $/día |
|---|---|---|---|---|
| media (promedio simple) | 1,062 | **0,974** | 72,9% | 843.399 |
| TimesFM 2.5 | 1,105 | 1,025 | 81,5% | 888.684 |
| media móvil 28 | 1,159 | 1,049 | 75,9% | 908.520 |
| ingenuo | 1,974 | 1,120 | 104,7% | 971.382 |
| deriva | 2,028 | 1,124 | 108,4% | 974.956 |
| perfil semanal | 1,142 | 1,133 | 79,9% | 982.664 |
| estacional 7 | 1,714 | 1,238 | 110,1% | 1.075.755 |

**Gana el promedio simple.** Un modelo de 200 millones de parámetros queda
segundo detrás de `mean()`. No es un defecto de TimesFM: es que la serie no
tiene estructura temporal que aprovechar — es ruido alrededor de un promedio.

### El resultado que casi publico mal

Con la referencia fija (ingenuo estacional) el titular daba
**«el modelo mejora 23%»**. Es cierto y es inútil: el ingenuo estacional rinde
MASE 1,24 en esta serie, o sea que es *malo acá*, y ganarle no significa nada.

Por eso la decisión no se toma contra una referencia elegida de antemano sino
contra **el mejor de los modelos que no aprenden nada** (`ingenuo`,
`estacional_7`, `media`). Contra esa vara, ninguno mejora: veredicto
**sin señal**.

## Controles: que el arnés no diga siempre que no

Un backtest que rechaza todo es tan inútil como uno que acepta todo.

| Serie de control | Resultado | ¿Correcto? |
|---|---|---|
| Semana con forma + fin de mes + tendencia | **TimesFM gana, MASE 0,65, +43% vs. el mejor trivial** → proyecta | Sí: hay señal y la encuentra |
| Misma forma con mucho ruido | gana el promedio → no proyecta | Sí: la señal se perdió en el ruido |
| Ruido puro | TimesFM sale +8% pero **se rechaza por margen** | Sí: con 4 ventanas, un 8% es suerte |

El tercero es el más importante: sin el margen mínimo del 10%, ese +8% se
publicaba como una mejora.

## Qué se decidió

1. **El módulo entra** (`kobra/proyeccion.py`), con seis modelos base y el
   backtest de doble ventana como parte del producto, no como un script.
2. **La pantalla puede decir que no.** Cuando no hay señal muestra el promedio,
   con la línea **punteada y gris**, y el texto «esto es un promedio, no una
   predicción». Una curva prolija sobre ruido termina en la meta del mes de
   alguien.
3. **TimesFM queda opcional** (`kobra/proyeccion_timesfm.py`), fuera del
   instalador:
   - pesa 925 MB + PyTorch (~200 MB) contra un instalador de 270 MB;
   - el programa instalado **no tiene internet**, así que no puede bajar pesos
     en el primer arranque;
   - en la demo no mejora nada.

   Si el cliente lo quiere sobre su cartera real, se instala `timesfm[torch]`,
   se copian los pesos a una carpeta y se apunta `KOBRA_TIMESFM_DIR`. El
   backtest decide solo si se usa: **compite, no se impone**.

## Cómo lo ve un cliente con datos propios

El veredicto se recalcula sobre la cartera de cada empresa. Una cartera con
forma de semana —cobranza que cae los sábados, pico los días de sueldo— va a
dar `sirve: true` y ahí la proyección se dibuja en verde y continua. Es el
mismo código, decidiendo distinto porque los datos son distintos.
