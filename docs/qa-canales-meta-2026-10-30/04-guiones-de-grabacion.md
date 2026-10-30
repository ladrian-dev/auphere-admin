# Guiones de grabación para la revisión de Meta (provisionales)

Fecha: 2026-10-30. Son **provisionales**: ninguno se ha ensayado de principio a fin, porque ningún flujo está verificado E2E en staging (ver `01-matriz-de-pruebas.md`).

Los textos de la interfaz salen de la consola de staging leída el 2026-10-30, en español. Para grabar hay que poner la consola en inglés y usar las etiquetas en inglés equivalentes.

## Reglas comunes

- **Entorno.** Las instrucciones del revisor (`specs/049…/app-review-reviewer-setup.md`) se montaron en **producción** por decisión del owner. Este QA trabaja solo contra staging. Antes de grabar hay que decidir dónde se graba (ver checklist C-01).
- **Datos.** Solo cuentas y activos de prueba: el cliente «Meta Review Demo» y un catálogo de demo con los productos de `catalog-demo-images/`.
- **Qué no debe salir en pantalla:**
  - números de teléfono reales;
  - el correo personal del owner;
  - tokens `EAA…`, el `code` de OAuth y `paging.next`;
  - las DevTools.
- **Antes de grabar:**
  - cerrar las notificaciones del sistema;
  - usar una ventana privada;
  - poner la interfaz de Meta en inglés.
- **Rótulos.** Cada escena lleva un rótulo en inglés (columna «Rótulo»). Sin audio.

---

## V-WA-1 · WhatsApp: conectar un número y responder

| Campo | Valor |
|---|---|
| Permisos | `whatsapp_business_management`, `whatsapp_business_messaging` (acceso existente; Meta lo vuelve a mirar) |
| Objetivo | Mostrar que el negocio conecta su número por Embedded Signup y que el asistente responde |
| Precondiciones | WA-01…WA-08 en PASS. Cliente de demo sin número. Número dedicado que no esté en la app WhatsApp Business (Cloud API). Teléfono de prueba para escribir |
| Activos | Portfolio de prueba, número dedicado, cliente «Meta Review Demo» |

| # | Pantalla de inicio | Acción | Qué debe verse | Evidencia que aporta | Rótulo (EN) | Precaución |
|---|---|---|---|---|---|---|
| 1 | `/login`, sesión cerrada | Entrar como revisor | Panel del partner | Acceso al producto | «The partner signs in to the Auphere console» | Ocultar el campo de contraseña |
| 2 | Clients → Meta Review Demo → agente → Channels | Elegir WhatsApp → Connect | Diálogo «Connect WhatsApp» con Coexistence y Cloud API | Inicio del flujo | «The business chooses how to connect its number» | — |
| 3 | Diálogo | Elegir Cloud API → Connect | Ventana de Meta (Embedded Signup) | Botón de login de Meta y pantalla de permisos | «Meta's Embedded Signup opens» | No enseñar el SMS de verificación con el número completo |
| 4 | Ventana de Meta | Elegir portfolio, WABA y número; aceptar | Pantalla de permisos con WhatsApp | Concesión de los dos permisos | «The owner grants WhatsApp permissions» | — |
| 5 | Consola | Volver | Tarjeta del número: conectado; paso 3 «Configure the channel» | Persistencia de la conexión | «The number is now connected» | Difuminar el número si no es de demo |
| 6 | Página del canal | Audiencia «Only my team» con el teléfono de prueba | Guardado | Configuración | «The team decides who the assistant answers» | Teléfono de prueba difuminado |
| 7 | Teléfono de prueba | Escribir «Hi, what time do you open?» | Respuesta del asistente en WhatsApp | Mensajería real | «A customer writes and the assistant replies» | Grabar el móvil con número oculto |
| 8 | Consola → Conversations | Abrir la conversación | Mensaje entrante y respuesta; botón para tomar el control | Bandeja y traspaso a persona | «The team sees the conversation and can take over» | — |

---

## V-CAT-1 · Catálogo en el número de WhatsApp

| Campo | Valor |
|---|---|
| Permisos | `catalog_management`, `business_management` |
| Objetivo | Listar los catálogos del negocio, enlazar uno y que el asistente responda con una tarjeta de producto |
| Precondiciones | **No grabar hasta cerrar INC-01 e INC-02.** El número tiene que estar conectado por **Cloud API** (en coexistencia no hay lista). El catálogo de demo, con 3 a 5 productos, tiene que pertenecer al portfolio del cliente y estar compartido con la integración (INC-04) |
| Activos | Catálogo «Auphere Demo Catalog», productos ficticios |

