# ⚖️ Vender MV Kobra AI en Brasil (Fase 2) — guía práctica de LGPD y cobranza

> **Orientación, no asesoría jurídica.** Esta guía resume, en español y para
> quien no es abogado, los puntos de la **LGPD** (Lei Geral de Proteção de
> Dados, **Lei n.º 13.709/2018**) y de la normativa de cobranza brasileña que
> más impactan a un producto como MV Kobra AI. **Antes de tocar una cartera
> real de deudores brasileños**, esto tiene que pasar por un **abogado
> brasileño especializado en LGPD/direito do consumidor** (idealmente con
> experiencia en fintech/cobrança). Las leyes, resoluciones de la **ANPD**
> (Autoridade Nacional de Proteção de Dados) y la jurisprudencia citada acá
> **cambian**: confirmá la versión vigente antes de operar.

---

## Lo primero (y lo que hay que internalizar ya): LGPD es más exigente que la 18.331 en varios puntos

MV Kobra AI ya cumple, para Uruguay, con la Ley 18.331 (ver
`docs/PLANTILLA_DPA.md` y `kobra/cumplimiento.py`). La LGPD brasileña se
parece mucho en estructura (bases legales, derechos del titular, DPO,
transferencias internacionales), pero tiene **tres diferencias que importan
directamente para un producto de scoring + cobranza con IA**:

1. **Tiene un regulador activo y con dientes** — la ANPD ya aplicó multas,
   tiene un régimen de sanciones reglamentado (dosimetría) y resoluciones
   específicas sobre incidentes de seguridad y transferencias internacionales
   que la 18.331 no tiene con ese nivel de detalle.
2. **Tiene un artículo específico sobre decisiones automatizadas de crédito**
   (Art. 20) que menciona expresamente el "perfil de consumo e de crédito" —
   esto pega de lleno en el **ProbPago** (score de pago) y el motor de
   **originação** de este producto.
3. **La regulación de horarios/frecuencia de cobranza no es un único cuerpo
   nacional uniforme**: combina el Código de Defesa do Consumidor (CDC,
   federal), la Lei do Superendividamento (federal, pero enfocada en oferta
   de crédito) y **leyes estaduales** (de cada estado) que fijan horarios
   distintos entre semana y sábado. Esto tiene consecuencia directa sobre
   `PoliticaContacto` en `kobra/cumplimiento.py` — ver la sección dedicada
   más abajo.

---

## 1. Bases legales para tratar datos de deudores (LGPD Art. 7 y 10)

La LGPD exige una base legal para cada tratamiento de datos personales. Para
cobranza, las dos bases relevantes son:

- **Art. 7, X — "proteção do crédito"**: la propia ley menciona la protección
  del crédito (incluida la operativa regulada por leyes específicas, p. ej.
  registros de morosos) como base legal autónoma, sin necesitar consentimiento
  del titular.
- **Art. 7, IX — "legítimo interesse"**: contactar a un deudor por
  email/teléfono/WhatsApp para gestionar el cobro de una deuda existente y
  concreta encaja como ejercicio regular de un derecho del acreedor
  (Art. 10, II).

