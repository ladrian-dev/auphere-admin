# Contrato: avisos al teléfono

Cubre R8, R9 y R10, y research §D5 a §D7.

**Son avisos normales.** El aviso viaja completo, con título y texto, y el
sistema del teléfono lo muestra tal cual. No hay extensión que pida el texto, ni
credencial aparte, ni tarea en segundo plano (decisión del owner del
2026-10-19).

## Tipos

| `kind` | Hecho | Quién lo recibe | iOS | Android (canal) |
|---|---|---|---|---|
| `inbox.waiting` | Una conversación pasa a esperar a una persona | Todos los teléfonos activos de las personas del cliente con el módulo Bandeja y el tipo activado | `time-sensitive` | `waiting_v1`, importancia alta |
| `inbox.message_for_you` | El contacto escribe en una conversación que atiende una persona | Solo los teléfonos de esa persona | `active` | `messages_v1`, importancia alta |
| `client.balance` | La campana del cliente recibe `client.balance_low` o `client.balance_out` | Los teléfonos con el tipo activado | `active` | `balance_v1`, importancia normal |

- **Los canales de Android** los crea la app al entrar, **antes** de pedir el
  destino, con su nombre en el idioma del teléfono.
- Llevan versión en el identificador porque, una vez creados, solo se puede
  cambiar el nombre y la descripción.
- La importancia la decide la persona en los ajustes del sistema (R8.9).

## Textos

Se componen en el servidor, en el `locale` del teléfono. Los dos idiomas viven
en `apps/api/src/nexus_api/services/push_texts.py`.

| `kind` | Título | Texto |
|---|---|---|
| `inbox.waiting` | «{contacto} espera a una persona» | El motivo del agente, recortado a 100 caracteres con «…» |
| `inbox.message_for_you` | «{contacto}» | El principio del mensaje, recortado a 100. Si es un archivo: «Foto» o «Documento» |
| `client.balance` | «Tu saldo se está agotando» o «Te quedaste sin saldo» | «Te alcanza para unos {n} días.», o a quién pedir saldo (`balance_contact`) |

**Nunca va:** el número de teléfono, el mensaje completo, el nombre o el
contenido de un archivo, las notas internas ni las etiquetas (R9.2). Si el
contacto no tiene nombre, se usa «Un contacto», nunca su número.

Un teléfono escrito **dentro** de un texto libre (el motivo del agente o el
mensaje del contacto, por ejemplo «llámame al 611 222 333») se tapa con «•••»
antes de salir. Un nombre de contacto que es un número cuenta como sin nombre.

## De dónde sale cada evento

Cada evento se escribe en `client_push_events`, **en la misma transacción** que
el hecho (R8.5).

| `kind` | Punto de enganche | `dedupe_key` |
|---|---|---|
| `inbox.waiting` | `inbox_lifecycle.mark_waiting`, en la transacción del escalado y solo si el cliente tiene Bandeja | `inbox.waiting:{conversation_event_id}` |
| `inbox.message_for_you` | `dispatcher._process_inbound_after_gates`, en el bloque transaccional (≈ línea 406), si `agent_active = false` y `assigned_user_id` no es nulo. Las burbujas plegadas producen un solo evento | `inbox.message:{inbound_message_id}` |
| `client.balance` | Justo después de un `emit()` de `client.balance_low` o `client.balance_out` que devolvió fila, en la misma sesión y con `SET LOCAL app.tenant_id` | `client.balance:{notification_id}` |

## El reparto, en el worker

La tarea nueva **`push-dispatcher`** es de la familia egress. Se despierta con
`pg_notify('nexus_push')` y con un tick de 1 s, y lee con
`FOR UPDATE SKIP LOCKED`. Por cada evento `pending`:

