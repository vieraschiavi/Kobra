---
description: Revisar el diff actual buscando bugs y mejoras
---

Revisá los cambios sin commitear (o los de $ARGUMENTS):
1. `git diff` para ver qué cambió.
2. Buscá bugs de correctitud, casos borde y problemas de seguridad (¿se filtran secretos? ¿datos reales?).
3. Señalá simplificaciones y reuso.
4. Priorizá por severidad y proponé el fix concreto de cada hallazgo.

No apliques cambios salvo que se pida — primero reportá.
