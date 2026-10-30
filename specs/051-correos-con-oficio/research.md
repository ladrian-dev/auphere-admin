# Investigación: Correos con oficio

Decisiones técnicas del plan, cada una con su alternativa descartada. Las decisiones del owner (D1–D4 de la nota de KB) no se rediscuten aquí: se aplican.

## R1 — Cómo se envía una plantilla de Resend

**Leído el 2026-10-30** en `resend.com/docs/api-reference/emails/send-email` y `…/dashboard/templates/template-variables`:

- `POST /emails` con `template: {id, variables}`. `id` acepta el **alias** de la plantilla.
- Solo plantillas **publicadas**. Con plantilla, el cuerpo **no admite** `html`, `text` ni `react` (error de validación).
- `from`, `subject` y `reply_to` del envío **pisan** los de la plantilla.
- Variables `string` (≤ 2 000 caracteres) o `number` (≤ 2^53−1), ≤ 50 por plantilla, claves `[A-Za-z0-9_]{1,50}`. Reservadas: `FIRST_NAME`, `LAST_NAME`, `EMAIL`, `UNSUBSCRIBE_URL`, `contact`, `this`.
- Una variable sin valor y sin valor por defecto hace que el envío falle con error de validación.
- **Sin bucles ni condicionales.**
- `tags` (`name`/`value`, ASCII, ≤ 256) e `Idempotency-Key` (24 h) disponibles.

**Decisión**: el código envía por **alias** (`auphere-<tipo>-<idioma>`), no por id. Un alias es estable entre cuentas y se lee en un registro; un id es opaco y cambia si se recrea la plantilla.

## R2 — El asunto vive en el código

**Decisión**: cada tipo de correo construye su asunto en el código y lo manda en el envío, que pisa el de la plantilla. La plantilla guarda el mismo asunto como valor por defecto, para que la previsualización del panel de Resend tenga sentido.

**Por qué**: el asunto lleva datos (el mes de un recibo, el nombre del partner) y tiene reglas comprobables (R4.1: ≤ 60 caracteres, sin núcleo genérico). En el código se prueba con una prueba unitaria, aparece entero en el registro de staging (R1.1) y no depende de si Resend interpola variables en el asunto por defecto, que la documentación no aclara.

**Descartado**: el asunto solo en Resend. El texto de staging diría `subject: null` y la regla de longitud solo se comprobaría contra la cuenta, no en CI.

## R3 — Escapado: el código escapa siempre

La documentación usa exclusivamente `{{{VAR}}}`, que en la familia Mustache significa **inserción sin escapar**, y no menciona el escapado en ningún sitio.

**Decisión**: el código aplica `html.escape(valor, quote=True)` a **toda** variable de tipo cadena antes de enviarla, venga o no de un usuario. Un enlace escapado (`&amp;` en una URL) sigue siendo HTML válido dentro de `href`. Escapar todo evita tener que decidir variable a variable cuál es «de usuario», que es justo el tipo de decisión que se olvida en el tipo dieciséis.

**Riesgo declarado**: si Resend sí escapa, un `&` saldría como `&amp;` visible, y el `<br>` de las variables de líneas (R8) se vería como texto. Se comprueba con un envío por plantilla a `delivered@resend.dev`, la dirección de pruebas de Resend, que no llega a ninguna persona, y leyendo el HTML entregado con `get-email`. Esa comprobación necesita el OK del owner (es un envío desde su cuenta) y queda como tarea de cierre.

## R4 — Modo de entrega por entorno

**Decisión**: un ajuste `email_delivery` con cuatro valores: `auto` (por defecto), `resend` (todo sale), `access` (solo salen los correos de acceso) y `log` (no sale nada).

| Entorno | `auto` resuelve a | Se puede forzar |
|---|---|---|
| producción | `resend` | `log` o `access` → **la API y el worker no arrancan** (R1.3) |
| staging | `access` | `resend` → todo sale y el arranque lo avisa (R1.4) · `log` → nada sale |
| dev / ci | `log` | `resend` o `access` → solo con una clave real |

