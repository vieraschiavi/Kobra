# i18n Keys Map

Reference for the Fase 2 wiring step: for each dictionary key in `es.json` /
`pt-BR.json`, this lists the exact file(s) and line number(s) the original
Spanish string was extracted from, so it can be found and replaced with a
lookup call (e.g. `t("dashboard.kpi.deudores")`).

Line numbers refer to the current state of each file at the time of
extraction (2026-07-10). Template placeholders in the dictionary values use
`{{name}}` notation for dynamic values that were embedded inline in the
original JSX (numbers, computed percentages, etc.) — the wiring step will
need to pass these as interpolation params.

## common.*
- `common.marca` — App.jsx:76 (`<b>MV KOBRA <span>AI</span></b>`); also Login.jsx:29 (`<h1>MV KOBRA <span>AI</span></h1>`, tracked separately as `login.marca`)
- `common.cargando` — Dashboard.jsx:39 (`Cargando…`); also Originacion.jsx:102 (`Cargando…`)
- `common.propension.alta` — Cartera.jsx:6 (`PROPENSIONES` array, "Alta"); rendered via `<option>` at Cartera.jsx:99
- `common.propension.media` — Cartera.jsx:6 ("Media")
- `common.propension.baja` — Cartera.jsx:6 ("Baja")

## app.* (App.jsx)
- `app.nav.vision_general` — App.jsx:15
- `app.nav.originacion` — App.jsx:16
- `app.nav.cartera` — App.jsx:17
- `app.nav.agenda` — App.jsx:18
- `app.nav.gestores` — App.jsx:19
- `app.nav.asistente` — App.jsx:20
- `app.nav.configuracion` — App.jsx:21
- `app.sidebar.rol_admin` — App.jsx:87 (`"🛡️ Administrador"`)
- `app.sidebar.rol_gestor` — App.jsx:87 (`"👤 Gestor"`)
- `app.sidebar.cerrar_sesion` — App.jsx:90

## login.* (pages/Login.jsx)
- `login.marca` — Login.jsx:29
- `login.subtitulo` — Login.jsx:30
- `login.input.placeholder_password` — Login.jsx:32
- `login.boton.entrando` — Login.jsx:35
- `login.boton.entrar` — Login.jsx:35

## dashboard.* (pages/Dashboard.jsx)
- `dashboard.titulo` — Dashboard.jsx:43
- `dashboard.subtitulo` — Dashboard.jsx:44-45
- `dashboard.kpi.deudores` — Dashboard.jsx:48
- `dashboard.kpi.cartera_label` — Dashboard.jsx:49 (template literal `` `Cartera (${getPais().moneda})` ``)
- `dashboard.kpi.recupero_esperado` — Dashboard.jsx:50
- `dashboard.kpi.recupero_esperado_delta` — Dashboard.jsx:51 (`fmtPct(...) + " de la cartera"`)
- `dashboard.kpi.probpago_promedio` — Dashboard.jsx:52
- `dashboard.kpi.mora_promedio` — Dashboard.jsx:53 (label)
- `dashboard.kpi.mora_promedio_valor` — Dashboard.jsx:53 (`Math.round(...) + " días"`)
- `dashboard.kpi.cartera_riesgo` — Dashboard.jsx:54
- `dashboard.chart.cartera_vs_recupero` — Dashboard.jsx:60
- `dashboard.chart.serie_cartera` — Dashboard.jsx:69 (`<Bar ... name="Cartera">`)
- `dashboard.chart.serie_recupero_esperado` — Dashboard.jsx:70 and Dashboard.jsx:101-102 (same label, two `<Bar name="Recupero esperado">`)
- `dashboard.chart.distribucion_propension` — Dashboard.jsx:76
- `dashboard.chart.recupero_por_segmento` — Dashboard.jsx:93
- `dashboard.chart.top_departamentos` — Dashboard.jsx:108

