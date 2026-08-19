# MV Kobra AI — Plan de la suite con módulos escalables

> **Estado: planificado, no implementado.** Este documento es el traspaso de una
> sesión que mapeó el terreno pero no pudo portar el código, porque los repos de
> origen no estaban en su alcance. Quien retome: leé "Cómo retomar" primero.

## El objetivo

Kobra deja de ser un producto único y pasa a ser una **suite con precios
escalables según los módulos incluidos**. Sobre el producto de cobranzas actual
se suman tres módulos que hoy viven en repos separados del dueño:

| Módulo | Repo de origen | Qué agrega |
|---|---|---|
| Gobernanza de datos | `vieraschiavi/Mv-Data-Governance` | Catálogo, linaje, calidad, PII, RBAC |
| Medidas calculadas (DAX) | `vieraschiavi/Power-bi` | KPIs definidos por el cliente con fórmulas |
| AutoML | `vieraschiavi/MV-Machine-Learning` | El cliente entrena con su propio dataset |
| Consultas SQL | `vieraschiavi/Mv-Sql` | (alcance a definir con el repo a la vista) |

Más un **dashboard conversacional** nuevo: buscador en lenguaje natural,
tarjetas de KPI, secciones de Advertencias/Sugerencias/Acciones y tarjetas de
Análisis por área, con la paleta de Kobra.

## Cómo retomar

El bloqueo de la sesión anterior: **el acceso a GitHub estaba restringido a
`vieraschiavi/Kobra`**, y el alcance de repos se fija al crear la sesión — no se
puede ampliar desde adentro. Para portar el código de verdad hace falta una
sesión cuyo entorno incluya los cinco repos.

Sin eso, la única alternativa es reescribir los módulos desde cero, que
desperdicia código ya escrito y probado.

## Lo que ya se sabe de Mv-Data-Governance

Leído de su sitio público (`mv-data-governance.vercel.app`), no del código:

* **Stack: Python + Streamlit + PyInstaller.** Es el mismo stack que Kobra, así
  que el port debería ser directo y no una traducción entre tecnologías.
* Nueve pestañas modulares: Overview (KPIs), Calidad, Linaje (grafo
  interactivo), Catálogo, Glosario, Políticas, MDM/deduplicación, PII, Export BI.
* Calidad medida sobre las seis dimensiones DAMA: completitud, unicidad,
  validez, consistencia, oportunidad y exactitud, con motor de reglas y umbrales.
* Linaje "de la fuente al dashboard", navegable en las dos direcciones.
* Ya es trilingüe (ES/EN/PT) — igual que Kobra, lo que simplifica el i18n.
* Exporta a Power BI, Tableau, Looker, Qlik vía CSV/Excel/JSON/Parquet/REST.
* Diseñado para correr **on-premise**, sin nube, por requisitos de banca y salud.

Las URLs de los otros tres proyectos no se pudieron confirmar
(`mv-machine-learning.vercel.app` y `mv-sql.vercel.app` dan 404, y
`power-bi.vercel.app` es de otra empresa).

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

### Fase 2 — Gobernanza de datos

Portar desde `Mv-Data-Governance`. Kobra ya tiene piezas para engancharse:

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

### Fase 3 — Motor de medidas calculadas (tipo DAX)

El cliente define sus propios KPIs con fórmulas sobre las columnas existentes.

**Requisito de seguridad, no negociable:** las fórmulas se evalúan con un parser
propio de lista blanca, nunca con `eval()` ni `exec()`. Una fórmula la escribe
un usuario, y en la edición instalada corre en la máquina del cliente con sus
permisos.

### Fase 4 — Dashboard conversacional

Página nueva con el diseño de Kobra. Todo lo necesario ya está mapeado:

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

### Fase 5 — AutoML

Portar desde `MV-Machine-Learning`. El cliente sube su dataset y Kobra prueba
varios algoritmos e hiperparámetros.

**Requisito de honestidad, heredado de cómo se entrena ProbPago** (`kobra/train.py`):
la métrica que se le reporta al cliente sale de un holdout que no se usó para
elegir nada, y las series temporales se parten por tiempo, nunca al azar. Un
AutoML que elige el modelo y reporta el error del mismo tramo donde eligió está
mintiendo, y con un comprador empresarial eso se descubre.

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
