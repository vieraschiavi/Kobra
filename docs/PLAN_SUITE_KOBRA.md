# MV Kobra AI — Plan de la suite con módulos escalables

> **Estado: implementado.** Las cinco fases están hechas, con tests. Lo que
> queda abierto es qué más traer de los repos de origen, y la decisión de
> producto sobre fusionar o no `Plania` y `Project-management-mv`.

## El objetivo

Kobra deja de ser un producto único y pasa a ser una **suite con precios
escalables según los módulos incluidos**. Sobre el producto de cobranzas se
suman tres módulos vendibles por separado:

| Módulo | Origen | Estado |
|---|---|---|
| Gobernanza de datos | construido acá + `Mv-Data-Governance` | ✅ con enforcement DDL y glosario portados |
| Medidas calculadas (DAX) | construido acá | ✅ — el repo `Power-bi` nunca llegó |
| AutoML | construido acá | ✅ — el repo `MV-Machine-Learning` nunca llegó |
| Consultas SQL | ya existía en Kobra | ✅ mejorado con 3 arreglos de `Mv-Sql` |

Más un **dashboard conversacional** nuevo: buscador en lenguaje natural,
tarjetas de KPI, secciones de Advertencias/Sugerencias/Acciones y tarjetas de
Análisis por área, con la paleta de Kobra.

## Cómo llegaron los repos

El acceso a GitHub de la sesión estaba restringido a `vieraschiavi/Kobra`, y el
alcance se fija al crearla — no se puede ampliar desde adentro, ni con `git
clone` ni leyendo github.com por web, porque el límite es "esta sesión solo
toca Kobra" y no "esta sesión solo usa la API de GitHub".

Se destrabó **subiendo los repos como archivos ZIP**, que son archivos locales
y no pasan por esa restricción. Es la vía si vuelve a pasar.

Lo que llegó: `Mv-Data-Governance`, `Mv-Sql` (dos versiones), `Plania` y
`Project-management-mv`. **No** llegaron `MV-Machine-Learning` ni `Power-bi`,
así que el AutoML y las medidas siguen siendo los construidos acá, sin comparar
contra el original.

### Lo que aportaron

Menos de lo esperado en código nuevo y **más de lo esperado en bugs**: los dos
motores que se superponían ya existían en Kobra, y compararlos contra la
versión madura de cada repo destapó fallas que nadie había visto.

* De `Mv-Data-Governance` se portaron `enforcement.py` (DDL de GRANT/REVOKE,
  enmascarado y seguridad por fila) y `glossary.py` (adaptado a términos de
  cobranzas). Lo demás de ese repo —MDM, sync con Purview/Collibra, perfilado,
  etiquetas MIP, export a BI— **no está** en Kobra y sigue siendo terreno
  disponible.
* De `Mv-Sql` no hubo motor que portar: `kobra/consulta_bd.py` ya tenía la
  misma arquitectura. Lo que se trajo fueron tres arreglos y el intervalo de
  confianza (ver Fase 3).

## Qué queda sin traer de Mv-Data-Governance

Ese repo tiene 50 módulos en `mvdg/` y sigue siendo terreno disponible. Lo que
**no** está en Kobra, en orden de valor aparente para un comprador empresarial:

| Módulo de `mvdg/` | Qué haría en Kobra |
|---|---|
| `mdm.py` | Deduplicar deudores y armar el registro maestro |
| `purview_*.py`, `collibra_*.py` | Sincronizar con el catálogo corporativo que la empresa ya tiene |
| `profiler.py` | Perfilar una cartera nueva y sugerir reglas de calidad solo |
| `policies.py`, `cobit_iso.py`, `dmbok.py` | Políticas verificadas contra el catálogo, marcos COBIT/ISO |
| `mip_labels.py` | Etiquetas de Microsoft Information Protection |
| `exporters.py`, `powerbi_meta.py`, `tableau_meta.py` | Export del catálogo a las herramientas de BI |
| `remediation.py` | Qué hacer con cada falla de calidad, no solo reportarla |
| `contracts.py` | Contratos de datos entre áreas |
| `mcp_server.py` | Exponer el catálogo a un asistente por MCP |

Nota de arquitectura útil: **solo 2 de sus 51 módulos importan Streamlit**. El
núcleo está desacoplado de la UI, así que traer cualquiera de estos es copiar
el módulo y escribirle la pantalla, no desenredarlo de su interfaz.