1. **Calcula los destinatarios en ese momento.** Descarta el destino de una
   fila si otra fila activa, de cualquier cliente, tiene el mismo destino
   registrado después; en ese caso pone a `NULL` el de la vieja. Un destino solo
   tiene un dueño. Cuentan los teléfonos activos;
   la membresía, el acceso y el módulo vigentes; y `notice_kinds`. Para
   `inbox.message_for_you`, el control tiene que seguir siendo de
   `target_principal_id` (R9.3).
2. **Compone el texto con los datos de ese momento.** Si otra persona ya tomó
   la conversación, `inbox.waiting` no se envía a nadie: el hecho ya no es
   cierto.
3. **Crea una `client_push_deliveries` por teléfono,** única por evento y
   teléfono. Los que no cumplen quedan en `skipped` con su razón.
4. **Envía** a APNs (HTTP/2 y token ES256) o a FCM HTTP v1.
5. **Si la respuesta es `Unregistered`, `BadDeviceToken` o `UNREGISTERED`,**
   pone `push_token = NULL` en el teléfono.
6. **Si el fallo es transitorio,** reintenta con espera creciente, como mucho 5
   veces por evento. Después lo marca `failed` y lo registra.

**Contrato del bootstrap.** La tarea se añade en tres sitios a la vez: la
llamada `_spawn`, `EGRESS_TASK_NAMES` y `ALL_EXPECTED` de
`test_bootstrap_split.py`.

## Payload

**APNs:**

```json
{"aps": {"alert": {"title": "Martín Ruiz espera a una persona",
                   "body": "Pide un reembolso por el pedido #4821."},
         "sound": "default", "badge": 3,
         "interruption-level": "time-sensitive",
         "category": "inbox_waiting",
         "thread-id": "<conversation_id>"},
 "url": "auphere-customers://inbox/<conversation_id>"}
```

- **Cabeceras:** `apns-push-type: alert`, `apns-priority: 10`, `apns-topic`
  con el bundle, y `apns-collapse-id` con `<conversation_id>`. Así los avisos
  de una conversación se reemplazan en vez de apilarse.
- **Placa:** `badge` es el número de conversaciones del cliente que esperan a
  una persona, el mismo `waiting` de `/inbox/counts`.
- **Pantalla bloqueada:** la categoría, que registra la app, lleva
  `hiddenPreviewsBodyPlaceholder` con el texto neutro del tipo. Es lo que el
  sistema enseña cuando el ajuste oculta las vistas previas (R8.10).

**FCM** (mensaje de aviso, lo muestra el sistema):

```json
{"message": {"token": "…",
  "notification": {"title": "…", "body": "…"},
  "android": {"priority": "high", "collapse_key": "<conversation_id>",
    "notification": {"channel_id": "waiting_v1", "tag": "<conversation_id>",
                     "visibility": "PRIVATE", "notification_count": 3}},
  "data": {"url": "auphere-customers://inbox/<conversation_id>"}}}
```

- **`visibility: PRIVATE`:** con el ajuste de ocultar contenido sensible, el
  sistema enseña el aviso sin su texto (R8.10).
- **`tag`:** una conversación ocupa un solo aviso.

## En el teléfono (`expo-notifications`)

- **Al entrar:**
  1. crea los canales de Android;
  2. registra las categorías de iOS (sin acciones, R8.12);
  3. pide permiso **después** de la pantalla propia (R10);
  4. registra el destino con `PUT /console/lite/phones/current/push`;
  5. lo vuelve a registrar si el sistema lo cambia.
- **Con la app en primer plano:** el manejador no muestra el aviso si la
  conversación del aviso está abierta (R8.7). En cualquier otro caso lo
  muestra como banner.
- **Al tocar el aviso:** se abre `url`, con la app abierta, cerrada o en
  segundo plano.
- **Placa:** la app la pone al día al volver al primer plano con el `waiting`
  de `/inbox/counts`, y la pone a cero si el cliente no tiene Bandeja.
- **Sin acciones:** el aviso no escribe nada (R8.12).
