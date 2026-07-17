---
name: automatizador-proyecto
description: >
  Automatizador universal de proyectos para Claude Code. Prepara CUALQUIER repo (Python, Node,
  Go, R, Rust, etc.) para trabajo autónomo aplicando las 12 features de Claude Code: CLAUDE.md,
  permisos, plan mode, checkpoints, skills, hooks, MCP, plugins, contexto/compact, slash commands
  y subagentes. ACTIVAR SIEMPRE que el usuario escriba "/automatizador-proyecto", diga "automatizá
  este proyecto", "armá el automatizador", "preparar el repo para Claude Code", "configurá Claude
  Code acá", "dejá el proyecto listo para trabajar solo", "generá el CLAUDE.md y los comandos", o
  pida convertir un proyecto en uno auto-operable por Claude. Es GENÉRICO (sirve en cualquier
  proyecto/lenguaje) y NO hardcodea datos de ninguna empresa. Responder siempre en español
  rioplatense salvo pedido explícito. NUNCA declarar el proyecto automatizado sin verificar que
  los archivos quedaron creados y que el hook/comando corre.
---

# Automatizador de Proyecto — dejá cualquier repo listo para que Claude trabaje solo

Este skill convierte un proyecto cualquiera en uno **auto-operable por Claude Code**, aplicando las
**12 features** del video "Claude Code's Top 12 Features". No es teoría: crea los archivos concretos
(`CLAUDE.md`, `.claude/settings.json`, hooks, slash commands, subagentes, `.mcp.json`) adaptados al
stack que detecte.

La idea de fondo: un proyecto "automatizado" es uno donde Claude, al abrir una sesión, ya sabe **qué
es el proyecto** (CLAUDE.md), **qué puede tocar sin preguntar** (permisos), **cómo arrancarlo y
testearlo** (hooks + comandos), **cómo dividir trabajo pesado** (subagentes) y **cómo publicar**
(comando ship). El usuario define el *qué*; el proyecto ya trae el *cómo*.

## Mapa: cada feature del video → qué crea este skill

| # | Feature (video) | Qué genera el skill |
|---|-----------------|---------------------|
| 1 | CLAUDE.md | `CLAUDE.md` con stack, comandos, estructura, convenciones y do/don't |
| 2 | Permissions | `.claude/settings.json` con allow/deny curado al stack |
| 3 | Plan Mode | comando `/plan` + convención "planificar antes de tocar" en CLAUDE.md |
| 4 | Checkpoints | comando `/ship` (commit) + política de checkpoints git en CLAUDE.md |
| 5 | Skills | deja el proyecto listo para invocar skills; documenta cuáles aplican |
| 6 | Hooks | `.claude/hooks/session-start.sh` (instala deps + verifica que corre) |
| 7 | MCP | `.mcp.json` template comentado (GitHub, Slack, etc.) |
| 8 | Plugins | estructura compatible; opción de empaquetar todo como plugin |
| 9-10 | Context / Compact | reglas de contexto/`/compact` en CLAUDE.md |
| 11 | Slash commands | `.claude/commands/`: `plan`, `ship`, `review`, `test` |
| 12 | Sub-agents | `.claude/agents/`: `explorer`, `parallel-worker`, `specialist` |

## Cómo se ejecuta (workflow del skill)

Seguí estas fases EN ORDEN. Trabajá sobre el directorio del proyecto actual (o el que indique el
usuario). Los templates base están en `assets/` dentro de este skill — copialos y adaptalos, no los
inventes de cero.

### FASE 0 — Diagnóstico (solo lectura)

1. Detectá el tipo de proyecto por sus manifiestos:
   - `package.json` → Node/JS/TS · `requirements.txt`/`pyproject.toml` → Python · `go.mod` → Go
   - `Cargo.toml` → Rust · `pom.xml`/`build.gradle` → Java · `*.Rproj`/`DESCRIPTION` → R · etc.
2. Extraé los comandos reales del proyecto: instalar deps, correr, testear, lint, build.
   (En Node leé `scripts` de `package.json`; en Python buscá `pytest`/`Makefile`; etc.)