**Los correos de acceso** son los seis que alguien necesita para seguir: confirmar el alta, «ya tienes cuenta», las dos invitaciones, restablecer la contraseña y el aviso de contraseña cambiada. Cada ficha del catálogo lo dice (`EmailSpec.access`). Todos los provoca una persona, a propósito y para sí misma o para alguien a quien invita. Los demás son automáticos (crons, umbrales, avisos), y son los que escribirían a un cliente real sin que nadie lo pidiera. **Segunda revisión del owner del 2026-10-30**: en la primera versión staging no enviaba nada y los enlaces se sacaban del registro.

Cuando un correo se retiene, el envío **devuelve `True`**: para quien llamó, el correo salió (R1.2). Las comprobaciones que hoy usan `settings.email_enabled` para distinguir «no hay proveedor» de «el proveedor rechazó» (`api/console/signup.py`) pasan a preguntar si el modo es de envío real.

**Por qué un ajuste y no tocar el secreto de staging**: quitar `NEXUS_RESEND_API_KEY` del secreto de staging apagaría el envío, pero en silencio y por accidente. El día que alguien la vuelva a poner por otra razón, staging vuelve a escribir a clientes. El modo por entorno lo convierte en una decisión escrita, con prueba.

**El repliegue SMTP (spec 011, D-4) se retira.** Mandaba a Mailhog el HTML escrito en el código, y ese HTML deja de existir: el cuerpo vive en Resend. El circuito local de CE-006 sigue siendo posible, porque en modo `log` el enlace de restablecimiento sale en el registro de la API. `smtp_url`, `_smtp_send` y el servicio `mailhog` de `docker-compose.yml` se van en este cambio.

## R5 — El registro en modo `log`

Un evento `email.suppressed` por correo, con:

- `kind`: el tipo del catálogo;
- `template`: el alias;
- `to`: los destinatarios;
- `subject`: el asunto ya construido;
- `links`: un diccionario con **solo** las variables que el catálogo marca como enlaces de acción;
- `partner_id` y/o `client_id` cuando el tipo pertenece a un negocio; `owner="none"` cuando no.

**Las demás variables no se registran.** El texto de una consulta de soporte, un nombre o un importe no hacen falta para completar un flujo, y registrarlos mete datos personales en CloudWatch sin propósito.

**Enmienda a la spec 011**: `docs/recuperar-la-contrasena.md` §6 descartó escribir el enlace en los registros «porque es cómo un secreto acaba en producción». La decisión D2 del owner lo permite en staging, y la guardia de arranque de R1.3 es la que impide que llegue a producción. Se actualiza el documento en el mismo cambio.

En modo `resend`, el evento sigue siendo `email.sent` (o `email.send_failed`), con `kind`, `template`, `to`, `subject`, el negocio y el `id` que devuelve Resend, **sin** `links` (R1.5).

## R6 — Catálogo en el código, cuerpo en Resend

**Decisión**: un módulo `nexus_api/services/email_catalog.py` con un `StrEnum` de tipos y, por tipo, una ficha inmutable:

- `aliases`: `{"es": "nexus-<tipo>-es"}` y, si el tipo respeta el idioma, también `"en"`;
- `sender`: `billing` o `notifications`;
- `variables`: las claves que el código envía;
- `link_variables`: el subconjunto que son enlaces de acción (se registran en staging);
- `owner`: `partner`, `client` o `none`;
- `links_allowed`: `False` solo para el aviso de contraseña cambiada (R6.1).

Cada sitio que hoy compone HTML pasa a construir su asunto y sus variables y llama a `send_template(kind, …)`. `send_email` desaparece: con eso, la prueba de barrido (CE-003) es simple. No queda ninguna función que acepte HTML.

