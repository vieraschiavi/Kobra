# Proyección de cobranza — qué se evaluó, con qué resultado y qué se decidió

> Backtest corrido el 2026-09-06 sobre la cartera de demostración
> (334 días de cobranza diaria, 100% sintética). Se reproduce desde el
> endpoint `/api/proyeccion-cobranza` o con `tests/test_proyeccion.py`.

## La pregunta

¿Sirve meter un modelo fundacional de series de tiempo (TimesFM, de Google)
para proyectar cuánto se va a cobrar?

La respuesta corta: **sirve, pero no gana**. Compite de igual a igual, le
gana a todos los baselines triviales y pierde contra un modelo mucho más
barato que aprende la forma de la semana. Lo que se quedó del ejercicio no es
TimesFM: es el arnés que decide, con evidencia, cuál se publica — y que en el
camino encontró un defecto en los datos de la demo.

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

## La primera corrida encontró un problema en los DATOS, no en el modelo

Sobre la cartera de demostración original, **ganaba el promedio simple**:
TimesFM quedaba segundo detrás de `mean()`, y ningún modelo le sacaba nada a
un baseline trivial.

La causa no era el modelo. El generador sorteaba el día de cada gestión con
`rng.integers(1, 28)`: repartido parejo, sin mirar siquiera qué día de la
semana era. O sea que la serie diaria era **ruido plano alrededor de un
promedio — la forma que ninguna cartera real tiene**. Una operación de
cobranza trabaja de lunes a viernes, el sábado a media máquina y el domingo
casi nada, y los pagos se amontonan alrededor del cobro del sueldo.

Se corrigió el generador (`data/generate_gestiones.py::PESO_DIA_SEMANA`) y la
demo pasó a tener la forma de una semana de verdad:

| lun | mar | mié | jue | vie | sáb | dom |
|---|---|---|---|---|---|---|
| 1.041k | 1.158k | 1.044k | 826k | 1.089k | **233k** | **109k** |

## Resultados sobre la cartera de demostración

Serie: cobranza diaria por fecha de pago, n=334, media $784.751.

| Modelo | MASE holdout (h=7) | MASE holdout (h=14) |
|---|---|---|
| **perfil semanal** | **1,172** | **1,021** |
| TimesFM 2.5 | 1,209 | 1,073 |
| media (promedio simple) | 1,346 | 1,236 |
| media móvil 28 | 1,394 | 1,343 |
| estacional 7 | 1,658 | 1,435 |
| ingenuo | 1,666 | 2,417 |
| deriva | 1,672 | 2,453 |

**Veredicto: sirve.** El perfil semanal le gana al mejor trivial por 13% (7
días) y 17% (14 días) en el holdout ciego, y el panel publica la proyección.

TimesFM queda **segundo**: le gana a todos los baselines triviales, pero no al
modelo barato que aprende la forma de la semana. Es un resultado sano — el
sistema elige el mejor, no el más impresionante.

### El resultado que casi publico mal

Con la referencia fija (ingenuo estacional) el titular daba
**«el modelo mejora 23%»**. Es cierto y es inútil: en la serie vieja el
ingenuo estacional rendía MASE 1,24 —o sea que era *malo ahí*— y ganarle no
significaba nada.

Por eso la decisión no se toma contra una referencia elegida de antemano sino
contra **el mejor de los modelos que no aprenden nada** (`ingenuo`,
`estacional_7`, `media`). Esa vara es la que sostiene el +13% / +17% de
arriba: es mejora contra el mejor baseline, no contra uno conveniente.

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
2. **La pantalla puede decir que no.** Si la cartera de un cliente no tiene
   señal, muestra el promedio con la línea **punteada y gris** y el texto
   «esto es un promedio, no una predicción». Una curva prolija sobre ruido
   termina en la meta del mes de alguien.

   Eso es una salvaguarda **del producto**, no un argumento de venta: la web y
   el video muestran lo que el cliente va a ver con datos con forma real —una
   proyección validada— y no el caso degenerado.
3. **TimesFM queda opcional** (`kobra/proyeccion_timesfm.py`), fuera del
   instalador:
   - pesa 925 MB + PyTorch (~200 MB) contra un instalador de 270 MB;
   - el programa instalado **no tiene internet**, así que no puede bajar pesos
     en el primer arranque;
   - en la demo queda segundo detrás de un modelo de diez líneas.

   Si el cliente lo quiere sobre su cartera real, se instala `timesfm[torch]`,
   se copian los pesos a una carpeta y se apunta `KOBRA_TIMESFM_DIR`. El
   backtest decide solo si se usa: **compite, no se impone**.

## Cómo lo ve un cliente con datos propios

El veredicto se recalcula sobre la cartera de cada empresa. Una cartera con
forma de semana —cobranza que cae los sábados, pico los días de sueldo— da
`sirve: true` y la proyección se dibuja en verde y continua, que es lo que
pasa ahora con la demo. Una cartera que de verdad sea ruido va a dar el
promedio. Es el mismo código, decidiendo distinto porque los datos son
distintos, y esa es toda la garantía que se puede dar de antemano.
