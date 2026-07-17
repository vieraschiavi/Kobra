---
description: Checkpoint + commit + push + PR draft
---

Publicá el trabajo actual:
1. Corré `python3 -m pytest -q tests/`; si falla, pará y reportá.
2. `git add` de lo relevante y mostrá un `git diff --staged` resumido.
3. Commiteá con mensaje claro (qué y por qué).
4. `git push -u origin <rama>`.
5. Si no hay PR abierto para la rama, abrí uno en **draft** usando el template del repo si existe.

Contexto extra: $ARGUMENTS