**Descartado**: copiar el HTML de cada plantilla en el repositorio y sincronizarlo con un script. Contradice D1 (el texto se edita en el panel de Resend) y crea dos fuentes del mismo texto, que es cómo empiezan a divergir.

## R6 bis — Tres plantillas genéricas, y por qué no veinticinco

Los avisos de la consola al partner son veinticinco tipos que pueden salir por correo (con `client.out_of_quota` y `template.rejected`), y los del cliente seis más. Cada uno tiene ya su frase en la campana (`apps/console/src/i18n/lanes/notices.ts` y `messages.ts`). Una plantilla por tipo serían treinta plantillas casi idénticas, en un panel donde un cambio de forma habría que repetirlo treinta veces.

**Decisión**: `partner_notice`, `client_notice` e `internal_alert` son genéricas. La plantilla pone la forma (logo, titular, mensaje, botón, pie) y el texto de cada tipo va en una tabla del código, probada: cada tipo emitible tiene fila, cada fila cumple las reglas de asunto (R4.1) y no contiene la lista de `contracts/redaccion.md`.

**Lo que sí tiene plantilla propia** son los correos con forma o peso propios: invitaciones, alta, contraseña, recibo, cobro, saldo y consumo, bandeja y escalado. Ahí está el texto que más se lee, y ahí es donde editarlo en Resend sin desplegar tiene sentido.

**Coste reconocido**: el texto de los avisos genéricos vive en el código, no en Resend. Es la excepción a D1, y se dice en la spec (R2.5).

## R7 — La comprobación de plantillas

`apps/api/scripts/check_email_templates.py`, con `NEXUS_RESEND_API_KEY` en el entorno:

1. por cada alias del catálogo, `GET /templates/{alias}`;
2. falla si no existe, si no está publicada o si sus variables no son **exactamente** las del catálogo;
3. sobre el HTML publicado: falla si falta «El equipo de Auphere», si aparece una cadena de la lista de `contracts/redaccion.md`, si hay más de un botón de llamada a la acción o, en `links_allowed=False`, si hay un `href` que no sea `mailto:`.

Se ejecuta a mano antes de pasar a producción y su salida se guarda en `evidence/`. No va en CI: CI no tiene la clave de Resend, y no debe tenerla.

## R8 — Listas de longitud variable

Las plantillas no tienen bucles. Los tres sitios que hoy pintan una lista (los conceptos del recibo, lo comprobado en una consulta de soporte, los canales de la conciliación con Meta) la pasan como **una variable de líneas**:

- cada línea se escapa por separado y se unen con `<br>`: es el **único** marcado que el código pone en una variable, y lo pone después de escapar, así que ningún valor de usuario puede abrir una etiqueta;
- se añaden líneas mientras quepan en 2 000 caracteres; si no caben todas, la última dice «y N conceptos más» y el detalle completo queda a un clic (`/billing` en el recibo);
- las alertas de saldo con varios clientes dan el **número** de clientes afectados, no la lista: es lo que ya hacen hoy.

**Descartado**: una tabla HTML de filas construida por el código. Una tabla necesita estilos en línea en cada celda, rompe el tope de 2 000 caracteres con una docena de conceptos y devuelve al código el maquetado que esta spec retira. Una línea por concepto se lee igual de bien en un móvil.

**Descartado también**: quitar los conceptos del recibo y dejar solo el total. Un recibo que no dice de qué es el importe obliga a abrir la consola para algo que cabe en el correo.

## R9 — Remitentes

| Ajuste | Hoy | Después |
|---|---|---|
| `receipt_from_email` | `Auphere <facturacion@auphere.com>` | `Auphere <billing@auphere.com>`: recibos y avisos de cobro |
| `signup_from_email` | `Auphere <no-reply@auphere.com>` | se renombra a `notifications_from_email`: `Auphere <notifications@auphere.com>` |

