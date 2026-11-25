# Plan: clientes de solo envío, códigos por WhatsApp y membresía que corta

**Spec**: [spec.md](spec.md) · **Rama**: `077-otp-con-membresia` · **Base**: `develop` en `dcf5f8d5`

## Resumen técnico

Cinco piezas, cada una sobre algo que ya existe:

1. **Solo envío**: una marca `tenants.send_only` (apagada por defecto) que el panel lee para cambiar pestañas, cabecera y puesta en marcha, y que la conexión por enlace lee para dejar el número sin agente y como línea de avisos.
2. **Códigos**: un campo `code` en `POST /v1/messages/template` que solo vale con plantillas de categoría `AUTHENTICATION`; se encola con cuerpo posicional y el parámetro del botón, que el adaptador ya sabe enviar. Las plantillas de autenticación se crean con un constructor común para panel y consola.
3. **Claves por cliente**: un router de admin bajo `/admin/tenants/{id}/api-keys` y el arreglo de la rotación, que hoy pierde `tenant_id`.
4. **Membresía**: una tabla `service_memberships` (FORCE RLS por `tenant_id`), una puerta que la lee (API y despachador), el camino de Stripe (Checkout de suscripción con cliente propio, avisos por el pipeline que ya existe, lectura bajo demanda y cada hora) y el camino de la bolsa (un **cargo fijo mensual** genérico en el libro, cobrado por un cron).
5. **Panel y consola**: el asistente, la ficha, «Envío por API», Facturación, el diálogo de plantillas y una página pública de «Pago recibido».

## Constitution Check

| Principio | Cómo se cumple | Prueba |
|---|---|---|
| I. Aislamiento | `service_memberships` con FORCE RLS, política canónica y `GRANT` a `nexus_app`; la puerta lee bajo el `tenant_id` del contexto; el aviso de Stripe resuelve el cliente desde Stripe y lo compara con la fila; el cargo se escribe bajo `apply_partner_to_session` del partner del cliente; las claves rotadas conservan su cliente. | `tests/isolation/test_77_service_membership_scope.py` (nuevo), la rotación que conserva el cliente por los tres caminos también en `test_77`, `test_43` barre la tabla nueva sin cambios |
| II. Superficie | `0`. La página pública no lee ni escribe nada. | — |
| III. Dato, no instrucción | El cuerpo de un aviso de Stripe solo dice qué mirar; el estado se lee de Stripe (como hoy en `process_event`). El código del cliente se valida y solo viaja a Meta. | `test_service_memberships_stripe.py` |
| IV. Acción consecuente | Claves, membresía y marca de solo envío: `require_enabled_operator` en la API, `requireOperator` + `X-Operator-Id` en las Server Actions, `ConfirmDialog` en rotar, revocar, cancelar y cambiar la marca. Auditoría `operator:<email>`. | `test_admin_tenant_keys.py`, `test_admin_service_membership.py` |
| V. La pantalla no miente | Estados de la membresía tal cual (pendiente, activa, impagada, cancelada), última lectura de Stripe, caducidad del enlace; la puesta en marcha calcula cada paso en el servidor; sin membresía no hay paso ni etiqueta. | tests de componentes del panel |
| VI. Por API | Todo lo nuevo es API; el panel la llama. | — |
| VII. Test primero | Cada criterio EARS es un test que se ve en rojo antes del código (tasks.md). | — |
| VIII. Licencias | Ninguna dependencia nueva. | — |
| IX. KB | `[[clients/tecfin]]` enlaza a esta carpeta. | — |
| Medidor | No hay modelo ni herramienta de pago. El cargo fijo es un `debit` del cubo comprado con clave `fee:…`: cuenta como gasto del partner y la conciliación cuadra sin cambios. | `test_wallet_fixed_fee.py` |

## Diseño

### A. Datos (migración `0242_service_memberships`)

- `tenants.send_only boolean NOT NULL DEFAULT false`.
- `service_memberships`:

| Columna | Tipo | Notas |
|---|---|---|
| `id` | uuid PK | |
| `tenant_id` | uuid NOT NULL, FK `tenants(id)` ON DELETE CASCADE | una viva por cliente (índice único parcial `WHERE archived_at IS NULL`) |
| `archived_at`, `archived_by` | timestamptz NULL, text NULL | «Quitar membresía» archiva, nunca borra (constitución §IV) |
| `payer` | text CHECK IN (`stripe`, `partner_wallet`) | |
| `amount_cents` | int CHECK > 0 | USD |
| `pending_amount_cents` | int NULL | importe nuevo para el periodo siguiente (bolsa) |
| `status` | text CHECK IN (`pending`, `active`, `past_due`, `canceled`) | |
| `current_period_start`, `current_period_end` | timestamptz NULL | el periodo pagado |
| `next_period_start` | timestamptz NULL | bolsa: el periodo que toca cobrar, **guardado antes de cobrar** |
| `billing_email` | text NULL | Stripe |
| `stripe_customer_id`, `stripe_subscription_id` (UNIQUE), `stripe_checkout_session_id` | text NULL | |
| `checkout_url`, `checkout_expires_at` | text NULL, timestamptz NULL | el último enlace |
| `last_synced_at` | timestamptz NULL | última lectura de Stripe |
| `last_failure` | text NULL | p. ej. `card_declined`, `insufficient_balance` |
| `created_at`, `updated_at` | timestamptz | |

FORCE RLS con la política canónica de `0241`, `UNIQUE (tenant_id, id)` para FK compuestas futuras, `GRANT` a `nexus_app`.

El **cargo fijo** es un asiento de un tipo nuevo, `kind='fixed_fee'` (se amplía `ck_usage_ledger_kind` como hizo `0195`), `bucket='purchased'`, con `tenant_id` y clave `fee:{reason}:{tenant_id}:{period_start_iso}`. **No es `debit`**: los lectores de `debit` (consumo de conversaciones en `usage_lines`, gasto por agente y por día en `credit_burn*`, la ganancia de la spec 039) lo leerían como consumo del cliente, y la regla futura de consumo mínimo necesita un consumo que no incluya cuotas. Se suma como salida en `reconcile_purchased` y en `attention_live._outflow`, y el panel lo nombra en `lib/money.ts`. La clave única impide el doble cobro.

### B. Envío de códigos

- `schemas/messages.py`: `TemplateMessageIn.code: str | None` (máx. 15).
- `services/broadcasts.resolve_template(..., allow_authentication=False)`: con `True` y categoría `AUTHENTICATION`, acepta el `{{1}}` del cuerpo y devuelve `is_authentication=True` y si la plantilla lleva botón (tipo `OTP` o `URL`, Meta lo convierte en `URL`). Sin el flag, igual que hoy (las difusiones lo siguen rechazando).
- `services/direct_messages.send_template_message`: rama de autenticación. Valida el código (1–15 caracteres ASCII imprimibles sin espacios; sin `://`, `http` ni `www.`), rechaza `variables`, y guarda `template_payload = {name, language, category: "AUTHENTICATION", otp: true, params: {body: [code], buttons: [{sub_type: "url", parameters: [{type: "text", text: code}]}]}}`. Sin `code` y con plantilla de autenticación: 422 `code_required`. Con `code` y otra categoría: 422 `code_not_allowed`. El log dice `has_code` y nunca el código; la comprobación de colisión de claves compara solo la plantilla cuando es un código.
- Despachador (`streams/outbound.py`): al terminar un envío (`SENT` o `FAILED`) de una fila con `otp`, se sustituye el código por `"•"` en `template_payload`. Un fallo reintentable deja la fila `PENDING` con el código; el único camino que devuelve una fila `FAILED` a la cola es el reenvío por la API con la misma clave, y ese reescribe el payload con el código nuevo. El adaptador no cambia.
- Plantilla de autenticación leída de Meta: se aceptan las dos formas (cuerpo con `{{1}}`, o cuerpo sin texto con `add_security_recommendation`), con o sin `BUTTONS`; solo se manda el parámetro del botón si la plantilla tiene un botón `OTP` o `URL`. **Solo un envío real en staging confirma la forma que devuelve Meta.**

### C. Puerta de membresía

- `services/membership_gate.py` (sin importar nada de `billing`, porque lo importan el camino de envío y el despachador): `is_active(row, now)` (activa = `status == active` y, si es de bolsa, `current_period_end > now`) y `blocks_sending(session) -> bool` (lee la fila del tenant del contexto; sin fila, `False`).
- API: `api/messages.py` (antes de `send_template_message`) y `services/broadcasts.create_broadcast` → `402 membership_inactive`.
- Despachador: `_drain_tenant` lee `blocks_sending` una vez por lote; las filas con `template_payload` pasan a `FAILED`, `failure_code='membership_inactive'`. Las respuestas de un agente no tienen `template_payload` y no se tocan.
- La puerta no importa `nexus_api.billing` ni llama a Stripe.

### D. Membresía por Stripe