## El plan, en cinco fases

El orden importa: cada fase se apoya en la anterior.

### Fase 1 — Catálogo de planes con módulos activables ✅ HECHA

Es el cimiento de "precios escalables", y **no depende de los repos de origen**:
se hizo entera antes de que llegue el código de los módulos.

Qué quedó implementado:

* `backend_venta/licencias.py` — la tupla `MODULOS` declara los tres módulos en
  un solo lugar, y `_NUCLEO` separa lo que ya hacía Kobra de lo que se vende
  aparte. La escalera quedó: Básico nada · Pro `gobernanza` · Starter
  `gobernanza`+`dax` · Enterprise los tres.
* `api/_license.js` — el espejo en Node, sincronizado (lo verifica
  `tests/test_licencia_puente.py`, que ejecuta el firmador de Node y valida con
  PyJWT).
* `landing/index.html` — cada tarjeta muestra qué módulos incluye, con la línea
  destacada por peso y símbolo (no solo por color). Traducido a pt y en, y las
  copias de idioma regeneradas.
* `tests/test_modulos_suite.py` — 9 tests: la escalera no se puede invertir, los
  planes de entrada no traen módulos, Enterprise los trae todos, un módulo no
  pagado corta con un mensaje que dice dónde mejorar, uno pagado deja pasar, y
  se puede vender un módulo suelto sin cambiar de plan.

**Pendiente al portar los módulos:** las tarjetas dicen "próximamente" a
propósito, porque hoy la licencia habilita un módulo que todavía no existe.
Sacar esa palabra cuando cada módulo esté realmente en el producto — anunciar
antes sería venderle a un cliente algo que no va a encontrar al instalar.

La distribución de módulos por plan es una **propuesta**: es decisión comercial
del dueño y se cambia editando las listas de `PLANES`.

La infraestructura ya existe y no hay que inventarla:

* `backend_venta/licencias.py::PLANES` define qué incluye cada plan, y cada
  licencia viaja firmada con su lista de `features`.
* `kobra/plan.py::exigir(feature)` es el **único** lugar donde se decide si una
  capacidad está habilitada. Ya lo usan `voz`, `whatsapp`, `copiloto`, `erp`,
  `excedente`, `white_label` y `sso`.

Los módulos nuevos entran como tres features más: `gobernanza`, `dax`, `automl`.
Cada endpoint nuevo abre con `kplan.exigir("gobernanza", "la gobernanza de
datos")` y listo — el gateo, el mensaje al cliente y el link de upgrade ya están
resueltos.

Falta decidir (**decisión comercial del dueño, no técnica**): qué plan incluye
qué módulo y a qué precio.

Superficies a tocar, todas mapeadas:

| Archivo | Qué hay que hacer |
|---|---|
| `backend_venta/licencias.py` | Agregar las features a los planes que las incluyan |
| `api/_license.js` | Espejo en Node del catálogo — tiene que coincidir |
| `api/checkout.js` | Precio de cobro por plan |
| `landing/index.html` | Tarjetas de precios (`#precios`) + `USD_BASE` |
| `webapp/frontend/src/i18n/{es,pt-BR}.json` | Textos de los módulos |
| `tests/test_licencia_puente.py` | Ya cruza Python↔Node: extenderlo |

### Fase 2 — Gobernanza de datos ✅ HECHA

Construida dentro de Kobra (`kobra/gobernanza.py`), **no portada** — los repos
de origen nunca estuvieron accesibles. Si más adelante se abre
`Mv-Data-Governance`, conviene comparar: lo de allá tiene glosario, MDM y
export a Power BI/Tableau, que acá no están.

Qué quedó implementado:

* **Clasificación** en cuatro niveles (`publico` / `interno` / `personal` /
  `sensible`). El catálogo de la cartera se declara a mano, porque adivinar por
  nombre falla justo donde importa: `score_buro` no dice "personal" en ninguna
  parte y es dato crediticio. Hay heurística de respaldo para las carteras que
  sube un cliente, y ante la duda clasifica de más, nunca de menos.
* **Enmascarado por rol** que conserva el valor operativo: un identificador se
  vuelve seudónimo estable (HMAC con sal propia de la instalación, así que dos
  empresas no pueden cruzar sus carteras), y un dato patrimonial se vuelve
  tramo. El gestor sigue viendo deuda, mora y canal — puede cobrar; lo que no
  puede es llevarse una lista nominal.
