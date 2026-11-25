# Modelo de datos: Editar plantillas de WhatsApp (075)

No hay tablas nuevas. Se leen y se escriben las que ya existen. Lo nuevo son formas de datos en la API y una constante compartida.

## Plantilla en Meta (externa)

La clave es `(waba_id, name, language)`. Campos que se leen: `id`, `category`, `status`, `quality_score`, `components`. El `id` de Meta **nunca** llega del llamante: se saca de la lista de la cuenta de las credenciales de la sesión.

Estados que Meta deja editar: `APPROVED`, `REJECTED`, `PAUSED`. Cualquier otro → `edit_blocker = "status"`.

## `whatsapp_template_status` (espejo, existente, sin RLS)

Clave única `(waba_id, template_name, language)`.

Lo que escribe la edición (R6), solo si `last_event_at IS NULL OR last_event_at < t0`:

| Columna | Valor |
|---|---|
| `status` | el que devuelve la lectura de Meta tras editar |
| `reason` | `NULL` |
| `category` | la que devuelve esa lectura |
| `last_event_at` | `now()` |
| `last_event_payload` | `{"field": "nexus_edit", "value": {"status": …}}` |

Siempre con `WHERE waba_id = <la de las credenciales de la sesión>`. Si no hay fila, se inserta con el `tenant_id` de la sesión.

> Si C1 lo pide (plan, «Decisión pendiente»): columna `approved_before_edit_at timestamptz NULL`.

## `audit_log` (existente)

Una fila por edición que llega a Meta:

- `action`: `console.template.edit` o `admin.template.edit`.
- `target`: `template:<name>:<language>`.
- `before`: `{category, components}`.
- `after`: `{category, components, meta_status}`.

La persona es la del token de la consola o el operador del panel. Una edición que no cambia nada (3.4) no deja fila.

## `messages` (existente, bajo RLS) — solo lectura

Envíos en cola de una plantilla: `status = 'pending'`, `template_payload->>'name' = name` y `template_payload->>'language' = language`. Se usa para el aviso de 5.1.

## Formas nuevas de la API

### `TemplateContentIn` (base común de crear y editar)

| Campo | Tipo | Regla |
|---|---|---|
| `category` | `UTILITY \| MARKETING` | Al editar es opcional; si viene en una aprobada y es distinta → 422 `category_locked` |
| `header_text` | `str ≤ 60 \| null` | sin variables |
| `body_text` | `str 1..1024` | |
| `footer_text` | `str ≤ 60 \| null` | |
| `buttons` | `≤ 3 × {type, label, url?, phone_number?}` | `QUICK_REPLY`, `URL` o `PHONE_NUMBER` |
| `examples` | `{var: str}` | un ejemplo por variable del cuerpo |

`TemplateCreateIn` = `TemplateContentIn` + `name` + `language`, que no cambia para quien ya la usa.

### `TemplateEditIn`

`TemplateContentIn` + `version: str` (la huella que se abrió) + `confirm: bool = false`.

### `TemplateEditOut`

`{name, language, changed: bool, status: str | null, category: str | null}`.

### `TemplateRowOut` (lista, campos añadidos)

| Campo | Qué es |
|---|---|
| `edit_blocker` | `null` o uno de `status`, `authentication`, `media_header`, `header_variable`, `unsupported_button`, `url_variable`, `too_many_buttons`, `unsupported_component` |
| `draft` | `TemplateContentOut` con el contenido partido; `null` si hay bloqueo de contenido |
| `version` | huella de 16 caracteres (R7) |
| `system_variables` | `null` o `{mode: "exact" \| "subset_keep", variables: [str]}` (R5) |

## Plantillas de sistema (constante compartida)

`SYSTEM_TEMPLATES: Mapping[str, SystemTemplate]`, en `nexus_api.services.whatsapp_template_edit`.

- Las seis de Reservas, en modo `exact`, con `reservations.templates.VARIABLES[name]`.
- `recordatorio_pago_proximo` y `recordatorio_pago_vencido`, en modo `subset_keep`, con `{cliente, negocio, monto, fecha}`.

Solo aplica a idiomas `es*`, que es en los que Auphere las manda.
