# MV Kobra AI — Gate de producción ECC

> Puntaje bajo la rúbrica de `.claude/skills/ecc/SKILL.md` (ECC v2.2.0,
> skill `production-audit`). **Evidencia ejecutada o no cuenta.**
> Complementa a [`AUDITORIA_PRODUCCION.md`](AUDITORIA_PRODUCCION.md), que
> documenta la auditoría manual de agosto 2026; esto es el gate reproducible.

**Veredicto: 92/100 → 9/10. Vendible, sin bloqueantes conocidos, con dos
verificaciones que solo se pueden cerrar fuera de un contenedor Linux (instalar
el .exe en Windows real y un cobro real por MercadoPago).**

## Evidencia ejecutada

| Verificación | Comando | Resultado |
|---|---|---|
| Los 4 gates de CI | `python3 verificar.py` | ✅ verde |
| Suite Python | (gate 4) | ✅ **1805 pasaron**, 9 skip, 0 fallas, 224 s |
| Linter | `ruff check .` (gate 1) | ✅ sin hallazgos |
| Tests de pagos y licencias | `npm test` (gate 2) | ✅ verde |
| Dataset con semilla fija | (gate 3) | ✅ reproducible |
| Recorrido comercial E2E | `python3 packaging/auditoria_e2e.py` | ✅ **todo PASS** |
| Dependencias Node | `npm audit --audit-level=high` | ✅ 0 vulnerabilidades |
| Secretos versionados | `git ls-files \| grep -E '\.env\|\.pem\|\.keystore\|id_rsa'` | ✅ ninguno |

El E2E cubre el camino del que paga de punta a punta: instalación limpia →
demo → trial vencido → compra → licencia emitida por el firmador real de Node
→ validación con PyJWT → gateo de 12 combinaciones plan×módulo → desbloqueo
Owner. Las 12 combinaciones de plan dieron exactamente el HTTP esperado, y un
código Owner equivocado devolvió 400.

## Por qué 9 y no 10

Ningún tope duro de la rúbrica aplica: hay auth server-side sobre los 88
endpoints, rate limiting en las funciones serverless (`api/_ratelimit.js`,
usado por checkout, webhook, verify-payment, copiloto y solicitar-demo),
health checks en `/salud` y `/health`, y cero secretos commiteados.

Lo que falta para 10 no es código, es evidencia que este entorno no puede
producir:

1. **Instalación real en Windows.** El instalador NSIS compila en CI
   (`build_windows.yml`), pero nadie corrió el `.exe` en una máquina Windows
   limpia dentro de esta auditoría. Es el primer contacto del cliente que paga.
2. **Un cobro real por MercadoPago.** El circuito está probado contra un
   `fetch` interceptado y contra el firmador real de licencias, no contra la
   pasarela en modo producción.
3. **CI en verde en GitHub.** `AUDITORIA_PRODUCCION.md` reporta 8 corridas sin
   runner por cuota de Actions agotada. La rúbrica topea en 8/10 cuando CI no
   está verde; acá el gate local corre exactamente lo mismo que CI
   (`verificar.py` existe para eso, y `tests/test_verificar_cubre_ci.py` falla
   si CI suma un gate y este script no), así que se computa como verificado
   localmente pero **no** como CI verde.

## Arreglado en esta pasada

- `docs/AUDITORIA_PRODUCCION.md` mandaba a correr `python3 auditoria_e2e.py`
  desde la raíz. El archivo vive en `packaging/`, así que quien seguía el doc
  se comía un "No such file or directory" y el guion de auditoría quedaba, en
  los hechos, no reproducible. Corregido a `packaging/auditoria_e2e.py`.

## Evidencia faltante (cerraría el 10/10)

- Un `.exe` instalado y abierto en Windows 10/11 limpio.
- Una compra real de cada plan con dinero real, y la licencia resultante
  activando el producto.
- Una corrida de CI en verde en GitHub Actions con cuota disponible.

## Próxima acción

Correr `python3 verificar.py` antes de cada push (o
`python3 verificar.py --instalar-hook` para que sea automático), y reservar el
10/10 para cuando existan las tres evidencias de arriba.
