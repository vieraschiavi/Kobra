---
description: Checkpoint + commit + push + PR draft
---

Publicá el trabajo actual:
1. Corré los tests del proyecto; si fallan, pará y reportá.
2. `git add` de los cambios relevantes y mostrá un `git diff --staged` resumido.
3. Commiteá con un mensaje claro y descriptivo (qué y por qué).
4. Push a la rama de trabajo (`git push -u origin <rama>`).
5. Si no existe un PR abierto para la rama, abrí uno en **draft** siguiendo el template del repo si lo hay.

Contexto extra del usuario: $ARGUMENTS