**Condición que impone el Art. 10**: el legítimo interés solo cubre datos
**estrictamente necesarios** para la finalidad (identificación, contacto,
datos de la obligación) — no habilita tratar categorías sensibles (salud,
etc.), algo que ya está resuelto en `PLANTILLA_DPA.md` ("el Encargado no
trata categorías especiales de datos"). La ANPD publicó una **Guía de
Legítimo Interés** que recomienda documentar un **LIA/Relatório de Impacto**
(análisis de necesidad + proporcionalidad + balance de intereses) cuando se
usa esta base — es un documento interno, no un trámite de registro, pero
conviene tenerlo redactado antes de vender.

**Fuentes**: [Lei 13.709/2018 (texto)](http://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709compilado.htm) · [Guia de Legítimo Interesse — ANPD](https://www.gov.br/anpd/pt-br/centrais-de-conteudo/materiais-educativos-e-publicacoes/guia_legitimo_interesse.pdf)

---

## 2. Derechos del titular (Art. 18) — equivalentes a los de la 18.331

El titular de datos (el deudor) puede pedir, en cualquier momento y sin
costo: confirmación de que se lo trata, **acceso**, **rectificación**,
anonimización/bloqueo/**eliminación** de datos innecesarios o tratados
incorrectamente, **portabilidad**, información sobre con quién se
compartieron sus datos, y **revocación del consentimiento** (cuando el
tratamiento se basa en consentimiento — no es el caso típico de cobranza,
que se basa en legítimo interés/protección del crédito, pero sí aplica si en
algún momento se pide consentimiento para otra finalidad, p. ej. marketing).

Esto es funcionalmente equivalente a lo que ya prevé el DPA de Uruguay
(cláusula "f. Asistencia" en `PLANTILLA_DPA.md`), pero **el canal para
ejercer estos derechos tiene que estar identificado y accesible en
portugués** para un titular brasileño — no alcanza con reusar el canal en
español pensado para Uruguay.

**Fuente**: [Art. 18 LGPD — LGPD Brasil](https://lgpd-brasil.info/capitulo_03/artigo_18)

---

## 3. Decisiones automatizadas y perfilamiento (Art. 20) — el punto que más importa para ProbPago y originação

Este es el artículo que **más impacto técnico/producto** tiene:

> El titular tiene derecho a **solicitar la revisión** de decisiones tomadas
> **únicamente** con base en tratamiento automatizado de datos personales que
> afecten sus intereses, **incluyendo decisiones destinadas a definir su
> perfil de consumo y de crédito** (la ley lo dice explícitamente).

Aplicado a MV Kobra AI:

- El **score ProbPago** (probabilidad de pago) y el motor de **originação**
  (scoring de crédito) son exactamente el tipo de tratamiento que el Art. 20
  contempla.
- El controlador (el cliente banco/fintech/cooperativa, "el Responsable" en
  el DPA) debe poder **explicar, cuando se lo pidan, los criterios y el
  procedimiento** usado por el modelo (respetando secreto comercial/industrial
  — no hay que revelar el modelo entero, pero sí los factores generales).
- Debe existir un **canal para que un humano revise** la decisión cuando el
  deudor lo pida — no puede ser un rechazo puramente automático sin
  posibilidad de reclamo.
- **Zona gris real, no resuelta**: no está definido en la ley ni en
  reglamento de la ANPD qué tan "únicamente automatizada" tiene que ser una
  decisión para gatillar este derecho, ni exactamente cómo debe ejecutarse la
  revisión (¿alcanza con que un supervisor mire el caso? ¿tiene que poder
  cambiar el resultado?). Esto viene de doctrina y de un proceso de consulta
  pública de la ANPD ("Tomada de Subsídios") todavía abierto/en evolución —
  **hay que confirmar el estado actual con el abogado antes de vender el
  motor de originação a un cliente brasileño**, porque si el cliente usa
  ProbPago/originação para **decisiones automáticas de negar crédito o
  intensificar cobranza sin intervención humana**, el riesgo regulatorio es
  mayor que en Uruguay (donde la 18.331 no tiene un artículo equivalente tan
  explícito sobre perfil de crédito).

**Fuentes**: [Art. 20 LGPD — LGPD Brasil](https://lgpd-brasil.info/capitulo_03/artigo_20) · [Artigo 20 da LGPD — Blog IDP](https://blog.idp.edu.br/direito-digital/artigo-20-lgpd-revisao-decisoes-automatizadas/) · [Tomada de Subsídios IA e Revisão de Decisões Automatizadas — Participa+Brasil](https://www.gov.br/participamaisbrasil/tomada-de-subsidios-inteligencia-artificial-e-revisao-de-decisoes-automatizadas)

---

## 4. Encarregado de Dados (DPO) — ¿hace falta nombrar uno?

- La LGPD (Art. 41) exige que el controlador designe un **Encarregado**
  (DPO), con contacto público (idealmente en el sitio web), que reciba
  reclamos de titulares y de la ANPD.
- **Actualización 2022**: la **Resolução CD/ANPD n.º 2/2022** eximió a los
  "agentes de tratamiento de pequeño porte" (empresas chicas, startups) de la
  obligación **formal** de nombrar un Encarregado — **siempre que ofrezcan un
  canal de comunicación accesible y funcional** para que el titular ejerza
  sus derechos. Es una dispensa de la formalidad, no de la función: alguien
  tiene que seguir respondiendo esos pedidos.
- **Importante**: la ANPD puede exigir en cualquier momento que una empresa
  chica cumpla igual con esta obligación, según el riesgo/volumen de los
  datos que trata. Tratar **carteras de deudores con datos financieros** es
  precisamente el tipo de operación de mayor riesgo — **recomendación
  práctica: nombrar un Encarregado desde el día uno en Brasil**, aunque la
  empresa sea chica, en vez de apoyarse en la dispensa. Es barato (puede ser
  una persona del equipo o un tercero contratado) y evita una discusión con
  la ANPD sobre si corresponde o no la excepción.

**Fuentes**: [Art. 41 LGPD — LGPD Brasil](https://lgpd-brasil.info/capitulo_06/artigo_41) · [Resolução CD/ANPD n.º 2/2022 — dispensa DPO pequenas empresas](https://blog.bcompliance.com.br/2025/07/11/lgpd-pequenas-empresas-dispensa-dpo-canal-comunicacao/)

---

## 5. Transferencia internacional de datos (Art. 33–36) — clave porque la infra de Kobra no está en Brasil

MV Kobra AI ya modela esto para Uruguay en `PLANTILLA_DPA.md` (sección 4:
Anthropic/OpenAI/Twilio/Meta procesan datos fuera del país). Para Brasil el
mecanismo formal **cambió recientemente y es más estricto**:

- La **Resolução CD/ANPD n.º 19/2024** aprobó el **Regulamento de
  Transferência Internacional de Dados (RTID)**, que reglamenta los Art. 33 a
  36 de la LGPD.
- Si se usa el mecanismo de **cláusulas contractuales** para justificar el
  envío de datos a proveedores fuera de Brasil (Anthropic, OpenAI, Twilio,
  Meta, o el propio hosting de MV Kobra AI si no está en Brasil), la ANPD
  exige adoptar **integralmente y sin modificar el texto** sus
  **Cláusulas-Padrão Contratuales (CPCs, Anexo II del RTID)** — no alcanza con
  una cláusula genérica redactada a mano como la que hoy tiene el DPA de
  Uruguay ("cláusulas contractuales tipo u otro mecanismo válido").
- Hay un plazo (originalmente 12 meses desde la resolución) para migrar
  contratos existentes a esas cláusulas estándar — **confirmar con el
  abogado si ese plazo ya venció o sigue corriendo** a la fecha en que se
  firme el primer contrato brasileño.
- Alternativa: transferir a un país/organismo reconocido por la ANPD como de
  "protección adecuada" (lista que la propia ANPD mantiene y actualiza) —
  hay que revisar esa lista al momento de operar.

**Consecuencia práctica para el DPA**: la sección 4 del `PLANTILLA_DPA.md`
actual **no sirve tal cual para Brasil** — para un cliente brasileño hay que
redactar una sección de transferencia internacional que cite la LGPD y, si
corresponde, incorpore las CPCs de la ANPD (Anexo II del RTID) en vez de la
fórmula genérica pensada para la 18.331.

**Fuentes**: [ANPD aprova regulamento sobre transferências internacionais de dados](https://www.gov.br/anpd/pt-br/assuntos/noticias/resolucao-normatiza-transferencia-internacional-de-dados) · [Minuta/Regulamento RTID — ANPD (PDF)](https://www.gov.br/anpd/pt-br/assuntos/noticias/MinutaRegulamentoTID.pdf)

---

## 6. Notificación de incidentes de seguridad — plazo mucho más corto que "48-72 horas"

- La **Resolução CD/ANPD n.º 15/2024** aprobó el **Regulamento de
  Comunicação de Incidente de Segurança (RCIS)**.
- Plazo: el controlador debe comunicar el incidente a la ANPD (y al titular,
  si corresponde) en **hasta 3 (tres) días hábiles** desde que tomó
  conocimiento de que el incidente afectó datos personales — salvo que otra
  ley específica fije un plazo distinto.
- Se admite una **comunicación preliminar** (con lo que se sepa hasta ese
  momento) y **complementarla** en hasta 20 días hábiles adicionales.
- No todo incidente se comunica: hay que evaluar si genera "risco ou dano
  relevante" a los titulares — pero dado que acá se trata de datos
  financieros/de deuda, conviene asumir un umbral bajo (a definir con el
  abogado) para decidir cuándo notificar.
- **Impacto en `PLANTILLA_DPA.md`**: el plazo interno de "notificar sin
  demora indebida (48–72 horas)" que hoy tiene la plantilla para Uruguay
  **debería acortarse en la versión Brasil** — el Encargado (MV Kobra AI)
  tiene que avisar al Responsable (el cliente) con margen suficiente para
  que el Responsable, a su vez, pueda cumplir la ventana de 3 días hábiles
  ante la ANPD. Un plazo de 24 horas (en vez de 48–72) sería más prudente
  para la versión brasileña de la plantilla.

**Fuentes**: [Regulamento de Comunicação de Incidente de Segurança — ANPD (PDF)](https://www.lgpd.ms.gov.br/wp-content/uploads/2024/05/REGULAMENTO-DE-COMUNICACAO-DE-INCIDENTE-DE-SEGURANCA-ABRIL-2024-ANPD-.pdf) · [Comunicação de incidente de segurança — Portal ANPD](https://www.gov.br/anpd/pt-br/canais_atendimento/agente-de-tratamento/comunicado-de-incidente-de-seguranca-cis)

---

## 7. Sanciones (Art. 52) — el "por qué" de tomarse esto en serio

En orden creciente de gravedad, la ANPD puede aplicar: advertencia, **multa
simple de hasta el 2 % de la facturación de la empresa en Brasil** (excluidos
impuestos), **tope de R$ 50 millones por infracción**, multa diaria,
publicación de la infracción, bloqueo/eliminación de los datos afectados,
**suspensión del banco de datos hasta 6 meses (prorrogable)**, suspensión de
la actividad de tratamiento, y prohibición parcial/total de operar con datos.
Hay un **Regulamento de Dosimetria** (2023) que fija los criterios para
graduar la sanción (gravedad, cooperación, buenas prácticas previas, daño
causado). La ANPD ya aplicó su primera multa real — no es una ley "de
papel".

**Fuentes**: [Art. 52 LGPD — sanciones administrativas](https://lgpd-brasil.info/capitulo_08/artigo_52) · [ANPD aplica a primeira multa por descumprimento à LGPD](https://www.gov.br/anpd/pt-br/assuntos/noticias/anpd-aplica-a-primeira-multa-por-descumprimento-a-lgpd)

---

## 8. Horarios y frecuencia de contacto en cobranza — el equivalente brasileño de `PoliticaContacto`

Acá es donde hay que prestar más atención al **mapeo con el código
existente** (`kobra/cumplimiento.py`).

### 8.1 Marco legal

- **CDC (Código de Defesa do Consumidor), Art. 42**: en la cobranza de
  deudas, el consumidor **no puede ser expuesto al ridículo ni sometido a
  constreñimiento o amenaza**. No fija un horario numérico — es un principio
  general que la jurisprudencia fue concretando.
- **Jurisprudencia dominante** (tribunales estaduales y STJ en casos
  análogos): las llamadas de cobranza son admisibles **en días hábiles, de
  8h a 20h**, y **los sábados solo hasta las 14h**. Domingos y feriados
  nacionales: cobranza telefónica prohibida en cualquier horario. Esto **no
  es un artículo único y cerrado de una ley federal** — es una construcción
  de doctrina y jurisprudencia sobre la base del Art. 42 del CDC.
- **Leyes estaduales**: al menos **San Pablo** tiene una ley propia que
  codifica exactamente eso — **Lei Estadual n.º 15.426/2014**: cobranza
  telefónica permitida de 8h a 20h de lunes a viernes, de 8h a **14h los
  sábados**, prohibida domingos/feriados, con multas de hasta R$ 7,2
  millones por infracción. **Otros estados pueden tener normas propias
  distintas** — hay que verificar estado por estado si Kobra va a operar con
  carteras de deudores domiciliados en más de un estado (lo más probable).
- **Lei n.º 14.181/2021 (Lei do Superendividamento)**, que modificó el CDC
  agregando los Art. 54-A a 54-G: está más enfocada en **oferta responsable
  de crédito** (prohíbe asediar/presionar para que el consumidor contrate
  crédito, en especial a personas mayores, analfabetas, enfermas o
  vulnerables) que en el horario de las llamadas de cobranza en sí — pero es
  directamente relevante para el motor de **originação**/scoring de Kobra si
  en algún momento se usa también para *ofrecer* crédito (no solo cobrar
  deuda existente), y para la relación general del cliente-acreedor con
  deudores en situación de sobreendeudamiento.

### 8.2 Qué tan bien mapea esto con `PoliticaContacto`

Revisando `kobra/cumplimiento.py` (clase `PoliticaContacto` — `hora_inicio`,
`hora_fin`, `dias_habiles`, `permitir_feriados`, `pais`, `max_por_dia`,
`max_por_semana`, `canales`):

**Lo que ya cubre bien:**
- El concepto de franja horaria (`hora_inicio`/`hora_fin`) y días hábiles
  (`dias_habiles`) es exactamente el tipo de control que exige la
  jurisprudencia/leyes estaduales brasileñas — la arquitectura es correcta.
- Los feriados nacionales de Brasil ya están modelados
  (`_FERIADOS_FIJOS_POR_PAIS["BR"]`, con Jueves/Viernes Santo derivados de
  Pascua), lo cual cubre el requisito de "domingos y feriados, prohibido".
- El tope de frecuencia (`max_por_dia`, `max_por_semana`) es una buena
  práctica defensiva: el CDC no fija un número exacto de contactos permitidos
  por día/semana (queda a criterio judicial si algo es "excesivo"/hostigante),
  así que tener un tope configurable y conservador **ayuda a probar buena fe**
  aunque no sea un número exigido literalmente por la ley.
- El opt-out (`PEDIDO_NO_CONTACTAR`, `registrar_no_contactar`) es
  directamente relevante al deber de no insistir del Art. 42 del CDC.

**Lo que falta estructuralmente (a evaluar, sin tocar código en esta guía):**
1. **`hora_fin` es un único valor para todos los `dias_habiles`.** La regla
   brasileña más citada (y la ley de San Pablo, textual) es **8h–20h de
   lunes a viernes, pero 8h–14h los sábados** — un horario de corte distinto
   para el sábado. Hoy `PoliticaContacto` no puede expresar "sábado con
   `hora_fin` distinto" dentro de una misma instancia; `en_horario()` no mira
   `ahora.weekday()`, solo la hora. Para Brasil (a diferencia de Uruguay,
   donde el franja es uniforme 09–20 L–S) esto es una limitación real, no
   solo un detalle: si se configura `hora_fin=20` para cumplir entre semana,
   los sábados quedarían fuera de norma; si se configura `hora_fin=14` para
   cumplir el sábado, se pierde horario válido entre semana.
2. **Granularidad de `pais` es a nivel país, no a nivel estado (UF).** Si la
   ley de horarios de cobranza varía por estado (San Pablo la tiene escrita;
   hay que confirmar cuáles otros estados tienen leyes propias con horarios
   distintos — Rio de Janeiro, Paraná, etc. suelen aparecer en relevamientos
   de despachos de cobranza), una política única `pais="BR"` puede no ser
   suficientemente fina si Kobra opera cartera en varios estados con normas
   distintas. Esto no es urgente para un piloto en un solo estado, pero si
   la cartera es nacional, es un gap a resolver antes de escalar.
3. **Feriados estaduales/municipales** (p. ej. Corpus Christi, aniversarios
   municipales) — el propio código ya trae el disclaimer de que
   `_FERIADOS_FIJOS_POR_PAIS` no los incluye. Para Brasil esto importa más
   que para Uruguay porque el calendario de feriados locales es mucho más
   variado por ciudad/estado.

**Conclusión para el checklist**: los *knobs* que ya existen (horario,
días hábiles, feriados, topes de frecuencia, opt-out) son el lugar correcto
donde resolver esto — no falta una capa nueva de cumplimiento, sino
**parametrización más fina** (horario distinto por día de la semana, y
posiblemente una dimensión de estado/UF) antes de vender una cartera real en
Brasil. Queda anotado como tarea de producto/ingeniería a futuro, no de esta
guía.

**Fuentes**: [Art. 42 CDC — jurisprudência TJDFT](https://www.tjdft.jus.br/consultas/jurisprudencia/jurisprudencia-em-temas/cdc-na-visao-do-tjdft-1/praticas-abusivas/proibicao-de-constrangimentos-ou-exposicao-do-consumidor-ao-ridiculo) · [Lei Estadual (SP) n.º 15.426/2014](https://www.al.sp.gov.br/repositorio/legislacao/lei/2014/lei-15426-22.05.2014.html) · [Horário para cobrança de dívidas](https://blog.assertivasolucoes.com.br/horario-para-cobranca-de-dividas/) · [Lei n.º 14.181/2021 (texto)](https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14181.htm) · [Art. 54-A a 54-G CDC comentado](https://www.aurum.com.br/blog/cdc-comentado/art-54-a-a-54-g-cdc/)

---

## 9. ¿Hace falta CNPJ / entidad local para vender en Brasil?

- La LGPD **no exige explícitamente** (a diferencia del GDPR europeo, que sí
  obliga a un "representante" local) que un controlador/operador extranjero
  designe un representante en Brasil. En la práctica, empresas extranjeras
  igual designan un Encarregado o representante local accesible, como
  medida de compliance voluntaria pero recomendada.
- **Pero para operar comercialmente** (facturar, firmar contratos con
  bancos/fintechs brasileños, cobrar en reales, contratar gente) sí hace
  falta, en la práctica, un **CNPJ** — y para que una empresa extranjera
  obtenga uno debe registrar el capital extranjero ante el Banco Central en
  hasta 30 días desde su ingreso al país, y nombrar un **administrador/
  representante legal domiciliado en Brasil**.
- **A confirmar con el abogado/contador brasileño antes de facturar el
  primer contrato real**: si conviene constituir una sociedad brasileña
  (Ltda./S.A.) desde el inicio, o si alcanza (para un piloto chico) con
  facturar desde Uruguay y que el cliente brasileño pague por otro medio
  (hay implicancias fiscales — retenciones, IOF, notas fiscais — que
  exceden el alcance de esta guía y son terreno de un contador, no de esta
  documentación).
- La extraterritorialidad de la LGPD (Art. 3) igual aplica aunque no haya
  entidad brasileña: alcanza con que el tratamiento ocurra en Brasil, o que
  el titular de los datos esté en Brasil, o que se ofrezcan bienes/servicios
  a personas en Brasil — **Kobra queda sujeto a la LGPD por vender el
  servicio a un cliente brasileño, tenga o no CNPJ propio**.

**Fuentes**: [CNPJ para empresa estrangeira — Receita Federal](https://www.gov.br/receitafederal/pt-br/assuntos/orientacao-tributaria/cadastros/cnpj/solicitacao-de-atos-perante-o-cnpj-por-meio-da-internet/orientacoes-para-pessoa-juridica-domiciliada-no-exterior) · [Opinião: LGPD e a ausência da figura do representante — Conjur](https://www.conjur.com.br/2023-abr-01/opiniao-lgpd-ausencia-figura-representante/)

---

## 10. Checklist antes de vender/procesar una cartera real en Brasil

| # | Ítem a verificar | Estado hoy | Quién lo resuelve |
|---|---|---|---|
| 1 | ¿Vamos a facturar/contratar desde una entidad brasileña (CNPJ propio) o desde Uruguay? | Pendiente de decisión de negocio | Abogado + contador BR |
| 2 | Designar un **Encarregado de Dados** (DPO) para Brasil, con contacto público | No existe (solo referencia de Uruguay en `PLANTILLA_DPA.md`) | Interno + abogado |
| 3 | Redactar una **versión LGPD del DPA** (no reusar `PLANTILLA_DPA.md` de Uruguay tal cual): base legal Art. 7 IX/X, derechos Art. 18, plazo de incidente ajustado a 3 días hábiles ANPD, cláusula de transferencia internacional con CPCs de la ANPD (RTID) | Falta | Abogado |
| 4 | Confirmar mecanismo de **transferencia internacional** para Anthropic/OpenAI/Twilio/Meta bajo el Regulamento RTID (Resolução 19/2024) — ¿adoptar las cláusulas-padrão de la ANPD? | Falta | Abogado |
| 5 | Documentar un **LIA/Relatório de Impacto** para el uso de legítimo interés en cobranza y para el scoring (ProbPago/originação) | Falta | Interno + abogado |
| 6 | Definir el **procedimiento de revisión humana** de decisiones automatizadas (Art. 20) para ProbPago y originação, y dejarlo visible/accesible al titular | Falta (a nivel producto/contrato) | Producto + abogado |
| 7 | Confirmar **estado(s) (UF)** donde va a operar la cartera y verificar leyes estaduales de horario de cobranza (San Pablo confirmado; revisar otros estados) | Falta | Abogado |
| 8 | Evaluar ajuste de `PoliticaContacto` para permitir **horario distinto el sábado** (8–20 L–V, 8–14 sáb.) — no es urgente para un piloto en un solo estado, sí antes de escalar | Gap de producto anotado, no resuelto | Ingeniería (fuera del alcance de esta guía) |
| 9 | Registrar el **canal de comunicación con titulares** en portugués (para ejercer derechos del Art. 18) | Falta | Interno |
| 10 | Confirmar si el cliente brasileño (banco/fintech) exige requisitos contractuales propios de residencia de datos o seguridad más allá de la LGPD (frecuente en contratos con instituciones reguladas por el BACEN) | A confirmar caso por caso | Abogado + cliente |
| 11 | Plan de respuesta a incidentes ajustado al plazo de **3 días hábiles** ante la ANPD | Falta (hoy el DPA de Uruguay habla de 48–72h) | Interno + abogado |

---

## Resumen para no perderse

- **La LGPD no se "activa" por tener CNPJ en Brasil** — se activa por
  procesar datos de personas en Brasil u ofrecerles el servicio. Ya aplica
  desde el primer cliente brasileño, tenga o no Kobra entidad local.
- **El mayor riesgo específico de este producto** no es la cobranza en sí
  (eso ya está resuelto conceptualmente por `PoliticaContacto`, solo falta
  afinarlo), sino el **Art. 20 sobre decisiones automatizadas de crédito** —
  porque ProbPago y originação son exactamente el caso de uso que ese
  artículo nombra explícitamente.
- **El DPA de Uruguay no es reusable tal cual** — la cláusula de
  transferencia internacional y el plazo de incidentes necesitan una versión
  específica para Brasil.
- Nada de esto reemplaza a un abogado brasileño: esta guía sirve para llegar
  a esa conversación con las preguntas correctas, no para saltarla.
