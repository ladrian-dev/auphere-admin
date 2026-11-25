# Investigación: Editar plantillas de WhatsApp (075)

Fecha: 2026-11-23 · `develop` en bfe97215.

## R1 — Cómo se edita en Meta

- **Decisión**: `POST /{template_id}` con `components` y, si cambia, `category`, y `parameter_format` cuando las variables son con nombre. Es lo mismo que manda `create_template`, sin `name` ni `language`. Va con el token del cliente que ya se usa para crear y borrar.
- **Por qué**: es la única vía que documenta Meta. La referencia de Graph (v27) acepta `category`, `components`, `message_send_ttl_seconds`, `parameter_format` y `product_set_id`. La respuesta documentada es `{"success": true}`, sin el estado nuevo. Por eso, después de editar, se vuelve a leer la plantilla de Meta sin caché (R6).
- **Alternativas**: borrar y crear otra. Se descarta porque Meta bloquea el nombre de una aprobada borrada durante 30 días.

## R2 — Lo que se comprobó en Meta el 2026-11-23

Cuenta de pruebas de Meta (`Test WhatsApp Business Account`), plantilla desechable `nexus_prueba_edicion_075` (UTILITY, `es`).

| Comprobación | Resultado |
|---|---|
| Crear y aprobar | Pasó de «En revisión» a «Activa» en unos 17 minutos. |
| Editar una plantilla **en revisión** | WhatsApp Manager abre el editor con todos los campos desactivados, y «Eliminar plantilla» también. Coincide con la documentación y con 3.1. |
| Editar una **aprobada** | Se editan el cuerpo, la cabecera, el pie y los botones. El nombre y el idioma salen desactivados, y la categoría no se ofrece. Coincide con 1.3 y 2.3. |
| C1: estado de una aprobada justo después de editarla | La lista la pone **«En revisión»** al instante. |
| C1: ¿Meta sigue aceptando la versión anterior? | **No se probó.** Hacía falta un envío real y el owner decidió no hacerlo: «trata "en revisión" como no enviable». Auphere deja de mandarla hasta que vuelva a estar aprobada, como ya hace hoy. **No hace falta columna nueva ni cambios en las puertas de envío.** |
| C2: límite de ediciones | En la primera edición de una aprobada, Meta no enseña ningún aviso de límite. Qué error devuelve al pasarlo sigue sin verse. Una segunda edición en 24 horas lo diría, pero no hace falta: 2.4 enseña el motivo que dé Meta. |
| C3: estado de una rechazada tras editarla | No se forzó un rechazo. 1.4 y 6.1 enseñan el estado que devuelva Meta, sea cual sea. |
| Después de editar una aprobada | Meta la reaprobó sola en unos 20 minutos («Activa»). Una vez reaprobada, WhatsApp Manager seguía con el editor y «Eliminar plantilla» desactivados. Encaja con el límite de una edición cada 24 horas, pero Meta no lo dijo. Desde la lista, en cambio, sí se pudo borrar. |

La plantilla de prueba se borró el 2026-11-23, desde la lista. Meta avisa de que el nombre de una plantilla borrada no se puede reutilizar en 30 días (T030).

## R3 — Dónde vive la regla de «qué se puede editar» (9.3)

- **Decisión**: en la API, en un solo módulo de servicio (`services/whatsapp_template_edit.py`). La consola y el panel la consumen, y ninguno la reescribe. La API añade a cada fila de la lista tres campos:
  - `edit_blocker`: por qué no se puede editar, o `null`.
  - `draft`: el contenido ya separado en cabecera, cuerpo, pie, botones y ejemplos.
  - `version`: una huella del contenido actual.
- **Por qué**:
  - La spec pide que la consola y el panel decidan igual (9.3), y hoy la consola parte el contenido en TypeScript (`draftFromComponents`) mientras el panel no lo parte.
  - Con la regla en el servidor, la misma función decide en la lista y en el guardado. Así el guardado no puede aceptar lo que la lista no ofrece.
- **Alternativas**: llevar `template-rules.ts` a `@nexus/ui` y que lo usen las dos apps. Se descarta porque la API seguiría necesitando su propia copia para validar, y serían dos reglas.

## R4 — Qué hace bloqueante una plantilla (3.2)

- **Decisión**: se puede editar si todo lo que lleva es una de estas piezas:
  - cabecera `TEXT` sin variables;
  - `BODY`;
  - `FOOTER`;
  - `BUTTONS` con 3 botones o menos, de tipo `QUICK_REPLY`, `URL` sin variable o `PHONE_NUMBER`.

  Además, la categoría no puede ser `AUTHENTICATION` y el estado tiene que ser `APPROVED`, `REJECTED` o `PAUSED`. Lo demás da un código de bloqueo cerrado: `status`, `authentication`, `media_header`, `header_variable`, `unsupported_button`, `url_variable`, `too_many_buttons` y `unsupported_component`. Este último cubre carrusel, oferta limitada y lo que Meta añada mañana.
