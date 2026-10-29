# Borrador: datos de Meta y eliminación en la política de privacidad

> **Aplicado el 2026-10-29** en `auphere-agency` (`messages/{es,en}.json` → `s09`–`s11`, orden en `LegalArticle.tsx`, fecha propia de privacidad), sin la frase entre corchetes. Sin commit ni publicación. Decisiones del owner: el responsable **no cambia** (se mantiene como estaba, con la app bajo Facelad, para evitar restricciones); el plazo de **30 días** se mantiene y la spec 049 lo exige (Requisito 5.3 y 5.6).

Para `auphere-agency` (sitio `auphere.com`). Requisito de App Review de Meta: la política tiene que decir qué datos se reciben de WhatsApp, Instagram y Messenger, para qué, con quién se comparten y cómo pedir su eliminación. Hoy no lo dice (comprobado el 2026-10-29).

## Dónde va

- Textos: `messages/es.json` y `messages/en.json` → `legal.privacy.items.s09`, `s10`, `s11`.
- Orden: `src/components/sections/LegalArticle.tsx`, línea 5 → `privacy: ['s01', 's02', 's03', 's04', 's05', 's06', 's07', 's09', 's10', 's11', 's08']` (los cambios de la política siguen al final).
- Fecha: actualizar el texto `updated` de la página al día de publicación.
- Cada `body` es **un solo párrafo** (el componente pinta un `<p>`), por eso no hay listas.

## Antes de publicar, comprobar

1. **Responsable del tratamiento.** La política dice «Auphere Intelligence S.L.»; la app de Meta pertenece al negocio verificado **Facelad**. Meta compara la política con el negocio de la app: o la política nombra a Facelad (o la relación entre ambas), o se explica en las instrucciones al revisor.
2. **Proveedores de modelos de IA.** El texto dice que el contenido pasa por proveedores de modelos de IA como subencargados. Confirmar que los contratos de esos proveedores están en el anexo de subencargados (s05) y que no usan los datos para entrenar; si no se puede afirmar, quitar la frase entre corchetes.
3. **Plazo de 30 días** para borrar tras desconectar: es el mismo que la respuesta de s07. Confirmar que la operación lo cumple (hoy desconectar un canal conserva el historial: spec 049, R5.3). Si no, ajustar el plazo.

---

## Español

### s09 — Datos de WhatsApp, Instagram y Messenger

**title:** `Datos de WhatsApp, Instagram y Messenger`

**body:**

> Cuando un negocio conecta su número de WhatsApp, su cuenta profesional de Instagram o su página de Facebook a Auphere, recibimos de Meta solo lo necesario para que su agente atienda las conversaciones: el identificador y el nombre de perfil de quien escribe (en WhatsApp, también su número de teléfono), los mensajes, archivos y reacciones que envía, el estado de entrega y lectura, los comentarios y menciones en las publicaciones del negocio, y los datos de la cuenta conectada (identificadores, nombre, plantillas y catálogo de productos). Los usamos únicamente para responder en nombre de ese negocio, mostrarle sus conversaciones y cumplir las normas de Meta. No los vendemos, no los usamos para publicidad ni para crear perfiles, y no los cruzamos entre negocios. El negocio es el responsable de esos datos y Auphere los trata por su cuenta, de acuerdo con las Condiciones de la Plataforma de Meta.

### s10 — Con quién se comparten

**title:** `Con quién compartimos estos datos`

**body:**

> Con el negocio que conectó la cuenta, que ve sus conversaciones en la consola de Auphere. Con Meta, que es por donde viajan los mensajes. Con los proveedores que alojan el servicio y con los proveedores de modelos de IA que generan las respuestas del agente, que actúan como subencargados con contrato de tratamiento de datos [y sin derecho a usarlos para entrenar sus modelos]. Y con las autoridades, solo cuando la ley nos obliga. Los subencargados están listados en el anexo de cada contrato (ver «Dónde se alojan»).

### s11 — Cómo pedir que borremos tus datos

**title:** `Cómo pedir que borremos tus datos`

**body:**

> Si escribiste a un negocio por WhatsApp, Instagram o Messenger y quieres que borremos tus mensajes y datos de perfil, escríbenos a contacto@auphere.com con el asunto «Borrar mis datos», indicando el canal, el nombre del negocio y tu número o usuario. Lo confirmamos y lo borramos en un plazo máximo de 30 días, y avisamos al negocio, que es el responsable. Si eres un negocio, puedes desconectar el canal desde la consola o quitar el acceso de Auphere en la configuración de integraciones comerciales de Facebook o de apps y sitios web de Instagram; dejamos de recibir datos al instante, borramos los tokens de acceso y eliminamos o anonimizamos el resto en un plazo máximo de 30 días, salvo lo que la ley nos obligue a conservar.

---

## English

### s09 — WhatsApp, Instagram and Messenger data

**title:** `WhatsApp, Instagram and Messenger data`

**body:**

> When a business connects its WhatsApp number, its Instagram professional account or its Facebook Page to Auphere, we receive from Meta only what its agent needs to handle the conversations: the ID and profile name of the person writing (on WhatsApp, also their phone number), the messages, files and reactions they send, delivery and read status, comments and mentions on the business's posts, and data about the connected account (IDs, name, message templates and product catalog). We use it only to reply on behalf of that business, show the business its conversations and comply with Meta's rules. We do not sell it, use it for advertising or profiling, or combine it across businesses. The business is the controller of this data and Auphere processes it on its behalf, in line with the Meta Platform Terms.

### s10 — Who we share it with

**title:** `Who we share this data with`

**body:**

> With the business that connected the account, which sees its conversations in the Auphere console. With Meta, which carries the messages. With the providers that host the service and the AI model providers that generate the agent's replies, which act as sub-processors under a data processing agreement [and may not use the data to train their models]. And with authorities only when the law requires it. Sub-processors are listed in the annex of each contract (see "Where it is hosted").

### s11 — How to ask us to delete your data

**title:** `How to ask us to delete your data`

**body:**

> If you wrote to a business on WhatsApp, Instagram or Messenger and want us to delete your messages and profile data, email contacto@auphere.com with the subject "Delete my data", stating the channel, the business name and your number or username. We confirm and delete it within 30 days at most, and we let the business know, as it is the controller. If you are a business, you can disconnect the channel from the console or remove Auphere's access in Facebook's Business Integrations settings or Instagram's Apps and Websites settings; we stop receiving data immediately, delete the access tokens and delete or anonymise the rest within 30 days at most, except what the law requires us to keep.

---

## En el panel de Meta, después de publicar

- Configuración básica → **URL de instrucciones para la eliminación de datos**: apuntar al ancla de la sección s11 si el sitio la tiene (si no, dejar la URL de la política).
- Si más adelante se implementa la **URL de callback de eliminación** (Ajustes avanzados lo recomienda), añadir a s11 que se devuelve un código de confirmación.
