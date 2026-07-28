# Presentación de Canva

**El maestro editable es Canva**, no un archivo de este directorio:
https://www.canva.com/d/VJ__8kGcZ2M3Q7D (enlace también en el README).

## Qué viaja con el repo y qué no

| Archivo | ¿Versionado? | Por qué |
|---|---|---|
| `Kobra_Canva_Honesta_comprimido.pdf` | **Sí** (3,1 MB) | Es lo que alguien necesita para mostrar la presentación sin acceso al Canva. |
| `Kobra_Canva_Honesta.pdf` (19 MB) | No | Export original. Se regenera desde Canva. |
| `Kobra_Canva_Honesta.pptx` (13 MB) | No | Ídem, para editar fuera de Canva. |
| `Kobra_Canva.pdf` / `.pptx` (53 MB) | No | Versión anterior, **superada**: la "Honesta" es la que tiene las cifras marcadas como ilustrativas (ver README). |

Los cuatro originales suman 85 MB. Meterlos en git los deja en el historial
para siempre y en cada clon, y GitHub avisa a partir de los 50 MB por archivo.
Por eso viaja solo la versión comprimida.

## Regenerar el comprimido

Después de exportar una versión nueva desde Canva a `Kobra_Canva_Honesta.pdf`:

```bash
python3 presentation/comprimir_canva.py
```

Rasteriza cada página a 150 ppp y la re-comprime en JPEG. Cada página de Canva
ya es una sola imagen a página completa — no hay texto seleccionable que
perder — así que la única pérdida real es resolución que la pieza no usaba.
El resultado pesa ~6× menos y se ve igual en pantalla y al proyectar.

## Ojo con la marca

Esta presentación viene de antes del rebrand: dice **"Kobra"** en vez de
**"MV Kobra AI"** y usa un verde brillante que no es el verde de marca
(`#00c896`, definido en `marketing/marca.py`). Actualizarla hay que hacerlo en
Canva — desde el repo no se puede.