3. Detectá el remote git, la rama por defecto y si ya existe `CLAUDE.md`/`.claude/`.
4. Mostrá un resumen corto de lo detectado antes de escribir nada.

### FASE 1 — CLAUDE.md (#1)

- Si NO existe: generalo desde el diagnóstico. Secciones mínimas: **Qué es**, **Stack**,
  **Comandos** (instalar/correr/test/lint/build), **Estructura**, **Convenciones**, **Do / Don't**,
  **Flujo de trabajo** (plan → cambios → test → ship), **Contexto/Compact** (cuándo usar `/compact`).
- Si YA existe: NO lo pises. Hacé backup (`CLAUDE.md.bak`) y proponé un merge de las secciones
  faltantes, mostrando el diff antes de aplicar.

### FASE 2 — Permisos (#2)

- Copiá `assets/settings.template.json` a `.claude/settings.json` y curá el `allow`/`deny` según el
  stack detectado (ej: permitir `npm test`, `pytest`, `git status`; denegar `rm -rf`, `git push
  --force`, secretos). Nunca permitas comandos destructivos ni exfiltración por defecto.

### FASE 3 — Hooks (#6)

- Copiá `assets/hooks/session-start.sh`, adaptá los comandos de instalación/verificación al stack, y
  registralo en `.claude/settings.json` como hook `SessionStart`. Dejalo idempotente y con `set -e`.

### FASE 4 — Slash commands (#11)

- Copiá `assets/commands/{plan,ship,review,test}.md` a `.claude/commands/`. Adaptá `test.md` y el
  comando de build al stack real. `ship.md` debe: checkpoint (commit), push a la rama, y abrir PR
  draft si no existe.

### FASE 5 — Subagentes (#12)

- Copiá `assets/agents/{explorer,parallel-worker,specialist}.md` a `.claude/agents/`. Ajustá el
  `specialist` al dominio del proyecto (ej: ML, cobranzas, frontend) si es evidente.

### FASE 6 — MCP (#7)

- Copiá `assets/mcp.template.json` como `.mcp.json` (o `.mcp.json.example` si preferís no activarlo).
  Dejá comentado qué servers convienen (GitHub siempre; Slack/Notion/Figma según el proyecto).
  NUNCA metas tokens reales: usá placeholders y referencia a variables de entorno.

### FASE 7 — Verificación (obligatoria, NO declarar éxito sin esto)

1. Listá todos los archivos creados/modificados (`git status` o `ls -R .claude`).
2. Corré el hook `session-start.sh` una vez y confirmá que termina sin error (o reportá qué falló).
3. Mostrá al usuario un resumen final: qué features quedaron activas (checklist de las 12) y cómo
   usarlas (`/plan`, `/ship`, `/review`, `/test`).
4. Si estás en un repo con rama de trabajo asignada, ofrecé commitear la automatización.

## Reglas duras

- **Genérico siempre**: nada de datos de una empresa puntual hardcodeado. Si el proyecto es de un
  dominio conocido, adaptá nombres pero mantené los templates reutilizables.
- **No destructivo**: nunca pises `CLAUDE.md`, `.claude/settings.json` ni configs existentes sin
  backup y sin mostrar el diff.
- **Permisos conservadores**: ante la duda, denegá. Es preferible una pregunta de permiso extra que
  un `rm -rf` autorizado.
- **Idempotente**: correr el skill dos veces no debe duplicar ni romper nada.
- **Verificá**: el proyecto NO está "automatizado" hasta que los archivos existen y el hook corre.

## Adaptación por stack (referencia rápida)

| Stack | install | test | lint | run |
|-------|---------|------|------|-----|
| Node/TS | `npm ci` | `npm test` | `npm run lint` | `npm run dev` |
| Python | `pip install -r requirements.txt` | `pytest` | `ruff check` | `python main.py` |
| Go | `go mod download` | `go test ./...` | `go vet ./...` | `go run .` |
| Rust | `cargo build` | `cargo test` | `cargo clippy` | `cargo run` |
| R | `renv::restore()` | `testthat` | `lintr` | `Rscript app.R` |

Detalle completo del mapeo a las 12 features en `references/12-features.md`.