## originacion.* (pages/Originacion.jsx)
- `originacion.titulo` — Originacion.jsx:83
- `originacion.subtitulo` — Originacion.jsx:84-86
- `originacion.modelo.prefijo` — Originacion.jsx:90
- `originacion.modelo.auc_label` — Originacion.jsx:91
- `originacion.modelo.ks_label` — Originacion.jsx:92
- `originacion.modelo.mejora_label` — Originacion.jsx:93
- `originacion.modelo.validacion_label` — Originacion.jsx:97
- `originacion.tabla.col_solicitud` — Originacion.jsx:107
- `originacion.tabla.col_fecha` — Originacion.jsx:107
- `originacion.tabla.col_tipo` — Originacion.jsx:107
- `originacion.tabla.col_monto` — Originacion.jsx:107
- `originacion.tabla.col_plazo` — Originacion.jsx:107
- `originacion.tabla.col_ingreso` — Originacion.jsx:108
- `originacion.tabla.col_score` — Originacion.jsx:108
- `originacion.tabla.col_decision` — Originacion.jsx:108
- `originacion.tabla.col_confianza` — Originacion.jsx:108
- `originacion.tabla.plazo_sufijo` — Originacion.jsx:117 (`{s.plazo_meses} m`)
- `originacion.decision.aprobar` — Originacion.jsx:5 (`PILL_DECISION` map key, rendered at 120)
- `originacion.decision.derivar` — Originacion.jsx:6
- `originacion.decision.rechazar` — Originacion.jsx:7
- `originacion.drawer.probabilidad_mora` — Originacion.jsx:39
- `originacion.drawer.solicita` — Originacion.jsx:41
- `originacion.drawer.meses_sufijo` — Originacion.jsx:42, 46
- `originacion.drawer.sugerido` — Originacion.jsx:43
- `originacion.drawer.ingreso_declarado` — Originacion.jsx:49
- `originacion.drawer.perfil` — Originacion.jsx:51
- `originacion.drawer.historial_interno` — Originacion.jsx:53
- `originacion.drawer.creditos_previos_sufijo` — Originacion.jsx:54
- `originacion.drawer.atrasos_sufijo` — Originacion.jsx:54
- `originacion.drawer.confianza_modelo` — Originacion.jsx:55
- `originacion.drawer.datos_presentes_sufijo` — Originacion.jsx:56
- `originacion.drawer.por_que_titulo` — Originacion.jsx:59
- `originacion.drawer.pp_sufijo` — Originacion.jsx:61 (`efecto_pp} pp`)
- `originacion.drawer.decision_final` — Originacion.jsx:63

## cartera.* (pages/Cartera.jsx)
- `cartera.titulo` — Cartera.jsx:82
- `cartera.subtitulo` — Cartera.jsx:83-84
- `cartera.toolbar.buscar_placeholder` — Cartera.jsx:87
- `cartera.toolbar.segmento_todos` — Cartera.jsx:90
- `cartera.toolbar.tramo_todos` — Cartera.jsx:94
- `cartera.toolbar.propension_todas` — Cartera.jsx:98
- `cartera.toolbar.exportar_csv` — Cartera.jsx:101
- `cartera.filtro.segmento_corporativo` — Cartera.jsx:5 (`SEGMENTOS` array)
- `cartera.filtro.segmento_pyme` — Cartera.jsx:5
- `cartera.filtro.segmento_retail` — Cartera.jsx:5
- `cartera.tabla.col_numero` — Cartera.jsx:110
- `cartera.tabla.col_id` — Cartera.jsx:110
- `cartera.tabla.col_segmento` — Cartera.jsx:110
- `cartera.tabla.col_producto` — Cartera.jsx:110
- `cartera.tabla.col_depto` — Cartera.jsx:110
- `cartera.tabla.col_tramo` — Cartera.jsx:111
- `cartera.tabla.col_monto` — Cartera.jsx:111
- `cartera.tabla.col_probpago` — Cartera.jsx:111
- `cartera.tabla.col_prop` — Cartera.jsx:111
- `cartera.tabla.col_estrategia` — Cartera.jsx:112
- `cartera.tabla.col_desc` — Cartera.jsx:112
- `cartera.tabla.col_canal` — Cartera.jsx:112
- `cartera.pager.pagina_de` — Cartera.jsx:138
- `cartera.pager.deudores_sufijo` — Cartera.jsx:139
- `cartera.drawer.propension_sufijo` — Cartera.jsx:24-25 (`{d.segmento_propension} propensión · ProbPago {fmtPct(d.probpago)}`)
- `cartera.drawer.segmento` — Cartera.jsx:27
- `cartera.drawer.departamento` — Cartera.jsx:28
- `cartera.drawer.mora` — Cartera.jsx:29
- `cartera.drawer.mora_valor` — Cartera.jsx:29 (`{d.dias_mora} días (tramo {d.tramo_mora})`)
- `cartera.drawer.deuda` — Cartera.jsx:30
- `cartera.drawer.recupero_esperado` — Cartera.jsx:31
- `cartera.drawer.estrategia` — Cartera.jsx:32
- `cartera.drawer.descuento_sugerido` — Cartera.jsx:33
- `cartera.drawer.canal_recomendado` — Cartera.jsx:34
- `cartera.drawer.por_que_probpago` — Cartera.jsx:35
- `cartera.drawer.guion_sugerido` — Cartera.jsx:38

