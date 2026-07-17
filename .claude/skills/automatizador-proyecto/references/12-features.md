# Las 12 features de Claude Code → cómo las aplica este automatizador

Basado en "Claude Code's Top 12 Features" (MattKnowsAI). Referencia de diseño del skill.

1. **CLAUDE.md** — Contexto persistente por sesión. El automatizador lo genera desde el diagnóstico
   del repo (stack, comandos, estructura, convenciones). Es lo primero que Claude lee al abrir.

2. **Permissions** — Listas allow/deny en `.claude/settings.json`. Permite lo seguro y repetitivo
   (git status, tests, lectura) sin preguntar; deniega lo destructivo (rm -rf, push --force, leer
   secretos). Menos fricción, sin barra libre.

3. **Plan Mode** — Planificar en solo-lectura antes de tocar. Comando `/plan` + convención en
   CLAUDE.md de "plan antes de cambios grandes".

4. **Checkpoints** — Puntos de retorno (A→B→C→D→E). Se materializa como política de commits
   frecuentes + comando `/ship` que hace el checkpoint antes de publicar.

5. **Skills** — Capacidades reutilizables compartidas entre equipos y entornos. Este mismo artefacto
   ES una skill; el proyecto queda listo para invocar otras skills relevantes.

6. **Hooks** — Acciones automáticas en eventos. `SessionStart` instala deps y verifica que el proyecto
   arranca, así cada sesión empieza con el entorno sano.

7. **MCP** — Conexión a herramientas externas (GitHub, Slack, Notion, Figma). Template `.mcp.json`
   con placeholders y variables de entorno.

8. **Plugins** — Empaquetar todo e instalar desde un marketplace. La estructura generada es
   compatible con empaquetar el conjunto como plugin de equipo.

9-10. **Context / Compact** — Manejo de contexto largo. Reglas en CLAUDE.md de cuándo usar `/compact`
   y cómo mantener el contexto enfocado.

11. **Slash commands** — Comandos `/` reutilizables. Se generan `plan`, `ship`, `review`, `test`.

12. **Sub-agents** — Trabajo delegado: exploración pesada, trabajo en paralelo, expertise
   especializado. Se generan tres agentes: `explorer`, `parallel-worker`, `specialist`.
