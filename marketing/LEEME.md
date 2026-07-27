# Kit de contenido para redes

Genera los banners, el copy y los storyboards de reels de MV Kobra AI, y los
empaqueta en ZIPs listos para publicar.

```bash
pip3 install playwright pillow            # solo en la máquina que genera
apt-get install -y fonts-inter            # tipografía del diseño
python3 -m marketing.generar_kit_social
python3 -m marketing.generar_kit_social --publicar-og   # + actualiza landing/og.png
```

## La tarjeta de previsualización (`landing/og.png`)

Es la única pieza que **se versiona en el repo**: no es material que alguien
baja, es un asset que sirve el sitio. Las páginas públicas la referencian por
URL absoluta en sus etiquetas Open Graph, y es lo que se ve cuando alguien
comparte el link en LinkedIn, X o WhatsApp. Si cambia el diseño o la captura,
hay que regenerarla con `--publicar-og` y commitear el PNG.

Las tres páginas que la usan — `landing/index.html`, `landing/descarga.html` y
`dashboard_estatico/index.html` — están cubiertas por
`tests/test_meta_social.py`: si a alguna se le cae una etiqueta, si la imagen
queda con una ruta relativa (que ningún scraper resuelve) o si el PNG deja de
medir 1200×630, el test falla.

Sale en `dist/social/` (ignorado por git — es material generado, se regenera
cuando se necesita):

```
dist/social/
├── banners/                      5 PNG en tamaño real
├── copy.md                       texto por red
├── reels.md                      storyboards cuadro por cuadro
├── LEEME.md
├── MVKobraAI_Kit_Social.zip      todo
└── MVKobraAI_Banners.zip         solo los PNG
```

## Qué editar

| Quiero cambiar… | Archivo |
|---|---|
| Titulares, bajadas, formatos de banner | `kit_social.py` → `BANNERS` |
| Texto de los posts | `kit_social.py` → `COPY` |
| Guiones de reels | `kit_social.py` → `REELS` |
| Colores, dominio, CTA | `kit_social.py` (constantes de arriba) |
| Composición, tipografías, tamaños | `generar_kit_social.py` |

## Reglas que el generador hace cumplir

No son preferencias de estilo: si alguna se viola, el generador termina con
error y no da los ZIP por buenos.

- **Sin precios.** Ninguna pieza publicada muestra importes ni planes.
- **Un solo dominio**, `mvkobranzaia.com`. Las URLs de preview de Vercel
  cambian con cada deploy y no van en material publicado.
- **Sin solapes ni texto recortado.** Después de renderizar se mide el DOM de
  cada pieza: ninguna zona invade a otra, nada se sale del lienzo, ningún
  texto queda cortado.
- **Tipografía verificada.** Si no hay una familia del diseño instalada, se
  planta en vez de exportar con la fuente de fallback.

## Por qué valida en vez de solo renderizar

La versión anterior de este kit se armó como un HTML suelto, con las piezas
posicionadas en absoluto. Se veía bien en el navegador donde se diseñó y salió
mal al exportar: **el texto pisaba el mockup**. La causa no era el CSS sino la
tipografía — el diseño pedía `Segoe UI`/`Roboto`, la máquina que exportó no las
tiene, cayó a una fuente más ancha, los titulares crecieron y se comieron el
espacio del mockup. Con posicionamiento absoluto nada lo impide y nada lo
avisa.

Acá el layout es CSS grid (cada pieza en su celda) y hay una pasada de
medición que corre siempre. Los tests de `tests/test_kit_social.py` renderizan
los 5 banners y fallan si alguno vuelve a romperse.
