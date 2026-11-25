# Implementation Plan: Editar plantillas de WhatsApp

**Branch**: `075-editar-plantillas` | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/075-editar-plantillas/spec.md`

## Summary

Hoy la consola y el panel listan, crean y borran plantillas de WhatsApp, pero no las editan. La spec pide editarlas con el mismo nombre, en los dos sitios y con las mismas reglas. Además:

- Las plantillas que Auphere manda por su nombre no pueden cambiar sus variables.
- Nada que no se tocó se pierde.
- No se pisa un cambio ajeno.
- Queda en la auditoría quién editó qué.

El plan pone **una sola función de servicio** en la API, que deja a la consola y al panel:

- decidir si una plantilla se puede editar;
- montar lo que se manda a Meta;
- pedir la confirmación;
- escribir el espejo y la auditoría.

Meta recibe la edición por `POST /{template_id}`.

La API añade a cada fila de la lista el borrador, la huella y, si lo hay, el motivo de bloqueo. El editor visual de la consola pasa a `@nexus/ui` para que el panel use el mismo (investigación R3 y R9).

## Technical Context

**Language/Version**: Python 3.11 (API, canales y worker) · TypeScript 5 / React 19 / Next.js 16 (consola, panel y `@nexus/ui`)

**Primary Dependencies**: FastAPI, SQLAlchemy async, httpx (cliente de Meta) · Next.js App Router, Server Actions, zod, `@nexus/ui`. **Sin dependencias nuevas.**

**Storage**: PostgreSQL. Se lee y escribe `whatsapp_template_status` (el espejo, sin RLS, filtrado por `waba_id`) y `audit_log`. Se leen `messages` (bajo RLS) para contar los envíos en cola. Sin migración, salvo si C1 lo pide (R2).

**Testing**: pytest (unitarias, integración e `tests/isolation/`) · vitest + Testing Library (consola, panel y `@nexus/ui`).

**Target Platform**: API en ECS (staging por `develop`); consola y panel en Vercel.

**Project Type**: web, con API y dos frontales más un paquete compartido.

**Performance Goals**: guardar en menos de 3 s en condiciones normales: una lectura sin caché y una escritura en Meta, más otra lectura después.

**Constraints**:
- Meta limita las ediciones de una aprobada; Auphere no lleva la cuenta (2.4).
- Ningún texto de error de Meta va a los registros (8.5).
- La lista sigue sin caché en la consola.

**Scale/Scope**: decenas de plantillas por cliente; una edición por acción humana.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | La plantilla se busca por nombre e idioma en la cuenta de las credenciales leídas bajo RLS. El llamante no da ningún id de Meta. El espejo se filtra por esa `waba_id`. Prueba nueva: `tests/isolation/test_template_edit_scope.py` (barre todas las rutas `PUT …/templates/…`). `test_console_scope.py` cubre la ruta nueva de la consola. |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie `0`. Una llamada más a Meta con las credenciales que ya usan crear y borrar. |
| III | Lo leído es dato, nunca instrucción; navegador y `shell_local` no conviven sin guardas | ☑ | Ningún agente interviene. El texto de la plantilla es dato del partner que va a Meta. |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | Es una acción humana directa, no de un agente: no hace falta aprobación durable. La auditoría `console.template.edit` / `admin.template.edit` guarda la persona, el antes y el después (8.4). |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | «Editar» no aparece en las plantillas bloqueadas ni para quien solo lee. Tras guardar se enseña el estado que devuelve Meta, sin el motivo anterior. Hay estados de carga, error y conflicto en el editor. |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ☑ | No aplica: ningún agente opera esto. |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada tarea de comportamiento empieza por su test en rojo (tasks.md). |
| VIII | Licencias leídas enteras; AGPL no; "Apache modificada" se lee completa | ☑ | Ninguna dependencia nueva. |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[features/2026-11-23-editar-plantillas-whatsapp]]` |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías de `architecture/agent-isolation.md` toca? | **1 (RLS)**. Busca por la cuenta de WhatsApp de las credenciales de la sesión; el espejo sin RLS se filtra por esa cuenta. | Tarea de `tests/isolation/test_template_edit_scope.py` |
| **Licencias** — ¿qué dependencia nueva entra? | Ninguna. | — |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | Nada. Editar no cuesta en Meta. | — |

**Complejidad que hay que justificar:** mover el editor a `@nexus/ui` (R9). La spec no lo pide como tal, pero es la única forma de que el panel tenga el mismo editor sin copiarlo (D6 y 9.3).

## Project Structure

### Documentation (this feature)

