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
| Dominio, CTA | `kit_social.py` (constantes de arriba) |
| **Colores de marca** | `marca.py` — fuente única, la usan también la landing y la presentación |
| El logo vectorial | `vectorizar_marca.py` (regenera los SVG desde el PNG) |
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

## Tokens de marca (`marca.py`)

Los colores estaban escritos a mano en tres lugares —la landing, el generador
de la presentación gerencial y este kit— y habían divergido: la presentación y
el sitio no parecían de la misma empresa. Ahora hay una sola paleta y los tres
la importan. `tests/test_marca.py` falla si alguna copia vuelve a separarse.

El violeta y el amarillo que usaba la presentación no eran colores de marca:
servían para distinguir categorías. Esa necesidad sigue, pero con el azul y el
ámbar que ya usaba la landing.

## Logo vectorial (`vectorizar_marca.py`)

Todo el branding era raster. Estos SVG se reconstruyen desde el PNG sin
redibujar nada a ojo: se despeja del antialias cuánto de cada píxel pertenece a
cada forma, se saca la isolínea en 0,5 —lo que da precisión de sub-píxel— y se
simplifica con Douglas-Peucker.

```bash
python3 -m marketing.vectorizar_marca
```

Genera `assets/brand/mv_icon.svg`, `mv_wordmark.svg` y `mv_wordmark_claro.svg`
(esta última para fondos claros: el "MV" casi blanco desaparecería sobre
papel). El logotipo sale **con fondo transparente**, a diferencia del PNG, que
lo trae incrustado y por eso no se puede poner sobre ningún otro color.

Fidelidad medida contra el PNG original: error medio de 0,34/255 en el isotipo
y 1,04/255 en el logotipo.

## Subtítulos del video (`subtitulos.py`)

El video del Copiloto está narrado en castellano y no tenía subtítulos: quien
elegía portugués o inglés en el sitio se quedaba sin entender la pieza
principal de la landing.

```bash
python3 -m marketing.subtitulos
```

Genera `landing/video/copiloto.{es,pt,en}.vtt`. `setLang()` en la landing
activa la pista del idioma elegido.

**Por qué subtítulos y no doblaje.** La interfaz que se ve *dentro* del video
también está en castellano. Una narración en inglés sobre una pantalla en
español confunde más de lo que ayuda; los subtítulos acompañan el audio
original y encima suman accesibilidad para quien mira sin sonido. Doblar de
verdad exige regrabar la pantalla, no solo la voz.

Los tiempos salen de transcribir el audio real, no de estimarlos. El texto en
castellano es esa transcripción **corregida a mano**: el reconocedor escribía
"cobra" en vez de "Kobra" y confundía varias palabras. Si se regenera la
transcripción, hay que volver a corregirla — hay un test que verifica que el
nombre del producto esté bien escrito.