- **Por qué**:
  - Es exactamente lo que el editor de hoy sabe pintar (`TemplateCreateIn.to_components`).
  - La cabecera con variable y la URL con variable necesitan un ejemplo propio que el editor no recoge, y Meta rechaza la edición sin él.
  - La lista se escribe por lo que **sí** se admite. Lo nuevo queda bloqueado por defecto.
- **Alternativas**: reenviar tal cual las piezas desconocidas (D3). Se descarta para la multimedia porque su ejemplo en la lectura es un enlace, no el `header_handle` que Meta pide al escribir.

## R5 — Plantillas que Auphere manda por su nombre (requisito 4)

- **Decisión**: un registro único en `nexus_api.services.whatsapp_template_edit.SYSTEM_TEMPLATES`.
  - Reservas: sus seis nombres, con las variables de `reservations.templates.VARIABLES` en modo `exact`.
  - Cobros: `recordatorio_pago_proximo` y `recordatorio_pago_vencido`, con `{cliente, negocio, monto, fecha}` en modo `subset_keep`. Ninguna variable de fuera del conjunto, y ninguna de las que la versión actual lleva puede desaparecer.
  - Los nombres de cobros pasan a `nexus_api`, y `cobranza_reminder_cron` los importa de ahí (el worker ya importa `nexus_api`).
- **Por qué**: así la regla y lo que se manda salen del mismo sitio (043 15.8, y 9.3 aplicado a cobros).

## R6 — Lo que se escribe después de editar (requisito 6)

- **Decisión**:
  1. Antes de llamar a Meta se apunta `t0`.
  2. Tras su `success`, se vacía la caché de la cuenta y se vuelve a leer la plantilla de Meta.
  3. El espejo (`whatsapp_template_status`) se actualiza con `status` = el que devuelve esa lectura y `reason = NULL`, **solo si** `last_event_at` es nulo o anterior a `t0`. Si el aviso de Meta llegó antes, manda el aviso (6.3).
  4. La actualización filtra por la `waba_id` de las credenciales de la sesión (garantía 1).
- **Por qué**:
  - La consola lite de Reservas y la herramienta `notification.send_template` leen el espejo.
  - Cobros y el outbox de Reservas leen a Meta en vivo, con una caché de 30 s que se vacía.
  - Así las cuatro lecturas ven lo mismo en cuanto se guarda (6.1 y 6.2).

## R7 — Cambio ajeno mientras se edita (7.1)

- **Decisión**: `version` = los 16 primeros caracteres de un sha256 del JSON canónico de `{category, components}` tal como lo lista Meta. La lista lo da. El guardado lo devuelve, el servidor lo recalcula con una lectura sin caché y, si no coincide, contesta 409 `template_changed`.
- **Por qué**: Meta no tiene versión ni ETag en las plantillas. El contenido es lo único que distingue un cambio.

## R8 — Confirmaciones (2.2 y 5.1) y envíos en cola

- **Decisión**:
  - El guardado lleva `confirm: bool`. Puede que haga falta confirmar: la plantilla está aprobada (`approved`), o se quitan o renombran variables y hay envíos en cola de esa plantilla (`queued_sends`, con su número). En ese caso, sin `confirm`, el servidor contesta 409 `confirmation_required` con las razones, y no llama a Meta. La pantalla pinta el aviso con esas razones y reenvía con `confirm: true`.
  - Los envíos en cola se cuentan con los `messages` del cliente en `PENDING` cuyo `template_payload` tiene ese nombre e idioma. Se leen bajo su RLS.
- **Por qué**: el número de envíos en cola solo lo sabe el servidor. Dejarle a él la decisión de cuándo hay que confirmar evita que una pantalla se salte el aviso.

## R9 — Editor compartido entre la consola y el panel (9.2, D6)

- **Decisión**: el editor visual (`TemplateComposer`) pasa a `@nexus/ui` como `TemplateEditor`. Recibe sus textos por `labels`, como `catalog-browser`, y devuelve el borrador por `onSubmit`. Las dos apps ponen su acción de servidor y sus textos.
  - Las reglas puras de la pantalla (`template-rules.ts`: variables, límites y avisos al escribir) se mueven con él.
  - La consola mantiene su interfaz pública, para que sus pruebas sigan valiendo.
- **Por qué**: el panel ya depende de `@nexus/ui` (spec 031), y el owner pidió el mismo editor en los dos (D6). Copiarlo serían dos editores.
- **Alternativas**: copiar el componente al panel. Se descarta por la misma razón que R3.

## R10 — Rutas

- **Decisión**:
  - Consola: `PUT /console/clients/{ref}/channels/whatsapp/templates/{name}/{language}`.
  - Panel: `PUT /admin/tenants/{id}/whatsapp/templates/{name}/{language}`.
  - Las dos llevan el mismo cuerpo y las dos llaman a la misma función del servicio.
- **Por qué**: al contrario que borrar, editar va por nombre **e** idioma. `PUT` porque se sustituye el contenido entero, igual que en Meta. Las rutas nuevas de `/console/*` las cubre solo `tests/isolation/test_console_scope.py`.