| # | Pantalla | Acción | Qué debe verse | Evidencia | Rótulo (EN) | Precaución |
|---|---|---|---|---|---|---|
| 1 | Página del número | Línea Catalogue = «None» → «Connect a catalogue» | «Asking Meta for the catalogues…» y la lista con el número de productos | `business_management` + `catalog_management` (lectura) | «Auphere lists the business's own catalogues» | Que no aparezcan catálogos de otros negocios |
| 2 | Selector | Elegir «Auphere Demo Catalog» | La tarjeta dice «Catalogue Auphere Demo Catalog» | Enlace por API (`POST /{waba}/product_catalogs`) | «The owner links one catalogue to the number» | — |
| 3 | Teléfono de prueba | «Do you have a classic burger?» | Tarjeta de producto nativa de WhatsApp | Lectura de productos y mensaje `product` | «The assistant answers with a native product card» | — |
| 4 | Consola | Conversación | El turno con la tarjeta | Trazabilidad | «The team sees what was sent» | — |
| — | — | **No grabar** «Disconnect» ni «Change» | — | Ver INC-01: Meta no tiene DELETE en ese edge | — | Quitar el paso 1f de las instrucciones del revisor hasta que esté arreglado |

---

## V-IG-1 · Instagram: conectar la cuenta (`instagram_basic`)

| Campo | Valor |
|---|---|
| Objetivo | Login unificado, elegir la cuenta profesional y ver el usuario y la foto en la tarjeta |
| Precondiciones | INC-03 resuelta (staging recibe eventos o se graba en el entorno que sí los recibe). Partner con `instagram` en `beta_channels`. Cuenta profesional real dentro de un portfolio, con «Allow access to messages» activado y rol de evaluador de Instagram. IG-01…IG-04 en PASS |

| # | Pantalla | Acción | Qué debe verse | Evidencia | Rótulo (EN) |
|---|---|---|---|---|---|
| 1 | Agente → Channels | Instagram → Connect | Ventana de Meta (configuración Instagram `1157578836735566`) | Inicio del login | «The business connects its professional Instagram account» |
| 2 | Meta | Iniciar sesión con Instagram o Facebook y elegir la cuenta | Permisos `instagram_basic` y `instagram_manage_messages` visibles | Concesión | «The owner grants access» |
| 3 | Consola | Volver | Tarjeta con @usuario y foto | Uso de `instagram_basic` | «Auphere shows which account is connected» |

## V-IG-2 · Instagram: mensajes directos (`instagram_manage_messages`)

| # | Pantalla | Acción | Qué debe verse | Evidencia | Rótulo (EN) |
|---|---|---|---|---|---|
| 1 | App de Instagram, cuenta personal de prueba | DM «Hi, what time do you open?» | — | Entrada real | «A customer sends a DM» |
| 2 | Consola → Conversations | Abrir | Mensaje con la etiqueta Instagram | Webhook recibido y asociado al cliente correcto | «It arrives in the Auphere inbox» |
| 3 | App de Instagram | Ver el DM | La respuesta del asistente | `POST /{IG_ID}/messages` | «The assistant's reply is delivered in Instagram» |

## V-IG-3 · Instagram: comentarios (`instagram_manage_comments`)

| # | Pantalla | Acción | Qué debe verse | Evidencia | Rótulo (EN) |
|---|---|---|---|---|---|
| 1 | Publicación de la cuenta de prueba | La cuenta personal comenta «Price?» | — | — | «A customer comments on a post» |
| 2 | Consola | Bandeja | El comentario | Webhook `comments` | «The comment reaches Auphere» |
| 3 | Instagram | Ver el post y los DM | Respuesta pública bajo el comentario y respuesta privada en los DM | `/{comment-id}/replies` y `recipient.comment_id` | «Public reply and one private reply» |

## V-HA-1 · Human Agent (Instagram y Messenger)

**No grabar hasta confirmar** que `HUMAN_AGENT` funciona con el login unificado (auditoría §3.5).

| # | Pantalla | Acción | Qué debe verse | Rótulo (EN) |
|---|---|---|---|---|
| 1 | Conversación con el último mensaje del cliente hace más de 24 h | Mirar el estado | El asistente no puede responder y la consola da un motivo claro | «After 24 h the assistant stops» |
| 2 | Misma conversación | Una persona pulsa «Take over» y escribe | Entrega con la etiqueta de agente humano | «Only a named team member can reply, up to 7 days» |
| 3 | Auditoría | Ver la fila | Quién tomó el control | «Every takeover is logged» |

Hay que preparar una conversación de más de 24 h con antelación: esperar un día real, porque no se puede falsear la ventana.

## V-MS-1 / V-MS-2 · Messenger

- **V-MS-1** (`pages_show_list`, `pages_manage_metadata`, `pages_read_engagement`):
  1. Connect Messenger.
  2. Elegir la Página en la lista de Meta.
  3. Ver la tarjeta con el nombre y la foto de la Página.
  4. Desconectar.
  5. Mensaje desde Messenger: ya no llega a Auphere.
- **V-MS-2** (`pages_messaging`): un evaluador escribe a la Página, el mensaje aparece en la bandeja con la etiqueta Messenger y la respuesta llega a Messenger.
- **Precondiciones** propias de la lista de revisión de Messenger (según auditoría 2026-10-29):
  - la Página está publicada;
  - `messaging_policy_enforcement` está suscrito;
  - `pages_read_engagement` está en la configuración «Auphere Messenger» (T050).