**Las direcciones van en inglés** (revisión del owner del 2026-10-30): `billing@`, `notifications@` y `support@`. `contacto@auphere.com` no cambia.
| — (nuevo) | — | `email_reply_to`: `support@auphere.com` |

**Por qué fuera de «no-reply»**: con `reply_to` a soporte (D3), un remitente que dice «no responder» se contradice. El dominio está verificado entero en Resend, así que no hace falta verificar el remitente nuevo.

Ya no hay un remitente por defecto implícito: cada tipo del catálogo declara el suyo. Era justo el defecto que la spec 006 encontró (el alta salía de facturación por herencia).

## R10 — Marca en el correo

- **Plantillas en HTML de correo, no en el editor visual.** Se intentó primero con el editor visual de Resend (TipTap), para que se pudieran editar arrastrando bloques. **No se puede publicar por API**: Resend responde `422 Template content has not been rendered to HTML yet` hasta que alguien abre cada plantilla en el panel. Con 39 plantillas, eso es un paso manual por plantilla y un riesgo de que una quede sin publicar. El HTML de correo se publica por API y se comprueba (R7). Se sigue editando en el panel de Resend, como código. Además controla lo que el editor no deja: tablas para Outlook, tipografía y el texto oculto de previsualización.
- **Tipografía**: `'Helvetica Neue', Helvetica, Arial, sans-serif`. Helvena, la de marca, no está en los clientes de correo; la familia Helvetica es la más cercana.
- **Tema global**: cuerpo `#F1F7F6` (hueso), contenedor `#FFFFFF` a 600 px con borde 1 px `#E4ECEA` y radio 8 px, texto `#0D0F01` a 15 px y 160 %, enlaces `#03624C`, botón `#00DF81` con texto `#0D0F01`, radio 4 px y relleno 12/20.
- **Logo**: `https://www.auphere.com/brand/auphere-logo.png` (1512×391), a 132 px de ancho, sin enlace.
- **Saludo y firma**: «Hola,» al empezar; «Un saludo, / El equipo de Auphere» al cerrar. En inglés, «Hi,» y «Best regards, / The Auphere team».
- **Pie**: línea fina y «Auphere · auphere.com», en verde pino `#0B453A` a 12 px. **Sin línea de «por qué lo recibes»** (revisión del owner). El aviso de contraseña cambiada no lleva el enlace a `auphere.com`.
- **Sin** gradientes, sombras, emojis ni imágenes que contengan texto.
- **Correos internos** (alertas de operador y plataforma): mismo tema, sin botón grande si no hay una acción; la cabecera dice «Aviso interno».

Los pares de color son los validados en `brand-system.md` (`--ink` sobre `--bone`: AAA; `--rich-black` sobre `--caribbean-green`: AAA; `--bangladesh-green` sobre `--bone`: AA).

## R11 — El idioma de cada correo

Revisión del owner: cada correo sale en el idioma de la cuenta de quien lo recibe, cuando se sabe.

- **Dónde está el idioma**: `console_auth.principals.locale`, el de la cuenta de consola. Lo tienen las personas de partners y las de clientes.
- **Cómo se resuelve**: `send_localized` busca la cuenta de cada destinatario por su correo, agrupa por idioma y envía una vez por grupo. Una dirección sin cuenta (la de facturación de un partner, por ejemplo) sale en español.
- **Cuándo no hace falta buscar**: si el idioma ya se sabe —la cuenta en el aviso de contraseña, la petición en el alta—, quien llama lo pasa y no se consulta nada.
- **La regla** es la de la spec 011: inglés solo si la cuenta lo dice; cualquier otra cosa, español. El alta hacía lo contrario (todo lo que no fuera `es` salía en inglés) y se iguala.
- **La consulta va en su propia sesión de plataforma**, porque quien envía puede estar dentro de una transacción de tenant que no ve `console_auth`. Si falla, el correo sale en español en vez de no salir.
