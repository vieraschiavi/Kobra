# Cómo instalar MV Kobra AI: tres formas, el mismo programa

Hay **tres** maneras de poner el programa a funcionar. Corren exactamente lo
mismo —mismas pantallas, mismas funciones, mismo motor— y se diferencian en
dónde corre, qué dejan atrás y **dónde quedan los datos**.

## Elegí en diez segundos

| | **Instalador** | **Carpeta portable** | **Servidor del cliente** |
|---|---|---|---|
| ¿Sos administrador de esa máquina? | Sí | No hace falta | No (lo levanta su IT) |
| ¿Te dejan instalar software? | Sí | No hace falta | **No hace falta: no instalás nada** |
| ¿Te dejan ejecutar .exe o .bat? | Sí | Sí | **No hace falta: solo usás el navegador** |
| Ícono en Escritorio y Menú Inicio | ✅ | ❌ (se abre desde la carpeta) | ❌ (es una dirección web interna) |
| Toca el registro de Windows | Sí (entrada de desinstalación) | **No** | **No** |
| **Dónde quedan los datos del cliente** | En esa máquina | Dentro de la propia carpeta | **En el servidor del cliente** |
| Se lleva en un pendrive | No | ✅ | — |
| No deja rastro al irse | — | ✅ | ✅ (se borra el contenedor) |

**Dos reglas prácticas:**

* Si la máquina no es tuya pero podés ejecutar archivos, **portable**.
* Si **no podés ejecutar nada** o los datos del cliente **no pueden tocar tu
  máquina**, **servidor del cliente**.

## Los tres escenarios reales

### Tu laptop, o un cliente que te autoriza a instalar

Bajás `MVKobraAI_Setup.exe` y lo instalás. El asistente deja elegir la carpeta
del programa y la carpeta de datos (por defecto, el disco con más espacio
libre). Queda con ícono, entrada en el Menú Inicio y desinstalador.

### La VM del cliente, o la laptop que te dio la consultora

Ese es el caso de, por ejemplo, entrar a la VM de **Conaprole** con el equipo
que te dio **Practia**: no sos administrador, el antivirus mira con lupa
cualquier ejecutable sin firma, y a veces ni siquiera se puede escribir en la
carpeta que te asignaron.

Ahí va la **carpeta portable**, en tres pasos:

1. Descomprimir `MVKobraAI_Portable.zip` donde puedas escribir.
2. Doble clic en **`MVKobraAI_Diagnostico.bat`** — treinta segundos.
3. Si dio verde, doble clic en **`MVKobraAI_Portable.bat`**.

### La laptop que no te deja ejecutar NADA, con datos que no pueden salir del cliente

Es el caso más restringido, y el que ningún instalador resuelve: la consultora
te da un equipo con **bloqueo de ejecutables** (ni `.exe` ni `.bat`), y encima
la cartera del cliente **no puede pasar por tu máquina**. Instalador y portable
quedan los dos afuera: los dos corren del lado de quien abre el programa.

La salida es dar vuelta el planteo: **el programa corre en el servidor del
cliente y vos lo usás por el navegador.** No instalás nada, no ejecutás nada, y
los datos nunca se mueven de la infraestructura de ellos.

Su IT lo levanta con dos comandos:

```bash
export KOBRA_OWNER_TOKEN="<el sello que te da Martín>"   # entra sin licencia
docker compose up -d app
```

Y vos entrás a `http://<ese-servidor>:8080` desde el navegador de la laptop.

**Qué pasa con el sello.** Es una credencial firmada: hace que la app entre sin
pedir licencia. Viaja como variable de entorno o como secreto montado en un
archivo (`KOBRA_OWNER_TOKEN_FILE`), **nunca dentro de la imagen** — una imagen
con el sello adentro convierte en dueño a cualquiera que la baje. Si falta, el
contenedor **no arranca** y dice por qué: arrancar pidiendo licencia en el
servidor de otra empresa sería peor que no arrancar.