* **Reglas de calidad** sobre las seis dimensiones DAMA, con un informe que
  nunca lanza: un dato malo tiene que poder mostrarse, no tumbar el proceso.
* **Linaje** escrito en el log append-only con cadena de hashes que ya existía
  (`kobra/auditoria.py`), con recorrido aguas arriba y aguas abajo, y corte de
  ciclos.

Integración: cuatro endpoints (`/api/gobernanza/{resumen,catalogo,calidad,linaje}`)
gateados con `plan.exigir`, más el enmascarado aplicado a `/api/cartera` **y al
export CSV** — si la pantalla enmascara y el CSV sale en claro, la protección
es decorativa. La pantalla nueva es `webapp/frontend/src/pages/Gobernanza.jsx`,
en el diseño de Kobra y traducida a los dos idiomas.

Decisión de diseño importante: **sin el módulo, nada cambia.** Quien no compró
gobernanza sigue viendo su cartera como siempre. Un módulo que al no comprarse
empeora el producto es un rehén, no un upsell.

45 tests (`tests/test_gobernanza.py` + `tests/test_gobernanza_api.py`).

Kobra ya tenía piezas que sirvieron de base:

* `kobra/auditoria.py` — log append-only con cadena de hashes SHA-256, ya
  registra logins, cambios de config, gestiones y exportes. Es la base del
  linaje; no hay que empezar de cero.
* `kobra/cumplimiento.py` — motor de horarios de contacto, feriados y pedidos de
  no-contactar. Es el precedente de "reglas que se aplican solas".
* `kobra/autenticacion.py` — roles (admin / no admin) sobre los que montar RBAC.

Lo pedido explícitamente por el dueño: linaje y auditoría, clasificación y
enmascarado de PII, RBAC sobre datos y reportes, y reglas de calidad al ingerir.

> Cuidado con el enmascarado de PII: `CLAUDE.md` exige que los datos sean
> siempre sintéticos. Las reglas de PII se prueban contra datos generados, nunca
> contra datos reales de clientes.

### Fase 3 — Motor de medidas calculadas (tipo DAX) ✅ HECHA

`kobra/medidas.py`. El cliente define sus KPIs con fórmulas sobre las columnas
de su cartera:

    promedio(monto_deuda)
    suma(monto_deuda) / contar()
    contar_si(dias_mora > 90) / contar() * 100

**El parser es lista blanca sobre `ast`, nunca `eval`.** No es una preferencia
de estilo: se comprobó ejecutando los mismos ataques contra las dos
implementaciones. Con `eval`, las cuatro pruebas pasaron — corrió un comando
del sistema, leyó `/etc/passwd`, llegó a `__subclasses__()` y escribió un
archivo en disco. El parser real las rechazó todas. `eval` no se arregla con
una lista negra: desde cualquier expresión se llega a `__builtins__`.

Se recorre el árbol y se rechaza todo nodo que no esté explícitamente
permitido; `generic_visit` es el rechazo, así que un tipo de nodo que nadie
previó (walrus, f-string, comprensión) falla cerrado. 18 tests cubren ese
vector — si empiezan a fallar, alguien aflojó la lista blanca.

Detalles que importan en uso real:

* Dividir por cero da "sin datos", no `inf` ni 0 — es el caso más común de una
  medida recién escrita, y `0` sería una mentira ("la tasa es cero").
* Una medida rota no deja el tablero en blanco: se muestra con su error y las
  demás siguen calculando.
* Guardar valida el lote entero o no guarda nada: guardar la mitad deja al
  cliente sin saber cuáles quedaron.
* Las medidas se calculan sobre los datos **ya enmascarados**. Una medida es
  una vía de lectura como cualquier otra: sin esto, un gestor podría averiguar
  el dato exacto de un deudor con `maximo(...)` y el filtro bien puesto.
* Solo un admin cambia las definiciones — es el KPI que después mira todo el
  equipo.

Pantalla: `webapp/frontend/src/pages/Medidas.jsx`, con botón "Probar" por
fórmula (el error tiene que aparecerle a quien la escribe, no a quien abre el
tablero) y referencia desplegable de funciones y columnas.

49 tests (`tests/test_medidas.py` + `tests/test_medidas_api.py`).

### Fase 4 — Dashboard conversacional ✅ HECHA