```text
specs/075-editar-plantillas/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── template-edit.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
apps/channels/src/nexus_channels/whatsapp_meta/
└── meta_client.py                     # + edit_template(template_id, …)

apps/api/src/nexus_api/
├── services/
│   ├── whatsapp_templates.py          # TemplateOut sin cambios; caché e invalidación ya existen
│   └── whatsapp_template_edit.py      # NUEVO: bloqueo, borrador, huella, plantillas de sistema,
│                                      #        envíos en cola, edit_template(), espejo
├── api/console/
│   ├── schemas_channels.py            # TemplateContentIn (base de TemplateCreateIn), TemplateEditIn/Out,
│   │                                  # TemplateRowOut + edit_blocker, draft, version, system_variables
│   └── templates.py                   # merge_rows añade lo de arriba; PUT /{name}/{language}
└── api/admin/
    └── whatsapp_templates.py          # lista con los mismos campos; PUT /{name}/{language}

apps/worker/src/nexus_worker/streams/
└── cobranza_reminder_cron.py          # importa los nombres de cobros del registro de la API

apps/api/tests/
├── unit/test_template_edit_rules.py           # bloqueo, borrador, huella, variables de sistema
├── unit/test_endpoint_template_edit.py       # consola y panel: 200, 404, 409, 422, confirmación, espejo, auditoría
└── isolation/test_template_edit_scope.py      # garantía 1

apps/channels/tests/test_meta_client.py        # + edit_template

packages/ui/src/
├── components/template-editor.tsx     # NUEVO: el editor (antes TemplateComposer de la consola)
├── lib/template-rules.ts              # movido desde la consola
└── components/__tests__/template-editor.test.tsx

apps/console/src/
├── components/channels/template-composer.tsx   # envoltorio fino: textos + createTemplateAction / editTemplateAction
├── components/channels/templates-section.tsx   # «Editar» en fila y detalle, motivo de bloqueo, aviso, conflicto
├── app/(console)/clients/[ref]/channels/actions.ts  # + editTemplateAction
├── lib/backend/channels.ts                     # + editTemplate
└── i18n/lanes/channels.ts                      # textos es/en

apps/admin/src/app/(dashboard)/tenants/[id]/_integrations/
├── whatsapp-templates-dialog.tsx      # «Editar» con TemplateEditor
└── actions.ts (o el de integraciones) # + editWhatsAppTemplateAction

docs/                                   # la spec viva de plantillas, si existe, en el mismo commit
```

**Structure Decision**: el monorepo tal como está. La lógica va en `apps/api` (servicio y rutas) y `apps/channels` (cliente de Meta). El editor va en `packages/ui`, porque lo consumen `apps/console` y `apps/admin`. El worker solo cambia de dónde lee dos constantes.

## Decisiones de diseño que no se ven en la estructura

- **Quién edita en el panel.** La ruta del panel pide `require_admin_token` **y** `require_operator`, que lee la cabecera `X-Operator-Id`. La auditoría usa `operator_actor(operator)`, como `auphere_channels`, y no `admin:<token>` como hoy crear y borrar. La acción de servidor del panel llama a `requireOperator()` y manda `X-Operator-Id`. La revisión de seguridad del 2026-11-22 marcó como P0 abierto las Server Actions del panel sin operador, así que esta no puede nacer sin él.
- **Comparar borradores, no componentes en bruto.** Una plantilla es editable solo si el viaje de ida y vuelta la reproduce: `build(draft_of(componentes de Meta))` tiene que dar lo mismo que los componentes de Meta, normalizados. Si no la reproduce, se bloquea con `unsupported_component`.
  - «No cambia nada» (3.4) se decide comparando lo que se va a mandar con `build(draft_of(actual))` y la categoría. Así, una diferencia de forma en la lectura de Meta no gasta una edición de una aprobada.
  - La prueba unitaria del viaje usa fixtures con la forma de la lista de Meta, como las de `tests/integration/reservas/_meta_templates.py`.
- **El texto de error de Meta.** Va a la pantalla como dato y nunca a los registros (8.5). El error lleva un código cerrado `meta_rejected`, con `meta_code` y `meta_subcode`, y `user_message`, que es el `error_user_msg` que Meta escribe para personas y sale del cuerpo de la respuesta.
  - La pantalla traduce los códigos que conoce (límite de ediciones, categoría bloqueada) y enseña `user_message` en los demás.
  - Los registros solo guardan el tipo y los códigos.
- **Categoría.** `TemplateContentIn.category` mantiene `AUTHENTICATION`, porque crear la acepta hoy. Al editar no puede llegar, porque una plantilla de autenticación está bloqueada.
- **Spec viva.** `docs/canales.md` gana una sección corta, «Plantillas: crear, editar y borrar», con las reglas de edición. Va en el mismo commit.

## Enmienda del 2026-11-25: un solo editor (requisito 10, D7)

Al poner la 075 sobre `develop` (`e7e6a71d`), el compositor de la consola chocaba con el formulario de autenticación de la 077. El owner decidió que no haya dos caminos:

- **`@nexus/ui`.** `TemplateEditor` pinta Autenticación al crear: botón, caducidad, aviso y el texto fijo de Meta (`OtpPreview`, exportada). Las reglas son de `template-rules.ts`: `missingOtpPieces`, `otpPreviewText`, y `toSubmission`, que devuelve una unión por categoría (`ContentSubmission | OtpSubmission`) con la forma que toma la acción de la consola. Al editar solo ofrece Utilidad y Marketing (1.4, 3.2).
- **Consola.** `template-composer.tsx` es solo el envoltorio del editor. Se borran `OtpFields`, `OtpPreview` y las claves del texto fijo del diccionario.
- **Panel.** «Nueva plantilla» abre el editor en un diálogo, como editar. Se borran el formulario propio y `otp-template.ts`. La acción valida la forma con `zod` estricto.
- **API.** `TemplateCreateIn` se mueve a `schemas/whatsapp_templates.py`. Las dos rutas de alta lo reciben y llaman a `services/whatsapp_templates.submit_template` (`to_components` y `parameter_format`). Desaparecen `OtpTemplateIn` y la entrada `components` del panel. Las dependencias de autorización de las rutas no cambian.

## C1, cerrada sin trabajo extra

La aprobada editada sale «En revisión» y el owner decidió que no se envía (research R2). Las tres puertas de envío, `notification.send_template`, el outbox de Reservas y cobros, ya exigen `APPROVED`. No hay migración ni columna `approved_before_edit_at`.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Editor movido a `@nexus/ui` | El panel edita lo mismo que la consola (D6) con las mismas reglas (9.3) | Copiar el editor al panel daría dos editores que se separan con el tiempo |
