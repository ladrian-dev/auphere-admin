# Plan: Correos con oficio

**Rama**: `051-correos-con-oficio` · **Fecha**: 2026-10-30 · **Spec**: [spec.md](spec.md)

## Resumen

Todo correo de la plataforma pasa a ser un **tipo de un catálogo cerrado** que se envía con `send_template(tipo, …)` por una **plantilla publicada en Resend**. El cuerpo vive en Resend (D1); el asunto, las variables, el remitente y la respuesta, en el código. Desaparecen `send_email`, todo HTML escrito en el código y el repliegue SMTP.

El envío tiene un **modo por entorno**: producción envía y no puede dejar de hacerlo; staging, local y CI escriben un `email.suppressed` con los metadatos y los enlaces de acción, y no llaman a Resend.

Los 21 correos del inventario quedan en 20 plantillas: 19 en español y en inglés, y una interna solo en español. Son 39 alias, con el texto de `contracts/catalogo.md` y la guía de `contracts/redaccion.md`. Una comprobación contra la cuenta de Resend vigila que las plantillas y el código no se separen.

## Contexto técnico

| | |
|---|---|
| **Lenguaje** | Python 3.11 (API y worker); ningún cambio de TypeScript |
| **Dependencias** | Las que ya hay: `httpx`, `structlog`, `pydantic-settings`. **Ninguna nueva** |
| **Almacenamiento** | Ninguno. Ni migraciones ni tablas |
| **Pruebas** | `pytest` (unitarias, integración, aislamiento) y `respx` para el transporte HTTP |
| **Proveedor** | Resend, `POST /emails` con `template: {id: <alias>, variables}`; `GET /templates/{alias}` para la comprobación |
| **Restricciones** | Variables `string`/`number`, ≤ 50 por plantilla, cadenas ≤ 2 000 caracteres, sin bucles ni condicionales (R1 de `research.md`) |
| **Alcance** | 18 sitios que envían (API, worker y un script), 20 plantillas, 39 alias |

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | **Garantía 6**: todo `email.suppressed`, `email.sent` y `email.send_failed` lleva `partner_id` y/o `client_ref` cuando el tipo pertenece a un negocio, y `owner="none"` cuando no. Prueba de barrido `tests/isolation/test_55_email_owner_tagging.py`: recorre el código, encuentra cada llamada a `send_template` con un tipo de dueño `partner` o `client` y falla si no pasa el negocio. Además comprueba en ejecución que el evento lo lleva. **Garantía 1, solo rozada**: los destinatarios se siguen resolviendo con las mismas consultas de hoy; ninguna llamada nueva acepta un destinatario del llamante |
| II | Superficie | ☑ | `0`. Resend ya es proveedor; las plantillas viven en la cuenta que ya envía |
| III | Lo leído es dato | ☑ | El texto libre que llega a un correo (nombre de negocio, consulta de soporte, nombre de contacto) se escapa siempre (R3 de `research.md`) y nunca decide a quién ni qué se envía |
| IV | Acción `mutates` | ☑ | No hay acción nueva. Enviar sigue siendo consecuencia de una acción que ya existe y ya se audita |
| V | Estados honestos | ☑ | En modo registro, el flujo responde como si el correo hubiera salido, porque en ese entorno «salir» es quedar registrado (R1.2). Si Resend rechaza, el error nombra tipo y plantilla (R7.2). Un aviso sin texto propio se dice en el registro (R2.5) |
| VI | Por API | ☑ | Resend por su API HTTP |
| VII | Test primero | ☑ | Cada criterio EARS nace como prueba (ver `tasks.md`); las pruebas existentes de las specs 006 y 011 se adaptan antes de tocar los servicios y se ven en rojo |
| VIII | Licencias | ☑ | Ninguna dependencia nueva |
| IX | KB | ☑ | `research/2026-10-30-correos-con-oficio`, `brand/voice-and-copy`, `brand/brand-system`. Al cerrar: la nota de KB enlaza esta spec y se añade el banner en `nexus-state.md` |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Garantía 6 (ver arriba) | La prueba de barrido de `tests/isolation/` |
| **Licencias** | Ninguna dependencia nueva | — |
| **Medidor** | Nada de modelo. Resend factura por correo a Auphere, como hoy; staging deja de gastar | — |

## Diseño

### Iteración 1 — El núcleo: modo por entorno y envío por plantilla (Historia 1)

**Ajustes** (`apps/api/src/nexus_api/config.py`)

- `email_delivery: Literal["auto", "resend", "log"] = "auto"`, con la propiedad `email_mode`. Producción resuelve `auto` a `resend`; cualquier otro entorno, a `log`.
- **Guardia de arranque**: producción con `email_delivery="log"` lanza en el validador de ajustes, igual que las guardias de `change-me`. La comparten la API y el worker, que cargan los mismos ajustes.
- `email_delivers` sustituye a `email_enabled`: es cierta solo si el modo es `resend` y la clave no es de desarrollo. La usa `api/console/signup.py` para distinguir «no hay proveedor» de «el proveedor rechazó».
- `signup_from_email` se renombra a `notifications_from_email`, con el valor `Auphere <notifications@auphere.com>`. Se añade `email_reply_to = "support@auphere.com"`. Se quita `smtp_url`.
- En el arranque de la API y del worker, un `email.delivery_mode` con el modo resuelto. Si es staging con `resend`, sale como `warning`: «staging envía correo real» (R1.4).

