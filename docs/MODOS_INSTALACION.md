# Cómo instalar MV Kobra AI: dos formas, el mismo programa

Hay **dos** maneras de poner el programa en una máquina. Corren exactamente lo
mismo —mismas pantallas, mismas funciones, mismo motor— y se diferencian en
cómo llegan y en qué dejan atrás.

## Elegí en diez segundos

| | **Instalador** | **Carpeta portable** |
|---|---|---|
| ¿Sos administrador de esa máquina? | Sí | No hace falta |
| ¿Te dejan instalar software? | Sí | No hace falta |
| Ícono en Escritorio y Menú Inicio | ✅ | ❌ (se abre desde la carpeta) |
| Desinstalador en «Agregar o quitar programas» | ✅ | ❌ (se borra la carpeta) |
| Toca el registro de Windows | Sí (entrada de desinstalación) | **No** |
| Dónde guarda los datos | Carpeta del usuario, elegible | **Dentro de la propia carpeta** |
| Se lleva en un pendrive | No | ✅ |
| No deja rastro al irse | — | ✅ |

**Regla práctica:** si la máquina no es tuya, **portable**.

## Los dos escenarios reales

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
| ¿Manda datos afuera? | **No.** Corre entero en esa máquina. |
| ¿Necesita internet? | **No** para operar. |
| ¿Abre puertos hacia afuera? | **No.** Levanta un servidor en `127.0.0.1` y abre el navegador ahí: es comunicación dentro de la misma máquina. |
| ¿Instala servicios o tareas programadas? | **No**, en ninguno de los dos modos. |
| ¿Modifica el registro? | El instalador, solo la entrada de desinstalación. El portable, **nada**. |

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