`kobra/analista.py` + `webapp/frontend/src/pages/Tablero.jsx`. Buscador en
lenguaje natural, KPIs, y las tres listas de Advertencias / Sugerencias /
Acciones.

**La regla que lo hace usable: pandas calcula, el modelo solo redacta.** Si el
modelo estimara las cifras, cada respuesta sería plausible y algunas falsas, y
no habría forma de saber cuál es cuál sin rehacer la cuenta a mano — o sea, sin
usar el tablero. Concretamente: `hechos()` calcula un resumen exacto, ese
resumen y nada más va al modelo, y el system prompt le prohíbe inventar,
estimar y proyectar. La respuesta incluye los hechos usados, desplegables en la
pantalla, para que quien lee pueda verificar sin creernos.

Decisiones que importan:

* **No está detrás de ningún módulo pago.** Es la pantalla de inicio: cobrarle
  al cliente por ver sus propios indicadores sería sacarle producto.
* **Abre sin proveedor de IA configurado**, que es como llega toda instalación
  nueva. KPIs, advertencias y acciones son determinísticos; lo único que se
  pierde sin IA es la pregunta libre.
* Advertencias y acciones salen de **reglas explícitas**, no del modelo. Una
  advertencia que aparece y desaparece según lo que alucinó el modelo esa vez
  no es una advertencia.
* La pregunta libre corre sobre los datos **ya enmascarados**: sin eso, sería
  la puerta para sacar por texto lo que la tabla protege.
* Las preguntas sugeridas se arman según las columnas que la cartera realmente
  tiene.

Un bug que encontraron los tests: la alerta de concentración usaba un umbral
fijo del 35%, y con dos segmentos marcaba como concentrado un reparto 50/50 —
que es *el más equilibrado posible*. Una alerta que aparece siempre se deja de
mirar. Ahora se compara contra el reparto parejo (1/n) y se piden al menos tres
categorías.

25 tests (`tests/test_analista.py` + `tests/test_tablero_api.py`).

Referencia del frontend que se usó (sirve para las próximas pantallas):

* **Router:** `HashRouter` en `src/main.jsx`; rutas en `src/App.jsx` (~línea 259)
  y el array `NAV` (~línea 31) que arma el sidebar.
* **Diseño:** todo en `src/theme.css`, un solo archivo, clases globales — no hay
  Tailwind ni CSS modules. Tokens en `:root`: `--navy-950 #0a1020` (fondo),
  `--navy-900 #0e1628` (cards), `--green #7cc242` (lima, botones),
  `--green-deep #00c896` (valores de KPI), `--ink #eaf1fb`, `--muted #93a5c0`.
* **KPIs:** el componente `Kpi({label, value, delta, bad})` vive local en
  `pages/Dashboard.jsx` (~línea 32) y **no está exportado** — copiarlo o
  extraerlo a `src/components/`.
* **Gráficos:** `recharts`. Ojo: no lee CSS vars, así que los colores están
  duplicados como literales en cada página (`Dashboard.jsx:22`).
* **Backend:** un solo helper `api(ruta, {metodo, cuerpo})` en `src/api.js`;
  mete el `Authorization: Bearer` solo y en 401 manda a `#/login`.
* **i18n:** `t("clave")` desde `src/i18n/index.js`; hay que agregar el bloque
  nuevo en **es.json y pt-BR.json**, más la clave de nav bajo `app.nav.*`.

El buscador en lenguaje natural se apoya en `kobra/llm.py` y
`kobra/consulta_bd.py`, que ya existen.

### Consultas SQL en lenguaje natural — mejorado con lo de Mv-Sql

No hubo port: `kobra/consulta_bd.py` ya tenía la misma arquitectura que el
motor de `Mv-Sql` (RAG sobre el esquema, generación con el modelo, validación
contra el catálogo). Comparar las dos versiones destapó **tres bugs en la de
Kobra**, los tres verificados ejecutándolos antes de tocar nada:

1. **Las consultas con CTE se rechazaban.** `WITH morosos AS (...) SELECT ...
   FROM morosos` daba "tabla no existe en el catálogo", porque `morosos` lo
   define la propia consulta. Se rechazaba justo el SQL que el prompt del
   sistema pide generar.
2. **Cualquier consulta comentada se rechazaba**, porque `--` estaba en la
   lista de prohibidas. Un modelo comenta casi siempre. Lo que se quería
   frenar era encadenar una segunda sentencia, y eso ahora lo corta un chequeo
   de `;` — que además cubre el caso que `--` no cubría.
