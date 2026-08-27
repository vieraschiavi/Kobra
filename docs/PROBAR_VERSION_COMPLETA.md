# Probar la versión completa (edición Owner)

> Para vos, el dueño. Cómo correr MV Kobra AI **sin licencia, sin trial y sin
> vencimiento**, con exactamente las mismas funciones que recibe un cliente que
> paga el plan más caro.

**No hace falta un instalador especial.** El instalador público y el del dueño
son el mismo binario: lo que cambia es cómo lo desbloqueás.

---

## Los tres pasos

### 1. Bajá el instalador que ya está publicado

<https://github.com/vieraschiavi/Kobra/releases/tag/v1.5.0> → **`MVKobraAI_Setup.exe`**

Son ~260 MB. No necesita Python ni nada más instalado: deja el ícono en el
Escritorio, la entrada en el Menú Inicio y el desinstalador en «Agregar o quitar
programas».

### 2. Instalalo

Durante el asistente podés elegir la carpeta del programa y la carpeta de datos.
Por defecto usa el disco con más espacio libre, no C:.

### 3. Desbloquéalo con tu credencial

Abrí el programa. En la pantalla que pide la licencia —el mismo campo donde un
cliente pega la suya— escribí:

```
vieraschiavi@gmail.com|TU-CODIGO-DE-25-CARACTERES
```

El mail y el código van pegados, separados por una barra vertical `|`, sin
espacios alrededor.

Listo. La copia queda en edición Owner: todas las pantallas, todos los módulos,
sin cupo de gestiones y sin fecha de vencimiento.

---

## Si perdiste el código

El código **no está en el repositorio y no puede estar** — solo se guarda su
hash. Si no lo tenés, generá uno nuevo:

```bash
python -m kobra.owner --nuevo-codigo
```

Imprime una SAL y un HASH nuevos. Pegalos en `kobra/owner.py` (reemplazando
`_SAL` y `_HASH`), commiteá ese cambio, y guardá el código en claro en tu gestor
de contraseñas. El código viejo deja de funcionar apenas se publica el cambio.

---

## Por qué no hay una carpeta con el instalador Owner en el repo

Es deliberado, y hay un test que lo impide (`tests/test_owner_no_se_regala.py`).

La edición Owner **arranca sin licencia, sin trial y sin vencimiento**. Un
instalador Owner commiteado en el repositorio es el producto completo regalado a
cualquiera que tenga acceso al repo — y a cualquiera que lo tenga en el futuro,
porque lo que entra al historial de git no se borra con un commit.

Esto no es hipotético: el 18 de agosto el workflow `release_owner.yml` cortó la
publicación justamente por esto. `vieraschiavi/Kobra` era **público** en ese
momento, y el gate lo detectó:

```
Visibilidad de vieraschiavi/Kobra: public
##[error]La edicion Owner NO se publica en un repositorio public.
```

Por el mismo motivo `packaging/Owner.bat` está en `.gitignore`: lleva un token
firmado con la privada del dueño, y convierte **cualquier** instalación en la
edición sin límites.

El camino de arriba te da lo mismo sin ese riesgo: el binario que se publica es
el de cliente, y lo que lo convierte en Owner es un código que solo tenés vos.

---

## La otra vía (la del ZIP Owner)

Existe, y es la que arma `release_owner.yml`: un paquete que ya viene con el
sello Owner adentro, para no tener que escribir la credencial. Se dispara desde
**Actions → Release Owner → Run workflow** y publica una release `owner-vX.Y.Z`
en el repo privado.

Hoy no está disponible por dos razones, en este orden:

1. **La cuota de GitHub Actions está agotada.** Desde que el repo pasó a privado,
   cada minuto de CI se descuenta de la cuota mensual. Los jobs fallan en 2
   segundos sin recibir máquina. Se destraba en Settings → Billing → Actions.
2. **Falta `owner-v1.5.0`.** La última es `owner-v1.4.0`, del 12 de agosto. Con
   Actions destrabado, disparar el workflow la genera: el repo ya es privado, así
   que el gate ahora pasa.

Mientras tanto, los tres pasos de arriba no dependen de ninguna de las dos cosas.