**Catálogo** (`apps/api/src/nexus_api/services/email_catalog.py`, nuevo)

- `EmailKind(StrEnum)` con los 20 tipos de `contracts/catalogo.md`.
- `EmailSpec` congelada: `aliases: Mapping[str, str]`, `sender: Literal["billing", "notifications"]`, `variables: frozenset[str]`, `link_variables: frozenset[str]`, `owner: Literal["partner", "client", "none"]` y `links_allowed: bool`.
- `CATALOG: Mapping[EmailKind, EmailSpec]`.
- Ayudas puras:
  - `format_day_es(date)` da «6 de noviembre de 2026»; `format_month_es(year, month)`, «octubre de 2026»;
  - `console_link(path)` construye un enlace absoluto desde `console_base_url` (R2.6);
  - `lines_variable(lines, more=…)` escapa cada línea, las une con `<br>` y recorta para que el total quepa en 2 000 caracteres (R8 de `research.md`).

**Envío** (`apps/api/src/nexus_api/services/email.py`, reescrito)

- `send_template(kind, *, to, subject, variables, locale="es", partner_id=None, client_ref=None, reply_to=None) -> bool`. Nunca lanza, como hoy.
  1. Las claves de `variables` tienen que ser **exactamente** las de la ficha. Si no lo son, registra `email.variables_mismatch` con las que faltan y las que sobran, y devuelve `False` sin enviar (R2.3).
  2. Cada cadena se escapa con `html.escape(quote=True)`, salvo las que ya vienen de `lines_variable`, que se marcan con un tipo propio (`EmailLines`) para no escaparlas dos veces. Una cadena de más de 2 000 caracteres se recorta y termina en «…» (R6.3).
  3. Elige el alias: el del idioma pedido o, si no existe, el `es`.
  4. Remitente según `sender`; respuesta en `reply_to` o, si no se pasa, `settings.email_reply_to`.
  5. **Modo `log`**: escribe `email.suppressed` (ver `data-model.md`) y devuelve `True`.
  6. **Modo `resend`** sin clave real: `email.not_configured` y `False`, como hoy.
  7. **Modo `resend`**: `POST /emails` con `from`, `to`, `subject`, `reply_to`, `template: {id: alias, variables}` y `tags: [{name: "kind", value: kind}]`. Si responde 2xx, escribe `email.sent` con el `id` de Resend; si no, `email.send_failed` con el estado, el tipo, el alias y los primeros 500 caracteres del cuerpo (R7.2).
- Se borran `send_email`, `_smtp_send` y el repliegue SMTP. `docker-compose.yml` pierde el servicio `mailhog` y `NEXUS_SMTP_URL`.

### Iteración 2 — Cada sitio que envía pasa al catálogo (Historias 2, 3 y 5)

Un cambio por sitio; cada uno construye su asunto y sus variables y llama a `send_template`. La tabla dice qué correo del inventario se convierte en qué tipo.

| Sitio | Tipo | Notas |
|---|---|---|
| `scripts/seed_console_memberships.py` | `team_invite` | El enlace sale de `console_link`: se acaba la ruta relativa sin `--console-origin` |
| `api/console/team.py` | `team_invite` | **Arregla** el correo sin enlace. `INVITER` es el nombre de quien invita, o su correo |
| `services/client_invitation_email.py` | `client_invite` | — |
| `services/signup.py` | `signup_link` / `signup_existing` | El idioma pasa a la regla de la contraseña: `en` solo si se pide `en`. Hoy era al revés (cualquier valor distinto de `es` daba inglés) |
| `services/password_reset.py` | `password_reset` / `password_changed` | `SECURITY_CONTACT` cae a `email_reply_to` si está vacío en local; producción ya exige el contacto al arrancar |
| `api/admin/receipts.py`, `worker/…/partner_receipt_cron.py` | `receipt` | `services/partner_receipt_email.py` pasa a construir asunto y variables, sin HTML |
| `services/partner_billing.py` | `charge_confirm` | — |
| `services/wallet_alerts.py` (cliente sin saldo) | `client_out_of_quota` | `CLIENT_NAME` es el nombre del cliente si lo hay, o su referencia |
| `services/wallet_alerts.py` (80 % / 100 %) | `wallet_low` / `wallet_empty` | `CLIENTS_OUT_NOTE` vacía si no hay clientes sin tope |
| `services/usage_alerts.py` | `usage_cap_threshold` / `usage_cap_reached` | — |
| `services/console_notifications.py` (cliente) | `inbox_waiting`, `client_balance_low`, `client_balance_out` o `client_notice` | Texto de `client_notice` en `services/email_notices.py` |
| `services/console_notifications.py` (partner) | `partner_notice`, también para `client.out_of_quota` cuando el partner no tiene lista de alertas | Texto en `services/email_notices.py`; se acaba el volcado de claves |
| `worker/…/operator_alerts.py` | `conversation_escalated` | Sin resumen para una persona del partner, como hoy |
| `api/console/support.py` | `internal_alert` | `DETAIL` con `lines_variable` |
| `services/account_deletion.py` | `internal_alert` | `reply_to` = la persona que lo pidió (R5.1) |
| `worker/…/meta_reconciliation_cron.py` | `internal_alert` | `DETAIL` con una línea por canal |
| `worker/…/platform_watcher.py` | `internal_alert` | Prefijo `[Nexus]` → `[Auphere]` |