- `billing/checkout.py`: `open_tenant_membership_session(...)` → `mode=subscription`, `price_data` recurrente mensual en USD con `product_data.name`, `customer` propio, `metadata` y `subscription_data.metadata` con `kind=tenant_membership` y `tenant_id`, **sin** `client_reference_id` (lo leería `partner_id_from`). Devuelve url, id y `expires_at`. `ensure_tenant_customer(...)` crea el cliente de Stripe del tenant con clave de idempotencia por `tenant_id`.
- `success_url` = `{console_base_url}/pago-recibido`, `cancel_url` = `{console_base_url}/pago-recibido?estado=cancelado` (página pública de la consola).
- Avisos: `process_event.handle_entry` gana una rama al principio, **solo cuando el aviso no trae `partner_id`** (los de partners siempre lo traen, así que su camino no cambia): `checkout.session.completed`, `customer.subscription.updated|deleted`, `invoice.paid`, `invoice.payment_failed`. Lee el objeto de Stripe, saca la suscripción, comprueba `metadata.kind == tenant_membership` y aplica el estado bajo el `tenant_id` de la metadata, **solo si** la fila guarda esa suscripción (o, en `checkout.session.completed`, esa sesión). Si no lo es, sigue al camino de hoy (que lo marca huérfano).
- **El estado sale siempre de la suscripción leída en Stripe**, nunca del tipo de aviso: el aviso solo dice cuándo mirar. Así un aviso que llega desordenado, o un fallo seguido de un pago, deja el estado que Stripe tiene ahora. Mapa: `active|trialing` → `active`; `past_due|unpaid|paused` → `past_due` (Stripe pone `past_due` al primer cobro fallido de una renovación: es el corte que pidió Luis); `canceled|incomplete_expired` → `canceled`; `incomplete` → `pending`. Fin de periodo: `items.data[0].current_period_end`, o `current_period_end` en versiones viejas.
- `refresh_from_stripe(tenant_id)`: si no hay suscripción guardada, la busca por la sesión de pago guardada (`checkout.sessions.retrieve(...).subscription`). La usan el botón del panel y el cron, que relee cada hora las de Stripe `pending` con sesión, `past_due`, y `active` con el periodo vencido o sin leer desde hace 24 h.
- Un enlace nuevo **caduca el anterior** (`checkout.sessions.expire` si sigue abierto), para que no se puedan pagar dos.
- Cancelar: `subscriptions.cancel` y `status=canceled`.
- Cobros: `invoices.list(subscription=…)` → periodo, importe, estado, `hosted_invoice_url`.

### E. Membresía a la bolsa (cargo fijo genérico)

- `metering/wallet.py`: `charge_fixed_fee(*, partner_id, tenant_id, qty, reason, period_start) -> FixedFeeResult` (`charged | duplicate | insufficient`). Bloquea el monedero, mira la clave, exige `purchased_remaining + credit_limit >= qty`, escribe el asiento y descuenta. No toca el tope del cliente ni el cubo incluido. Sirve para cualquier `reason`.
- `services/service_memberships.charge_wallet_if_due(tenant_id, now)`:
  - **El periodo que toca se guarda antes de cobrar** (`next_period_start`, en su propia transacción): la primera vez es ahora; después, el `current_period_end` anterior. La clave sale de ese valor guardado, así que repetir tras una caída da `duplicate`, que se trata como pagado.
  - Se cobra desde una hora antes del vencimiento. Con éxito: `active`, periodo `[next_period_start, mismo día del mes siguiente)`. Sin saldo: `past_due` y `last_failure='insufficient_balance'`.
  - Al activar desde el panel se cobra en el acto.
  - Cancelar la corta en el acto (el periodo termina ahora); reactivarla con «Cobrar ahora» cobra un periodo nuevo desde ese momento.
- Cron `service-memberships-cron` (cada 5 min, en `SCHEDULER_TASK_NAMES`, `_spawn` y `test_bootstrap_split`): recorre los tenants activos y, bajo su contexto, cobra los de bolsa que toca y relee los de Stripe vencidos (máx. una vez por hora cada uno).

### F. API de admin