## agenda.* (pages/Agenda.jsx)
- `agenda.titulo` — Agenda.jsx:13
- `agenda.subtitulo` — Agenda.jsx:14-16 (contains inline `<b>...</b>`)
- `agenda.vacio_sin_pendientes` — Agenda.jsx:19
- `agenda.tabla.col_id_deudor` — Agenda.jsx:25
- `agenda.tabla.col_resultado` — Agenda.jsx:25
- `agenda.tabla.col_comprometido` — Agenda.jsx:25
- `agenda.tabla.col_dias_vencida` — Agenda.jsx:26
- `agenda.tabla.col_monto_acordado` — Agenda.jsx:26
- `agenda.tabla.col_canal` — Agenda.jsx:26
- `agenda.tabla.col_gestor` — Agenda.jsx:26

## gestores.* (pages/Gestores.jsx)
- `gestores.titulo` — Gestores.jsx:13
- `gestores.subtitulo` — Gestores.jsx:14-15
- `gestores.vacio_sin_gestiones` — Gestores.jsx:18

Note: the ranking table's column headers (Gestores.jsx:24, `Object.keys(datos.ranking[0]).map((k) => k.replace(/_/g, " "))`)
are derived at runtime from API field names, not hardcoded strings — no
dictionary key was created for them. The wiring step (or the backend) will
need a separate field-name → label map if these should be localized too.

## asistente.* (pages/Asistente.jsx)
- `asistente.titulo` — Asistente.jsx:27
- `asistente.subtitulo` — Asistente.jsx:28-30 (contains inline `<code>ANTHROPIC_API_KEY</code>`)
- `asistente.placeholder_input` — Asistente.jsx:48
- `asistente.boton_preguntar` — Asistente.jsx:50
- `asistente.chat.ejemplo` — Asistente.jsx:34-35
- `asistente.chat.fuentes_prefijo` — Asistente.jsx:41
- `asistente.chat.buscando` — Asistente.jsx:45
- `asistente.error_no_pude_responder` — Asistente.jsx:19 (`"No pude responder: " + err.message`)

## configuracion.* (pages/Configuracion.jsx)
- `configuracion.titulo` — Configuracion.jsx:31
- `configuracion.subtitulo` — Configuracion.jsx:32-34
- `configuracion.nota.ingresar_clave` — Configuracion.jsx:18
- `configuracion.nota.guardadas_prefijo` — Configuracion.jsx:21 (`"✅ Guardadas: " + r.guardadas.join(", ")`)
- `configuracion.nota.error_prefijo` — Configuracion.jsx:25 (`"Error: " + err.message`)
- `configuracion.tabla.col_clave` — Configuracion.jsx:40
- `configuracion.tabla.col_estado` — Configuracion.jsx:40
- `configuracion.tabla.col_nuevo_valor` — Configuracion.jsx:40
- `configuracion.estado.configurada` — Configuracion.jsx:45
- `configuracion.estado.sin_configurar` — Configuracion.jsx:45
- `configuracion.boton_guardar` — Configuracion.jsx:58

## tour.* (components/Tour.jsx)
- `tour.paso1.titulo` — Tour.jsx:4
- `tour.paso1.texto` — Tour.jsx:5
- `tour.paso2.titulo` — Tour.jsx:6
- `tour.paso2.texto` — Tour.jsx:7
- `tour.paso3.titulo` — Tour.jsx:8
- `tour.paso3.texto` — Tour.jsx:9
- `tour.paso4.titulo` — Tour.jsx:10
- `tour.paso4.texto` — Tour.jsx:11
- `tour.boton_saltar` — Tour.jsx:31
- `tour.boton_siguiente` — Tour.jsx:33
- `tour.boton_empezar` — Tour.jsx:34

## api.* (api.js — not in the original file list, but user-facing)
- `api.error.sesion_vencida` — api.js:26 (`throw new Error("Sesión vencida — iniciá sesión de nuevo.")`)

---

### Known rough edges for the wiring step
1. **Duplicate/shared strings**: `common.cargando`, `common.marca`
   (also `login.marca`), `dashboard.chart.serie_recupero_esperado`, and the
   propension labels (`Alta`/`Media`/`Baja`, also `cartera.drawer.*` pill
   text) appear in more than one place. They're single keys reused across
   locations rather than duplicated per-call-site.
2. **Hardcoded locale bug**: Cartera.jsx:139 formats the total debtor count
   with `.toLocaleString("es-UY")` — hardcoded, unlike every other number in
   the app which reads `getPais().locale`. This is unrelated to text
   translation but the wiring step should probably fix it while touching
   that line, or pt-BR users in a UY tenant will still see Spanish-style
   number grouping.
3. **Dynamic table headers**: Gestores.jsx ranking table headers come from
   raw API field names at runtime (see note above) — out of scope for a
   static string dictionary.