**Textos de los avisos** (`apps/api/src/nexus_api/services/email_notices.py`, nuevo)

- `PARTNER_NOTICES` y `CLIENT_NOTICES` tienen, por tipo, titular, mensaje, etiqueta del botón y ruta, con los textos de `contracts/catalogo.md` §18 y §19.
- `partner_notice_email(row, locale, client_name)` y `client_notice_email(row, locale)` devuelven asunto y variables; resuelven las variantes de `client.activated` según `missing` y rellena `{cliente}`, `{modelo}`, `{plantilla}` y `{ticket}` desde el contenido del aviso. Para un tipo sin fila devuelve el texto genérico y registra `email.notice_without_copy`.

### Iteración 3 — Las plantillas en Resend y su comprobación (Historias 2 y 4)

**Las plantillas**: 39 alias en HTML de correo (tablas, estilos en línea, alternativa para Outlook), con el tema de marca de R10 de `research.md`, el texto de `contracts/catalogo.md` y las variables de la ficha de cada tipo. Se publican por API. Por qué HTML y no el editor visual: R10. Una copia del HTML y del JSON inicial de cada una queda en `evidence/plantillas-iniciales/`. Es **registro**, no fuente: la fuente es Resend (D1).

**La comprobación** (`apps/api/scripts/check_email_templates.py`, nuevo): R7 de `research.md`. Recorre `CATALOG`; por cada alias, `GET /templates/{alias}`. Con `--json` imprime un informe que se guarda en `evidence/`.

**La prueba de escapado** (necesita el OK del owner): un envío por plantilla a `delivered@resend.dev`, con un nombre que lleva `<b>&</b>`, y la lectura del HTML entregado.

### Iteración 4 — Documentación viva y cierre

- `docs/correos.md` (nuevo) explica:
  - el catálogo y cómo añadir un tipo;
  - el modo por entorno;
  - qué escribe staging y dónde mirarlo (Logs Insights por `event = "email.suppressed"`);
  - cómo cambiar una plantilla en Resend y pasar la comprobación;
  - por qué la mayoría del texto no está en git.
- `docs/recuperar-la-contrasena.md` §6: sin Mailhog; el enlace en local y staging sale en el registro, y producción no puede.
- `docs/registro-de-partners.md` §5 ter y §5 quater: `email_delivers` y el remitente nuevo, con la enmienda a la regla «no-reply».
- `docs/paso-a-produccion-031-041.md`: la línea del correo.
- KB: banner en `nexus-state.md` y enlace a la spec desde la nota de investigación.
- `./scripts/verify.sh` una vez, al final.

## Estructura

```text
specs/051-correos-con-oficio/
├── spec.md · plan.md · research.md · data-model.md · quickstart.md · tasks.md
├── contracts/
│   ├── catalogo.md          # los 20 tipos: plantilla, variables, asunto, texto
│   └── redaccion.md         # la guía de redacción y la lista que la comprobación busca
├── checklists/requirements.md
└── evidence/                # comprobación de plantillas, plantillas iniciales, prueba de escapado

apps/api/src/nexus_api/
├── config.py                          # email_delivery, guardia, remitentes, reply_to
├── services/email.py                  # send_template (reescrito)
├── services/email_catalog.py          # nuevo
├── services/email_notices.py          # nuevo
└── (los 13 módulos de la tabla de la iteración 2)
apps/api/scripts/check_email_templates.py   # nuevo
apps/worker/src/nexus_worker/streams/       # 4 módulos de la tabla
apps/api/tests/
├── unit/test_email_delivery_mode.py        # nuevo
├── unit/test_email_send_template.py        # nuevo
├── unit/test_email_catalog.py              # nuevo
├── unit/test_email_no_inline_html.py       # nuevo, barrido
├── isolation/test_55_email_owner_tagging.py  # nuevo, barrido
└── (las pruebas existentes que se adaptan, ver tasks.md)
docker-compose.yml                          # sin mailhog
docs/correos.md                             # nuevo
```

## Complexity Tracking

| Desviación | Por qué hace falta | Alternativa más simple descartada |
|---|---|---|
| El texto de los avisos genéricos vive en el código, no en Resend | 29 tipos de aviso con la misma forma; una plantilla por tipo multiplica por 29 cada cambio de forma (R6 bis) | Una plantilla por aviso: 29 casi idénticas en el panel |
| `<br>` dentro de una variable | Las plantillas no tienen bucles y el recibo necesita sus conceptos (R8) | Quitar los conceptos del recibo |