| Método y ruta | Qué hace |
|---|---|
| `PATCH /admin/tenants/{id}/send-only` | Marca o desmarca (operador, auditoría) |
| `GET /admin/tenants/{id}/send-readiness` | Pasos de la puesta en marcha con su estado |
| `GET /admin/tenants/{id}/template-messages?limit=50` | Últimos envíos de plantillas (destinatario enmascarado) |
| `GET/POST /admin/tenants/{id}/api-keys` | Lista y emite claves del cliente |
| `POST /admin/tenants/{id}/api-keys/{key_id}/rotate` · `/revoke` | Rota (conserva el cliente) y revoca |
| `GET/PUT /admin/tenants/{id}/membership` | Lee y configura |
| `POST /admin/tenants/{id}/membership/archive` | Quita la exigencia archivando la fila (solo si no está activa ni tiene suscripción viva) |
| `POST /admin/tenants/{id}/membership/checkout` | Enlace de pago de Stripe |
| `POST /admin/tenants/{id}/membership/refresh` | Relee Stripe |
| `POST /admin/tenants/{id}/membership/charge` | Cobra ahora a la bolsa |
| `POST /admin/tenants/{id}/membership/cancel` | Cancela |
| `GET /admin/tenants/{id}/membership/charges` | Cobros (Stripe o bolsa) |

`POST /admin/tenants` acepta `send_only`. `ApiKeyOut` gana `tenant_id`. La rotación de `admin/partners.py` copia `tenant_id`.

### G. Plantillas de autenticación

`services/whatsapp_templates.authentication_components(button_text, code_expiration_minutes, add_security_recommendation)`. El `TemplateCreateIn` de admin acepta `otp` y deja `components` opcional con `AUTHENTICATION`; el de la consola acepta `otp_button_text`, `otp_expiration_minutes` y `otp_security_recommendation` y no exige `body_text` con `AUTHENTICATION`.

> **Enmienda del 2026-11-25 (075, requisito 10).** Ya no hay dos `TemplateCreateIn`: el alta del panel recibe el de la consola, que vive en `nexus_api/schemas/whatsapp_templates.py`, y las dos rutas crean con la misma función (`services/whatsapp_templates.create_template`). `OtpTemplateIn` y la entrada `components` del panel desaparecen.

### H. Conexión por enlace

Dos capas, para que ningún camino de alta de número se escape:

- **En la puerta del entrante** (`nexus_worker/runtime/dispatcher.py`): un cliente con `send_only` trata cualquier número suyo como de solo envío (`send_only_channel`). Cubre el enlace, la conexión directa del operador, la consola y lo que venga.
- **En los datos, para que el panel no mienta**: los caminos que crean un número de WhatsApp (`nexus_channels/whatsapp_meta/signup.py::_upsert_channel` a través de quien lo llama en la API) dejan `config.agent_enabled = false` y `config.role = "notifications"` si el cliente es de solo envío. Marcar un cliente existente como de solo envío aplica lo mismo a sus números de WhatsApp.

### I. Panel (`apps/admin`)

- Asistente: tipo de cliente; partner opcional (como hoy: con partner va a su recibo, sin él es directo; se guarda con `PUT /billing`); membresía opcional con quién la paga (`PUT /membership`; «Del saldo del partner» solo aparece con partner).
- Ficha: pestañas y cabecera según `send_only`; Resumen con la puesta en marcha de solo envío; acción «Marcar como solo envío» en el menú.
- «Envío por API»: claves, cómo llamar, últimos envíos.
- Facturación: tarjeta de membresía (estado, quién paga, importe, enlace, actualizar, cobrar ahora, cancelar, quitar) y cobros; lo de hoy, igual. En pantalla, quien paga es «El cliente, con tarjeta» o «Del saldo del partner»: la palabra «bolsa» ya nombra la bolsa de cada cliente de la spec 047.
- Diálogo de plantillas: campos de autenticación. _(Desde el 2026-11-25, con el editor compartido de `@nexus/ui`; `otp-template.ts` y el formulario propio desaparecen.)_
- Conexión de canal de un cliente de solo envío: termina al conectar.

### J. Consola (`apps/console`)

- Página pública `/pago-recibido` (y `?estado=cancelado`), fuera del middleware de sesión.
- Formulario de plantillas: campos de autenticación, ES/EN. _(Desde el 2026-11-25, dentro del `TemplateEditor` compartido.)_

### K. Documentación

`docs/envio-directo.md` (nuevo), `docs/billing.md`, `docs/admin.md`, y el docstring de `seed_tenant_direct.py`.

## Riesgos

- **El webhook de producción** puede no estar suscrito a los avisos de suscripción. Paso del paso a `main`.
- **Avisos perdidos**: el webhook no reintenta. Lo cubre la relectura horaria y el botón.
- **El cargo a la bolsa** es la segunda resta del sistema: su único llamante es el worker y su clave es única por periodo.