**Sin contraseña, y por eso atado al loopback.** Este modo entra directo. Por
eso el compose publica el puerto en `127.0.0.1` y no en toda la red: se llega
por un túnel SSH (`ssh -L 8080:localhost:8080 usuario@servidor`) o poniéndole
adelante el proxy con autenticación que ya tenga el cliente. Publicarlo en
`0.0.0.0` sin proxy significa que cualquiera que llegue al puerto entra como
dueño.

**¿Y si el cliente no te da ni servidor ni VM?** Entonces no hay dónde correr el
programa del lado de ellos, y la única alternativa honesta es que los datos
salgan de su infraestructura — que es justamente lo que no se quiere. En ese
caso hay dos caminos, y los dos son decisión del cliente, no técnica:

1. **Que te den un extracto anonimizado** (sin nombres ni documentos) para
   trabajar en modo portable. La cartera deja de ser dato personal y el
   problema desaparece.
2. **Que levanten el contenedor en cualquier máquina suya**, aunque no sea un
   servidor: alcanza con una PC de la oficina con Docker. No hace falta una VM
   dedicada.

Lo que no existe es una tercera opción donde el programa corra en tu laptop y
los datos igual no pasen por ella: si el programa los procesa en tu máquina,
estuvieron en tu máquina.

## El diagnóstico es el paso que ahorra la semana

`MVKobraAI_Diagnostico.bat` contesta, **antes** de instalar nada, si esa
máquina va a dejar correr el programa. Comprueba:

- que se pueda **escribir** donde van a ir los datos (escribiendo un archivo de
  verdad, no preguntando permisos: en Windows la ACL puede decir una cosa y la
  política otra);
- que el programa pueda **escuchar en `127.0.0.1`**, que es como se comunica con
  el navegador;
- que haya **espacio** en disco;
- si sos administrador (informativo: recomienda el modo).

Cuando algo falla **dice exactamente qué pedirle a IT**. Esa frase es la
diferencia entre resolverlo en un mail y perder una semana de idas y vueltas.

El informe sale en texto plano y sin acentos, para que se pueda copiar de la
consola de Windows y pegar en un mail sin que se vea roto.

## Lo que le vas a tener que contestar a Seguridad

Las cuatro preguntas que traban una autorización, y sus respuestas:

| Pregunta | Respuesta |
|---|---|
| ¿Manda datos afuera? | **No.** Corre entero donde se instala: la máquina, la carpeta o el servidor del cliente. |
| ¿Necesita internet? | **No** para operar. |
| ¿Abre puertos hacia afuera? | **No.** En instalador y portable levanta un servidor en `127.0.0.1` y abre el navegador ahí: es comunicación dentro de la misma máquina. En modo servidor, el puerto lo publica el cliente en su propia red. |
| ¿Instala servicios o tareas programadas? | **No**, en ninguno de los tres modos. |
| ¿Modifica el registro? | El instalador, solo la entrada de desinstalación. El portable y el contenedor, **nada**. |
| **¿Dónde queda la cartera del cliente?** | En modo servidor, **en los volúmenes de su propia máquina**: no se copia a la laptop de quien usa el programa. |

## Para vos: cómo se construyen

| Qué querés | Doble clic en |
|---|---|
| Instalador de clientes | `packaging\construir_instalador.bat` |
| Carpeta portable | `packaging\construir_portable.bat` |
| Instalador Owner (sin licencia) | `packaging\construir_instalador_owner.bat` |

Los tres reusan **la misma tubería de compilación**. El portable llama al
mismo script con `solo-motor`, que prepara todo y corta antes de armar el
instalador. Dos tuberías paralelas se separan a la primera corrección que se
haga en una sola, y ahí el portable empieza a ser una versión distinta del
producto sin que nadie lo note — que es exactamente lo que no se quiere cuando
un cliente reporta un bug.
