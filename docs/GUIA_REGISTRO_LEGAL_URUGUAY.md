# ⚖️ Proteger MV Kobra AI en Uruguay — guía práctica

> **Orientación, no asesoría jurídica.** Para el trámite final consultá al
> **Consejo de Derechos de Autor** (Biblioteca Nacional / MEC), a la **DNPI**
> (MIEM) o a un abogado de propiedad intelectual. Los montos son **aproximados
> y cambian**: confirmá los aranceles vigentes antes de pagar.

---

## Lo primero (y tranquilizador): ya sos el dueño

En Uruguay el **software está protegido por derecho de autor** de forma
**automática desde que lo creás** — Ley 9.739 (Propiedad Literaria y Artística),
modificada por la **Ley 17.616**, que incluye expresamente a los *programas de
computación* y las *bases de datos* como obras protegidas. No necesitás
registrar nada para *tener* el derecho.

Y como ya aclaraste, **no tenés empleador**: al ser autor único, la titularidad
de los derechos patrimoniales es **100 % tuya**.

**Consecuencia:** el registro **no crea** tu derecho, lo **prueba**. Sirve para
tener **fecha cierta de autoría** si algún día tenés que reclamar.

---

## Qué se puede (y qué NO se puede) proteger

| Querés proteger… | Herramienta | Dónde | ¿Sirve? |
|---|---|---|---|
| **El código** (tu obra) | Derecho de autor | Consejo de Derechos de Autor (Biblioteca Nacional, MEC) | ✅ Automático; registrable para prueba |
| **El nombre "MV Kobra AI" / logo** | Marca | **DNPI** (MIEM) | ✅ Muy recomendable si vas a vender |
| **La IDEA / el concepto** ("cobranza con IA") | — | — | ❌ Las ideas no se registran |
| **Un método técnico novedoso** | Patente | DNPI | ⚠️ Difícil: el software "como tal" en general no es patentable |

> 🔑 **Clave:** el derecho de autor protege la **forma en que expresaste** la
> solución (tu código, tus textos, tu UI), **no la idea**. Nadie puede copiar tu
> código, pero sí puede tener "una app de cobranza con IA". Por eso lo que más te
> conviene es: **derecho de autor sobre el código + marca sobre el nombre +
> contratos/NDAs** al vender.

---

## Acciones recomendadas (en orden)

### 1. Blindá la autoría YA (gratis)
- **Historial de git** con fechas y tu autoría (ya lo tenés en este repo).
- Guardá una **copia sellada** (ZIP + hash SHA-256; ya generás `SHA256SUMS`).
- Opcional: un *timestamp* de fecha cierta (escribano, o servicio de sellado).

### 2. Registrá el derecho de autor (barato, alto valor probatorio)
- **Dónde:** Consejo de Derechos de Autor — Registro en la **Biblioteca
  Nacional** (Av. 18 de Julio 1790, Montevideo), dependiente del **MEC**.
- **Qué depositás:** la obra (podés depositar el código; se admite depósito
  parcial/identificatorio del software).
- **Costo aproximado:** bajo — del orden de **unos cientos de pesos**
  (≈ USD 20–60). *Confirmar arancel vigente.*
- **Para qué:** fecha cierta e inscripción oficial de que **vos** sos el autor.

### 3. Registrá la MARCA "MV Kobra AI" (si vas a comercializar)
- **Dónde:** **DNPI — Dirección Nacional de la Propiedad Industrial** (MIEM).
  Se puede iniciar online.
- **Clases (Clasificación de Niza)** que te interesan:
  - **Clase 9** — software / programas de computación.
  - **Clase 42** — servicios de software (SaaS), diseño y desarrollo.
- **Vigencia:** 10 años, **renovable** indefinidamente.
- **Costo aproximado:** aranceles oficiales del orden de **USD 100–250 por
  clase** (búsqueda de antecedentes + solicitud + concesión); sumá honorarios si
  usás agente/abogado de marcas. *Confirmar aranceles DNPI vigentes.*
- **Antes de pagar:** hacé una **búsqueda de antecedentes** en la DNPI para
  verificar que "MV Kobra AI"/"MV Kobra AI" esté disponible en esas clases.

### 4. Al vender: contratos que te protegen
- **Licencia de uso** clara (no cedés el código fuente; licenciás el uso).
- **NDA** antes de mostrar internals a un prospecto.
- Si contratás a alguien para ayudarte: **cláusula de cesión de derechos** a tu
  favor por escrito (si no, el aporte podría no ser tuyo).

### 5. Empleados a futuro: cómo evitar que se lleven el código