3. **`sp_executesql` pasaba sin bloquearse.** Es ejecución de SQL arbitrario
   en SQL Server; `exec ` tapaba el caso habitual de rebote, pero no ese.

Los dos primeros son la falla que más se subestima en este tipo de función: no
aparecen como agujero de seguridad, pero hacen que el cliente pruebe, no le
ande, y no vuelva.

Se trajo también el **intervalo de confianza** (`calcular_confianza`), que
combina tres señales independientes — autoevaluación del modelo, similitud del
esquema recuperado y validación estructural — y ensancha el margen cuando falta
información. Reportar solo lo primero sería publicar la opinión del modelo
sobre su propia respuesta, y un modelo equivocado suele estar seguro.

`validar_sql` pasó a devolver `(valido, problemas, advertencias)`. Un problema
invalida; una advertencia se muestra y deja correr — si una columna no
reconocida invalidara, ningún alias de CTE pasaría, y son correctos.

25 tests en `tests/test_consulta_bd_validador.py`.


### Fase 5 — AutoML ✅ HECHA

`kobra/automl.py`. El cliente sube su tabla, elige qué predecir, y Kobra prueba
cuatro familias de algoritmos y se queda con el mejor.

**Lo difícil no es probar modelos — es de dónde sale el número que se reporta.**
El error habitual (partir en dos, elegir el mejor en prueba, reportar esa misma
métrica) da siempre un número optimista: al tomar el máximo entre varias
mediciones sobre el mismo conjunto, ese máximo incorpora la suerte del ganador
en ese corte. El cliente descubre la diferencia en producción.

Acá se parte en **tres**: entrenamiento (60%) ajusta, selección (20%) decide
cuál gana, holdout (20%) solo mide y no se usa para nada más. El número
reportado sale del holdout, y **se muestra además la brecha** entre selección y
holdout — cuánto se hubiera exagerado con el método habitual.

Otras decisiones que importan:

* Con columna de fecha, los cortes son **temporales**. Un split aleatorio sobre
  datos con orden temporal es la fuga más común que existe.
* El escalado va dentro del Pipeline, no antes: si no, la media del conjunto de
  prueba se filtra al entrenamiento.
* Un AUC ≥ 0.98 dispara un aviso en vez de celebrarse: casi siempre es una
  consecuencia del resultado colada como causa.
* Se explica qué columnas pesaron. En cobranzas hay que poder justificar por
  qué se prioriza a una persona.
* El archivo subido **no se guarda**: se lee, se entrena y se descarta.

Un bug que encontraron los tests y conviene no repetir: la heurística que
descarta identificadores usaba "muchos valores distintos", y con eso tiraba
`monto_deuda` —un decimal continuo, y la columna más predictiva de una
cartera— en silencio. Ahora el criterio depende del tipo: los decimales nunca
se descartan, los enteros solo si son únicos en todas las filas, y el texto si
casi no se repite.

Pantalla: `webapp/frontend/src/pages/AutoML.jsx`, con el flujo en dos pasos y
la brecha selección→holdout mostrada con nombre propio.

30 tests (`tests/test_automl.py` + `tests/test_automl_api.py`).

> Nota: se construyó dentro de Kobra, **no se portó** desde
> `MV-Machine-Learning` — ese repo nunca estuvo accesible. Si se abre, conviene
> comparar antes de dar el módulo por cerrado.

## Lo que esta sesión sí dejó hecho

**Arreglo de facturación** (commit "Cobrar el precio que la landing muestra"):
la landing tenía tres fuentes de precios contradictorias. Un visitante de
AR/MX/CL/CO/PE/BR elegía su país y veía el plan Pro convertido desde US$149,
mientras el checkout le cobraba US$349. Se corrigió `USD_BASE`, se regeneraron
las copias en inglés y portugués (que arrastraban el mismo error, incluida la de
Brasil) y se ató todo con `tests/test_precios_coherentes.py`.

Importa para este plan porque **la Fase 1 no se puede construir sobre precios
que se contradicen**.

## Recordatorios del repo

* Antes de pushear: `python3 verificar.py` — corre los cuatro gates de CI.
  Solo `pytest` no alcanza: el hook de pre-push ya frenó un push por `ruff`.
* Datos siempre sintéticos, seeds fijos (`--seed 42`), nunca PII real.
* Las cifras de impacto son ilustrativas y se presentan como tales.
