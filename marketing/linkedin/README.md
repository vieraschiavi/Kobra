# mv-linkedin

Publica en LinkedIn con la **API oficial**. Sin dependencias externas.

## Por qué no es el MCP que trajiste

El servidor MCP de LinkedIn que pasaste (`linkedin-mcp-server`) **no publica**: es
un scraper. Usa `patchright` —un fork de Playwright hecho para evadir la
detección de bots— y se autentica con la cookie `li_at` de tu sesión. Dos
consecuencias concretas:

1. **No tiene la funcionalidad que pediste.** Lee perfiles y ofertas; no
   escribe posts.
2. **Viola los Términos de LinkedIn** (raspado automatizado, evasión de
   detección). El costo real no es teórico: LinkedIn restringe cuentas por
   esto, y la cuenta en juego es la de 1.500 seguidores que es tu único canal
   de distribución.

Esto usa el camino oficial: OAuth 2.0 y `POST /rest/posts`.

## Preparar la app en LinkedIn (una vez)

1. Entrá a <https://www.linkedin.com/developers/apps> → **Create app**.
   Hace falta una **página de empresa** de LinkedIn para asociar la app.
2. En la pestaña **Products**, pedí estos dos:
   - *Sign In with LinkedIn using OpenID Connect* → da `openid` y `profile`
     (de ahí sale tu id de miembro, que arma el URN de autor).
   - *Share on LinkedIn* → da `w_member_social`, el permiso de publicar.
   La aprobación de ambos suele ser automática o de pocos minutos.
3. En **Auth** → *Authorized redirect URLs*, agregá exactamente:
   `http://localhost:8765/callback`
4. Copiá **Client ID** y **Client Secret** al `.env`.

```bash
cp .env.example .env   # y completá los dos valores
python3 linkedin_publicar.py --autorizar
```

Se abre el navegador, autorizás, y el token queda en
`~/.mv-linkedin-token.json` con permisos `600`. Dura 60 días.

## Publicar

```bash
# 1. Vista previa (default: NO publica nada)
python3 linkedin_publicar.py posts/kobra-es.txt

# 2. Publicar de verdad (pide escribir PUBLICAR para confirmar)
python3 linkedin_publicar.py posts/kobra-es.txt --publicar
```

El cuerpo va como post y lo que está después de `--- comentario ---` se
publica como primer comentario. **Ahí va el link**: LinkedIn suprime el alcance
de los posts con links externos en el cuerpo, y la CLI se niega a publicar un
post que tenga uno (`https://` o `http://` en el cuerpo → error, código 1).

## Lo que NO hace, y por qué

- **No sube el video.** La API de video de LinkedIn requiere el producto
  *Community Management API*, que sólo se aprueba para partners. El video de
  Kobra lo subís a mano; esta herramienta cubre el texto y el comentario.
- **No programa publicaciones.** Un scheduler que corre en tu máquina falla
  callado cuando la máquina está apagada, que es justo cuando lo necesitás.
- **No lee métricas.** `r_member_social` (leer tus propias estadísticas) es un
  permiso restringido que no se le da a apps individuales.

## Formato de un post

```
# idioma: es
# visibilidad: PUBLIC

Cuerpo del post, tal cual va a salir.

--- comentario ---
El primer comentario, con el link.
```

Las líneas `# clave: valor` de la cabecera son metadatos y no se publican. Un
`#hashtag` en medio del texto es texto normal (hay un test que lo fija).
`visibilidad` acepta `PUBLIC` o `CONNECTIONS`.

## Tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
```

29 tests, sin red. Corren contra `tests/servidor_falso.py`, un LinkedIn de
mentira en localhost que **guarda cada request** para que los tests afirmen
sobre lo que se mandó, no sólo sobre lo que se recibió. Sin eso, la única forma
de probar el cliente sería publicando de verdad en un perfil.

Tres detalles que los tests fijan porque son los que rompen en producción:

| Detalle | Qué pasa si falta |
|---|---|
| Cabecera `LinkedIn-Version` | La API contesta **426** |
| Cabecera `X-Restli-Protocol-Version: 2.0.0` | Parsea los URN con el protocolo viejo |
| El URN sale de `x-restli-id`, no del cuerpo | `/rest/posts` devuelve 201 con cuerpo vacío: te quedás sin el id con el que después se comenta |
| El URN va percent-encoded en la ruta del comentario | Los `:` sin escapar dan **404** |

Verificados a mano sacando cada uno y viendo el test ponerse en rojo.