> Hoy no tenés empleados (sos autor único), pero esto queda documentado acá
> para cuando llegue el momento de contratar.

**La ley ya juega a tu favor con empleados — no así con contratistas.** La
**Ley 17.616** (que modificó la 9.739) establece que cuando un programa se
crea **dentro de una relación de dependencia** cuyo objeto se relaciona con
ese tipo de creación, se **presume** que el autor (tu futuro empleado) te
cedió a vos, como empleador, los derechos patrimoniales de forma exclusiva —
**salvo pacto en contrario por escrito**. Con un **contratista/freelance**
esa presunción no aplica igual: ahí sí hace falta la cláusula de cesión
explícita del punto 4.

**Aun con la ley a favor, escribilo en el contrato de todos modos.** La ley
dice "salvo pacto en contrario" — sin nada por escrito, un empleado podría
alegar que lo que creó no era parte de "el objeto de su relación laboral"
(p. ej. algo hecho fuera de horario). Un contrato claro evita esa discusión.

Capas de protección, en orden de esfuerzo/costo:

| Capa | Qué hacer | Nota |
|---|---|---|
| **Contrato de trabajo** | Cláusula explícita de cesión de derechos de autor sobre todo lo creado en el marco laboral | Barato, alto valor probatorio, aunque la ley ya lo presuma |
| **Confidencialidad** | Cláusula de confidencialidad (código fuente, modelos, prompts, datos de clientes) durante y después de la relación | Durante el empleo ya aplica el deber de buena fe/lealtad aunque no lo escribas — pero por escrito evita discusiones sobre qué es "secreto" |
| **No competencia posterior** | Si querés impedir que se vaya a armar un competidor con lo aprendido | ⚠️ En Uruguay esto es legalmente discutido: para que valga necesita compensación económica al empleado y hay debate doctrinario sobre su alcance. Consultar a un abogado laboral antes de asumir que es exigible |
| **Marca + derecho de autor registrado** | Puntos 2 y 3 de esta guía | Te da con qué reclamar si alguien (empleado o no) copia y sale a vender algo idéntico |
| **Medidas técnicas** | Ver abajo | Lo que más reduce el riesgo día a día, más que cualquier papel |

**Medidas técnicas (previenen, no solo dan derecho a reclamar después):**
- **Acceso mínimo necesario:** cada persona ve solo lo que necesita para su
  tarea, no el repo completo (permisos granulares por carpeta / repos
  separados para módulos sensibles).
- **Secretos nunca en el código:** ya resuelto — `kobra/config.py` guarda las
  claves cifradas (keyring del sistema), no en texto plano en el repo.
  Mantener esa disciplina también con las claves de producción de cada cliente.
- **Historial de git como evidencia:** cada commit ya queda atribuido a su
  autor con fecha — prueba objetiva de quién escribió qué y cuándo.
- **Checklist de baja (offboarding):** el día que alguien se va, revocar
  accesos ese mismo día — repo, servidor, claves de API, VPN, credenciales de
  clientes. Esto previene fugas reales más que cualquier cláusula.
- **No repartir el código fuente completo si no hace falta:** el "modo PC"
  (instalador Windows) ya distribuye compilado, no el `.py` — mantener esa
  lógica también para lo que vea un empleado que no necesite el motor completo.
- **Monitoreo básico:** alertas si alguien clona todo el repo de golpe, sube a
  un remoto personal, o descarga volúmenes grandes de datos de clientes.

---

## Resumen de plata (aprox., a confirmar)

| Ítem | Costo aprox. | Recurrencia |
|---|---|---|
| Derecho de autor (código) automático | **$0** | — |
| Registro derecho de autor (Biblioteca Nacional) | **~USD 20–60** | única vez |
| Marca "MV Kobra AI" en DNPI (por clase) | **~USD 100–250** | cada 10 años (renovable) |
| 2 clases (9 + 42) | **~USD 200–500** | cada 10 años |
| Abogado/agente de marcas (opcional) | variable | por trámite |

**Prioridad práctica y económica:**
1. Blindaje de autoría (gratis, ya está).
2. Registro de derecho de autor (barato, alta prueba).
3. Marca "MV Kobra AI" cuando estés por salir a vender (protege el nombre, que es
   con lo que te van a identificar en el mercado).
4. Contrato con cesión de IP + confidencialidad y acceso limitado al repo,
   recién cuando contrates a la primera persona (sección 5) — no hay nada
   urgente que hacer en esto hoy.

> La **idea** no se protege; lo que te da ventaja defendible es tu **código**
> (derecho de autor), tu **marca** (DNPI) y tus **contratos**. Con eso, si
> alguien copia, tenés cómo reclamar.
