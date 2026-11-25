---
description: "Tareas de la spec 075 — editar plantillas de WhatsApp"
---

# Tasks: Editar plantillas de WhatsApp

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/template-edit.md](contracts/template-edit.md), [quickstart.md](quickstart.md)

**Tests**: obligatorios (constitución §VII). Cada bloque de tests se escribe y se ve en rojo antes de su implementación.

**Enmienda del 2026-11-25**: la fase 7 aplica la D7 del owner (requisito 10) al poner la 075 sobre `develop` (`e7e6a71d`), que ya trae la 077.

**Pruebas de API**: siguen el patrón de `apps/api/tests/unit/test_endpoint_console_channels.py`, con `console_world`, `db_session` y `respx` contra Graph. Los ficheros nuevos van al lado.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: se puede hacer en paralelo (ficheros distintos, sin dependencias pendientes).
- **[Story]**: US1, US2 o US3, las historias de la spec.

---

## Phase 1: Setup

No hay dependencias nuevas ni estructura que crear. La rama `075-editar-plantillas` sale de `develop` (bfe97215).

---

## Phase 2: Foundational (lo que necesitan las tres historias)

**⚠️ Ninguna historia empieza sin esta fase.**

### Tests (en rojo primero)

- [x] T001 [P] Test de `MetaClient.edit_template` en `apps/channels/tests/test_meta_client.py`. Comprueba cinco cosas:
  - hace `POST /{template_id}` con `components`;
  - `category` va solo si se pasa;
  - `parameter_format: "NAMED"` va solo si se pasa;
  - nunca manda `name` ni `language`;
  - un 400 de Graph sale como `MetaAPIError` con `code` y `subcode`.

  _Requisitos: 1.5, 1.6_
- [x] T002 [P] Tests unitarios de las reglas en `apps/api/tests/unit/test_template_edit_rules.py`, con fixtures con la forma de la lista de Meta (copiar la forma de `apps/api/tests/integration/reservas/_meta_templates.py`):
  - **`edit_blocker`**: devuelve exactamente un código para cada caso. `status` para `PENDING`, `IN_APPEAL` y `DISABLED`. `authentication` para la categoría `AUTHENTICATION`. `media_header` para cabecera `IMAGE`, `VIDEO` o `DOCUMENT`. `header_variable` para cabecera de texto con `{{…}}`. `unsupported_button` para `OTP`, `COPY_CODE`, `CATALOG` o `FLOW`. `url_variable` para una URL con `{{1}}`. `too_many_buttons` para 4 botones. `unsupported_component` para `CAROUSEL`, `LIMITED_TIME_OFFER` o un tipo desconocido. Devuelve `None` para `APPROVED`, `REJECTED` y `PAUSED` cuando el contenido se puede pintar.
  - **Viaje de ida y vuelta**: para toda plantilla sin bloqueo, `build(draft_of(c)) == normalize(c)`. Si el viaje no reproduce la plantilla, da `unsupported_component`.
  - **`version`**: tiene 16 caracteres, es estable con el mismo `{category, components}` en otro orden de claves, y cambia si cambia un carácter del cuerpo.
  - **`is_noop`**: da verdadero con el mismo contenido y la misma categoría, y falso si cambia la categoría.
  - **`check_system_variables`**: en `exact` informa de las que faltan y las que sobran. En `subset_keep` rechaza una variable fuera de `{cliente, negocio, monto, fecha}` y la pérdida de una que la versión actual lleva, y acepta un subconjunto que conserve las actuales.
  - **`SYSTEM_TEMPLATES`**: contiene los seis nombres de `reservations.templates.NAMES` con `VARIABLES[name]` y los dos de cobros.

  _Requisitos: 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 7.1_

### Implementación

- [x] T003 `MetaClient.edit_template(*, template_id, access_token, components, category=None, parameter_format=None)` en `apps/channels/src/nexus_channels/whatsapp_meta/meta_client.py`, con `self._post(f"/{template_id}", …)`. Actualizar el docstring del módulo con la ruta nueva. T001 pasa a verde. _Requisitos: 1.5_
- [x] T004 Formas de la API en `apps/api/src/nexus_api/api/console/schemas_channels.py`:
  - **`TemplateContentIn`**: extraer de `TemplateCreateIn` los campos `category`, `header_text`, `body_text`, `footer_text`, `buttons` y `examples`, con `variables()`, `parameter_format()` y `to_components()`. `TemplateCreateIn` hereda de ella y no cambia su forma pública (las pruebas de creación siguen en verde). `category` sigue siendo `Literal["MARKETING", "UTILITY", "AUTHENTICATION"]`.
  - **`TemplateEditIn`**: `TemplateContentIn` con `category` opcional, más `version: str` (`min_length=16`, `max_length=16`) y `confirm: bool = False`.
  - **`TemplateEditOut`**: `{name, language, changed, status, category}`.
  - **`TemplateContentOut`**: el borrador sin validación de entrada.
  - **`TemplateRowOut`**: añadir `edit_blocker: str | None`, `draft: TemplateContentOut | None`, `version: str | None` y `system_variables: SystemVariablesOut | None`, donde `mode` es `"exact" | "subset_keep"` y `variables` es `list[str]`.

  _Requisitos: 1.3, 1.4, 4.1, 7.1, 9.3_
  _Desviación (2026-11-23): `TemplateContentIn`, `TemplateContentOut` y los botones viven en `apps/api/src/nexus_api/schemas/whatsapp_templates.py`, no en `schemas_channels.py`: el servicio los necesita, e importar algo de `api.console` ejecuta su `__init__`, que importa las rutas, que importan el servicio (import circular). `schemas_channels.py` los reexporta._
- [x] T005 Servicio `apps/api/src/nexus_api/services/whatsapp_template_edit.py` con las piezas puras de T002:
  - `EDITABLE_STATUSES`, `BlockerCode`, `edit_blocker(tpl)`, `draft_of(tpl)`, `build(content)` (reutiliza `TemplateContentIn.to_components`), `normalize(components)`, `version(tpl)`, `is_noop(...)`;
  - `SystemTemplate`, `SYSTEM_TEMPLATES` y `check_system_variables(...)`. Las de Reservas toman sus variables de `reservations.templates.VARIABLES`; los dos nombres de cobros son constantes exportadas `COBROS_PROXIMO` y `COBROS_VENCIDO`.

  T002 pasa a verde. _Requisitos: 3.1, 3.2, 3.3, 3.4, 4.1, 7.1, 9.3_
- [x] T006 `apps/worker/src/nexus_worker/streams/cobranza_reminder_cron.py`: `TEMPLATE_PROXIMO` y `TEMPLATE_VENCIDO` se importan de `nexus_api.services.whatsapp_template_edit` (`COBROS_PROXIMO` y `COBROS_VENCIDO`) en vez de declararse ahí, con el mismo valor. Correr `cd apps/worker && uv run pytest tests/ -k cobranza -x`. _Requisitos: 4.1_
- [x] T007 [P] Mover `apps/console/src/components/channels/template-rules.ts` y su test a `packages/ui/src/lib/template-rules.ts` y `packages/ui/src/lib/__tests__/template-rules.test.ts`, y exportarlos desde `packages/ui/src/index.ts`. Los imports de la consola apuntan a `@nexus/ui`. El test movido sigue en verde sin cambiar sus casos. _Requisitos: 9.3_
- [x] T008 Test primero, en `packages/ui/src/components/__tests__/template-editor.test.tsx`, y después `TemplateEditor` en `packages/ui/src/components/template-editor.tsx`, sacado del cuerpo de `apps/console/src/components/channels/template-composer.tsx`:
  - **Props**: `labels` (todas las frases que hoy da `useT`), `mode: "create" | "edit"`, `initial`, `categoryLocked`, `systemVariables`, `pending`, `serverError`, `onSubmit(draft, { confirm })` y `onCancel`.
  - **En `edit`**: el nombre y el idioma salen como título y no como campos. Si `categoryLocked`, la categoría no se pinta. Si hay `systemVariables`, se listan las variables que tiene que llevar.
  - Exportarlo desde `packages/ui/src/index.ts`.
  - **El test comprueba** tres cosas: en `edit` no hay inputs de nombre ni de idioma; con `categoryLocked` no hay control de categoría; y `onSubmit` recibe el borrador.

  _Requisitos: 1.3, 2.3, 4.1, 9.2_
- [x] T009 `apps/console/src/components/channels/template-composer.tsx` pasa a ser un envoltorio de `TemplateEditor`: los textos de `useT` van a `labels`, y en `create` sigue llamando a `createTemplateAction`. `apps/console/src/components/channels/__tests__/template-composer.test.tsx` sigue en verde sin cambiar sus casos. _Requisitos: 9.3_

**Checkpoint**: la API sabe decir si una plantilla se puede editar y cómo se arma, el cliente de Meta sabe editar, y el editor vive en `@nexus/ui` con la consola igual que antes.

---

## Phase 2b: Las puertas de la constitución

- [x] T010 Test de aislamiento de la garantía 1 en `apps/api/tests/isolation/test_template_edit_scope.py`. Se escribe aquí y queda en rojo hasta T015 y T016.
  - **Montaje**: dos clientes A y B con credenciales de Meta en cuentas distintas (`WABA_A` y `WABA_B`), y `respx` con la lista de cada cuenta.
  - **Barrido**: recorre `app.routes` y toma **todas** las rutas `PUT` cuyo camino acabe en `/templates/{name}/{language}`, sin una lista fija.
  - **Comprobación**, para cada una, con la sesión de A y el nombre de una plantilla que solo existe en `WABA_B`:
    - responde 404 `template_not_found`;
    - no hay ninguna llamada a `POST /{id}` de Graph;
    - la fila de `whatsapp_template_status` de `WABA_B` no cambia.
  - **Y una más**: el cuerpo no acepta `template_id` ni `waba_id`, porque `extra="forbid"` da 422.

  _Requisitos: 8.1, 8.2, 8.6_
  _Nota (2026-11-23): se escribió después de T016, así que no se vio en rojo. Barre 2 rutas (consola y panel) y pasa._
- Licencias: **no aplica**. El plan no instala ninguna dependencia (plan, Technical Context).
- Medidor: **no aplica**. Editar una plantilla no cuesta en Meta ni gasta modelo (spec, encabezado).

**Checkpoint**: las puertas tienen dueño.

---

## Phase 3: User Story 1 — Corregir una plantilla rechazada o pausada (P1) 🎯 MVP

**Goal**: editar desde la consola y desde el panel una plantilla `REJECTED` o `PAUSED`, con el mismo nombre, sin perder nada, sin pisar cambios ajenos y con auditoría.

**Independent Test**: quickstart, «En staging», paso 1 en la consola y en el panel.

### Tests (en rojo primero)

- [x] T011 [P] [US1] Tests de la ruta de la consola en `apps/api/tests/unit/test_endpoint_template_edit.py`:
  - **La lista**: trae `edit_blocker`, `draft`, `version` y `system_variables` por fila.
  - **Plantilla `REJECTED` con `version` correcta**: responde 200 con `changed: true`.
    - Graph recibe `POST /{id}` con `build(draft)` y sin `name`.
    - La caché de la cuenta se vacía.
    - La respuesta trae el `status` de la lectura posterior.
    - El espejo queda con ese `status` y `reason = NULL`, filtrado por la `waba_id` de A.
    - La auditoría tiene `console.template.edit` con el actor de la persona, y `before` y `after` con `{category, components}`.
  - **El espejo no se pisa**: si su `last_event_at` es posterior a `t0` (aviso adelantado), no cambia.
  - **Errores**:
    - 404 `template_not_found` con otro idioma;
    - 409 `template_changed` con una `version` vieja, sin llamar a Graph;
    - 409 `not_editable` con `blocker` para `PENDING` y para una cabecera `IMAGE`;
    - 422 `missing_examples` con una variable sin ejemplo;
    - 400 con un nombre inválido.
  - **Sin cambios**: el mismo contenido da 200 con `changed: false`, sin llamar a Graph y sin auditoría.
  - **Graph responde 400** con `error_user_msg`: la ruta da 422 `meta_rejected` con `meta_code`, `meta_subcode` y `user_message`. Ningún registro capturado (`structlog` testing) contiene el texto de Meta.
  - **Permisos**: un rol sin `channels:write` recibe 403.

  _Requisitos: 1.1, 1.2, 1.4, 1.5, 1.6, 3.1, 3.2, 3.4, 6.1, 6.2, 6.3, 7.1, 8.2, 8.3, 8.4, 8.5, 9.4_
- [x] T012 [P] [US1] Tests de la ruta del panel en el mismo fichero, en una clase aparte, contra `PUT /admin/tenants/{id}/whatsapp/templates/{name}/{language}`:
  - sin `X-Operator-Id` responde 400;
  - con el operador, el mismo 200 que T011, con la auditoría `admin.template.edit` y el actor `operator_actor(operator)`;
  - la lista del panel trae los mismos campos nuevos.

  _Requisitos: 8.3, 8.4, 9.1, 9.3_
- [x] T013 [P] [US1] Tests de la consola en `apps/console/src/components/channels/__tests__/templates-section.test.tsx`:
  - **Dónde sale «Editar»**: en filas `REJECTED` y `PAUSED` con permiso de gestión. No sale con solo lectura, ni con `edit_blocker`; en ese caso el detalle dice el motivo en una línea.
  - **Al abrir**: el editor sale con el `draft`, el nombre y el idioma como título, y la acción sugerida a la vista.
  - **Al guardar**: llama a `editTemplateAction` con `ref`, `name`, `language`, `version` y el borrador.
  - **Respuestas**:
    - con `template_changed`, enseña el aviso y el botón de recargar;
    - con `meta_rejected`, enseña el `user_message` y conserva el texto;
    - con éxito, refresca la lista.

  _Requisitos: 1.1, 1.2, 1.3, 1.6, 3.2, 6.1, 7.1, 8.3_
- [x] T014 [P] [US1] Tests del panel en `apps/admin/src/app/(dashboard)/tenants/[id]/_integrations/__tests__/whatsapp-templates-dialog-edit.test.tsx` (al poner la 075 sobre `develop`, el nombre sin `-edit` ya era de los tests de autenticación de la 077):
  - «Editar» sale con las mismas reglas que en la consola;
  - el editor es `TemplateEditor` en modo `edit`;
  - `editWhatsAppTemplateAction` llama a `requireOperator()` y manda `X-Operator-Id`.

  _Requisitos: 9.1, 9.2, 8.3_

### Implementación

- [x] T015 [US1] `edit_template(session, *, creds, name, language, body, actor, audit_action)` en `apps/api/src/nexus_api/services/whatsapp_template_edit.py`, en este orden:
  1. Leer la lista **sin caché** de `creds.waba_id` y buscar por nombre e idioma; si no está, 404 `template_not_found`.
  2. Comprobar la `version`; si no coincide, 409 `template_changed`.
  3. Comprobar `edit_blocker`; si lo hay, 409 `not_editable`.
  4. Comprobar los ejemplos; si falta alguno, 422 `missing_examples`.
  5. Comprobar `is_noop`; si no cambia nada, 200 con `changed: false`.
  6. Apuntar `t0` y llamar a `MetaClient.edit_template`, con `category` solo si cambia y `parameter_format` según el cuerpo. Un `MetaAPIError` da 422 `meta_rejected`, con el `user_message` leído de `exc.body`, y el registro guarda solo el tipo y los códigos.
  7. Vaciar la caché, volver a leer y actualizar el espejo con `WHERE waba_id = creds.waba_id AND (last_event_at IS NULL OR last_event_at < t0)`, o insertarlo con el `tenant_id` de la sesión.
  8. Escribir la auditoría con `before` y `after`.

  _Requisitos: 1.4, 1.5, 1.6, 3.4, 6.1, 6.2, 6.3, 7.1, 8.1, 8.2, 8.4, 8.5, 9.4_
- [x] T016 [US1] Rutas y lista:
  - **Consola**, en `apps/api/src/nexus_api/api/console/templates.py`:
    - `merge_rows` rellena `edit_blocker`, `draft`, `version` y `system_variables`;
    - `PUT /{name}/{language}` con `client_scope("channels:write")` llama a `edit_template(..., audit_action="console.template.edit")`.
  - **Panel**, en `apps/api/src/nexus_api/api/admin/whatsapp_templates.py`:
    - la lista devuelve las mismas filas enriquecidas; reutiliza `merge_rows`, o mueve `merge_rows` al servicio si así la comparten;
    - `PUT /{name}/{language}` con `require_admin_token` **y** `require_operator` llama a `edit_template(..., actor=operator_actor(operator), audit_action="admin.template.edit")`.

  T010, T011 y T012 pasan a verde, y `tests/isolation/test_console_scope.py` sigue en verde. _Requisitos: 1.1, 8.1, 8.3, 9.1, 9.3_
- [x] T017 [P] [US1] Consola, lado servidor:
  - `editTemplate(ref, name, language, body)` en `apps/console/src/lib/backend/channels.ts`, que hace `PUT` a `…/whatsapp/templates/{name}/{language}`;
  - `editTemplateAction` en `apps/console/src/app/(console)/clients/[ref]/channels/actions.ts`, con zod (`ref`, `name` `^[a-z0-9_]{1,512}$`, `language` de 2 a 15, `version` de 16, `confirm` booleano, y el contenido como en `createTemplateAction` con `category` opcional), `can(role, "channels:write")`, `run()` y `revalidatePath`.

  _Requisitos: 8.3_
- [x] T018 [US1] Consola, pantalla, en `apps/console/src/components/channels/templates-section.tsx` y `template-composer.tsx` (modo `edit`):
  - «Editar» en la fila y en el detalle solo si `manage && !row.edit_blocker`;
  - si hay bloqueo, una línea en el detalle con el motivo y «se edita en WhatsApp Manager»;
  - el editor en modo `edit` con `row.draft`, `row.version` y la acción sugerida;
  - al recibir `template_changed`, aviso y recargar; al recibir `meta_rejected`, `user_message`;
  - con éxito, un toast y refrescar.
  - Los textos van en es y en en, en `apps/console/src/i18n/lanes/channels.ts`, con una frase por código de bloqueo.

  T013 pasa a verde. _Requisitos: 1.1, 1.2, 1.3, 1.6, 3.2, 6.1, 7.1_
- [x] T019 [US1] Panel:
  - `editWhatsAppTemplate(tenantId, name, language, body, operatorId)` en `apps/admin/src/lib/backend.ts`, con la cabecera `X-Operator-Id`;
  - `editWhatsAppTemplateAction` en `apps/admin/src/app/(dashboard)/tenants/[id]/_integrations/setup-actions.ts`, con `requireOperator()` y el operador de la sesión;
  - en `whatsapp-templates-dialog.tsx`, «Editar» con `TemplateEditor` y textos en español, con las mismas reglas de bloqueo y de error que la consola.

  T014 pasa a verde. _Requisitos: 9.1, 9.2, 8.3_

**Checkpoint**: una rechazada o pausada se corrige desde la consola y desde el panel. Es el MVP.

---

## Phase 4: User Story 2 — Editar una plantilla aprobada (P2)

**Goal**: editar una aprobada con confirmación previa, sin tocar su categoría y avisando de los envíos en cola cuando cambian las variables.

**Independent Test**: quickstart, «En staging», paso 2.

### Tests (en rojo primero)

- [x] T020 [P] [US2] Tests de la ruta en `apps/api/tests/unit/test_endpoint_template_edit.py`:
  - una `APPROVED` sin `confirm` da 409 `confirmation_required` con `reasons: [{"kind": "approved"}]` y no llama a Graph;
  - con `confirm: true` da 200;
  - una `category` distinta en una `APPROVED` da 422 `category_locked`;
  - quitar o renombrar una variable de una plantilla que no es de sistema, con 3 `messages` del cliente en `pending` cuyo `template_payload` es ese nombre e idioma (más 2 de otro cliente y 1 de otro idioma, que no cuentan), da `reasons` con `{"kind": "queued_sends", "count": 3}`;
  - sin cambios de variables no sale `queued_sends`;
  - con Graph devolviendo el error de límite de ediciones, sale `meta_rejected` con su `meta_code`.

  _Requisitos: 2.1, 2.2, 2.3, 2.4, 5.1_
- [x] T021 [P] [US2] Tests de `TemplateEditor` en `packages/ui/src/components/__tests__/template-editor.test.tsx`:
  - cuando `onSubmit` devuelve `confirmation_required`, abre la confirmación con una frase por razón (`approved` dice las tres cosas de 2.2, y `queued_sends` dice el número);
  - al confirmar, vuelve a llamar con `{ confirm: true }`.

  _Requisitos: 2.2, 5.1_

### Implementación

- [x] T022 [US2] En `edit_template`, antes de llamar a Meta:
  - `category_locked` si el estado es `APPROVED` y la categoría cambia;
  - la lista de razones: `approved` si el estado es `APPROVED`, y `queued_sends` si se quitan o renombran variables y `count_queued_sends(session, name, language) > 0`, contados en `messages` bajo RLS con `status = pending`;
  - si hay razones y no hay `confirm`, 409 `confirmation_required`.

  T020 pasa a verde. _Requisitos: 2.2, 2.3, 5.1_
- [x] T023 [US2] Confirmación dentro de `TemplateEditor`, con `ConfirmDialog` de `@nexus/ui`.
  - Textos de las razones: en la consola, en `apps/console/src/i18n/lanes/channels.ts` (es y en); en el panel, en español.
  - La pantalla traduce el `meta_code` del límite de ediciones a una frase, y en el resto enseña `user_message`.

  T021 pasa a verde. _Requisitos: 2.2, 2.4, 5.1_
- [x] T024 [US2] Comprobar en `apps/api/tests/unit/test_endpoint_template_edit.py` que, después de editar, `resolve_template` de difusiones (`apps/api/src/nexus_api/services/broadcasts.py`) lee la versión nueva y no la de la caché: se vació en T015. Si no la lee, arreglar la invalidación. _Requisitos: 5.2_

  _Nota (2026-11-23): no se conoce el `meta_code` del límite de ediciones (research R2, C2), así que no hay frase propia para él. Las dos pantallas enseñan el `user_message` de Meta y, si no viene, una frase genérica. Cuando se vea el código en staging, se añade su frase._
  _Nota (2026-11-23): el editor recorta el texto y quita espacios y guiones del teléfono al mandar. `is_noop` compara sin contar eso, así que no se gasta una edición por formato (3.4). En una edición real, un campo no tocado puede salir recortado: se acepta, porque no cambia el contenido (3.3). El panel enseña además el motivo de rechazo de Meta en cada fila._

**Checkpoint**: las aprobadas se editan con aviso y sin cambiar su categoría.

---

## Phase 5: User Story 3 — Plantillas que Auphere manda por su nombre (P3)

**Goal**: corregir las de Reservas y cobros sin romper lo que Auphere les manda, y que la consola lite lo vea.

**Independent Test**: quickstart, «En staging», paso 4.

### Tests (en rojo primero)

- [x] T025 [P] [US3] Tests de la ruta en `apps/api/tests/unit/test_endpoint_template_edit.py`:
  - `reserva_recordatorio` sin `{{nombre}}` da 422 `system_variables` con `missing: ["nombre"]`; con `{{otra}}`, `extra: ["otra"]`;
  - `recordatorio_pago_vencido` que pierde `monto`, o que añade `{{iban}}`, da 422; un subconjunto que conserva las actuales da 200;
  - la fila de la lista trae `system_variables` con su modo;
  - tras editar una de Reservas rechazada, `GET /console/lite/reservas/templates` del cliente la enseña con el estado nuevo, y `ensure_templates` no vuelve a pedirla a Meta (`respx` sin `POST /{waba}/message_templates`).

  _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5_
- [x] T026 [P] [US3] Test de `TemplateEditor`: con `systemVariables`, lista las variables y avisa al escribir si falta una o sobra otra. _Requisitos: 4.1, 4.2_

### Implementación

- [x] T027 [US3] En `edit_template`, `check_system_variables` en idiomas `es*`: si falla, 422 `system_variables` con `missing` y `extra`. `merge_rows` rellena `system_variables`. T025 pasa a verde. _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5_
- [x] T028 [US3] `TemplateEditor` pinta `systemVariables` y su aviso en vivo, reutilizando el análisis de variables de `template-rules.ts`. Los textos van en la consola (es y en) y en el panel (es). T026 pasa a verde. _Requisitos: 4.1, 4.2_

**Checkpoint**: las tres historias funcionan cada una por su lado.

---

## Phase 6: Polish & Cross-Cutting

- [x] T029 [P] Sección «Plantillas: crear, editar y borrar» en `docs/canales.md`. Dice qué se puede editar, qué bloquea, la confirmación, las plantillas de sistema y que el espejo se actualiza al guardar. Va en el mismo commit que el código. _Requisitos: 3.2, 4.1, 6.2_
- [x] T030 Borrar la plantilla desechable `nexus_prueba_edicion_075` de la cuenta de pruebas de Meta (`Test WhatsApp Business Account`) cuando Meta termine de revisar su edición. Mientras está en revisión, Meta no deja borrarla. C1 y C2 ya están anotadas en research R2. _Requisitos: 2.2_
- [x] T031 Puertas de UI del workspace sobre el editor, la sección de la consola y el diálogo del panel: `ui-states-checklist`, `a11y-audit`, `responsive-audit` y `design-tokens`, sin ningún 🔴 pendiente. _Requisitos: 1.1, 3.2_
  _Hecho (2026-11-23): estados, «Recargar» con espera y fallo dicho en el editor (consola y panel); a11y, 🔴 `role="alert"` sobre la `<ul>` corregido y campos descritos por sus fallos, foco en el botón mal escrito y confirmación anunciada, axe limpio; responsive, 🔴 pie del editor que desbordaba a 360 px (estimado por clases) apilado y diálogo del panel a `sm:max-w-2xl`; tokens, sin hex ni estilos en línea, `status-danger/40` y `status-warning/15` a sus tokens._
- [x] T032 `/cso` sobre el diff (toca autorización del panel y entrada externa hacia Meta). Un HIGH o CRITICAL bloquea. _Requisitos: 8.1, 8.3, 8.5_
  _Hecho (2026-11-23): sin hallazgos HIGH ni CRITICAL. El informe está en `.gstack/security-reports/2026-11-23-075-api.json` (local). En la pantalla no hay `dangerouslySetInnerHTML`: el `user_message` de Meta se pinta como texto. La acción del panel llama primero a `requireOperator()`. Se reforzó el recuento de envíos en cola con el cliente del contexto._
- [x] T033 Validación del quickstart, «En local»: `./scripts/verify.sh lint`, las pruebas tocadas de API, canales, worker, `@nexus/ui`, consola y panel, y `next build` de la consola y del panel. Las suites completas quedan para el paso a `main`. _Requisitos: todas_
  _Hecho (2026-11-23):_
  - _`./scripts/verify.sh lint` en verde (ruff y `mypy --strict` en api, worker, channels y mcp)._
  - _pytest de lo tocado: 1849 en API (unit, isolation e integración de plantillas y Reservas), 30 en canales y 34 en el worker (cobranza)._
  - _vitest: 318 en `@nexus/ui`, 2549 en consola y 705 en panel; typecheck en verde en los tres._
  - _`next build` de consola y panel compilan; los corrió el subagente de T031 tras sus últimos cambios._
  - _Las suites completas y el quickstart en staging quedan para el paso por `develop`._

---

## Phase 7: Un solo editor para crear y editar (requisito 10, D7, 2026-11-25)

**Objetivo**: la autenticación de la 077 entra en el `TemplateEditor` compartido, y el panel crea con él. Ni la consola ni el panel conservan un formulario de plantillas propio, y los clientes de solo envío usan el mismo diálogo que los demás.

**Barrido de dónde se crean o editan plantillas (2026-11-25)**:
- **Consola**: `apps/console/src/components/channels/template-composer.tsx` (`TemplateComposer` para crear y `TemplateEditDialog` para editar). Lo abre `templates-section.tsx`, que usan la página de canales del cliente (`app/(console)/clients/[ref]/channels/page.tsx`) y el constructor (`components/builder/channel-templates.tsx`). Un cliente de solo envío pasa por ahí como cualquier otro (077, «Fuera de alcance»).
- **Panel**: `apps/admin/src/app/(dashboard)/tenants/[id]/_integrations/whatsapp-templates-dialog.tsx`, que se abre en la página del número (`channels/[channelId]/page.tsx`). Allí llega también la puesta en marcha de solo envío: el paso «Plantilla de código» de `readiness.ts` enlaza a `/channels`.
- **Fuera de las pantallas**: Reservas pide sus seis plantillas en el servidor (`services/reservations/templates.py`), y su pantalla de la consola lite (`reservas-templates.tsx`) solo enseña el estado. La app móvil no gestiona plantillas.

### Tests (en rojo primero)

- [x] T034 Enmendar la spec (requisito 10, criterio 1.4, D7, «Fuera de alcance» y casos límite) y la 077 (3.3 y 3.4, plan G, I y J, y tareas T007, T028 y T031). _Requisitos: 10.1_
- [x] T035 [P] Tests de `@nexus/ui`:
  - En `packages/ui/src/lib/__tests__/template-rules.test.ts`:
    - `toSubmission` de Autenticación lleva solo el nombre, el idioma, la categoría y `otp_*`, sin caducidad si está vacía;
    - `otpPreviewText` sigue los campos.
  - En `packages/ui/src/components/__tests__/template-editor.test.tsx`:
    - en `create` ofrece Autenticación y, al elegirla, pide el botón, la caducidad y el aviso en lugar del mensaje y los botones;
    - la vista previa enseña el texto fijo en español solo para una plantilla `es*`;
    - una caducidad fuera de 1–90 no se envía;
    - envía `otp_*`;
    - con `initial.otp` («Duplicar») empieza en Autenticación con sus valores y, si el botón venía vacío, con el de por defecto;
    - en `edit` no ofrece Autenticación.

  _Requisitos: 10.1, 10.2, 10.3, 10.4, 1.4_
- [x] T036 [P] Tests de la consola:
  - los cinco de autenticación de la 077 en `template-composer.test.tsx`, sin cambiar sus casos: fallan con el editor compartido sin autenticación (rojo visto el 2026-11-25);
  - en `templates-section.test.tsx`, «Duplicar» de una de autenticación rechazada abre el editor en Autenticación con su botón y su caducidad.

  _Requisitos: 10.1, 10.2, 10.3, 10.4_
- [x] T037 [P] Tests del panel en `whatsapp-templates-dialog.test.tsx`, reescritos contra el editor compartido:
  - «Nueva plantilla» abre el `TemplateEditor`;
  - Utilidad manda la forma de la consola (`body_text`, `buttons`, `examples`), no `components`;
  - Autenticación manda `otp_*`, nunca un cuerpo;
  - una caducidad fuera de rango no llama a la API;
  - el texto fijo solo se previsualiza en español para una plantilla `es*`;
  - `createWhatsAppTemplateAction` exige el operador antes de nada, y lo que no tiene la forma de la consola (con `components`, con `otp`, una de autenticación con cuerpo o un nombre inválido) no llega a la API.

  _Requisitos: 10.1, 10.2, 10.3, 10.5, 10.6_
- [x] T038 [P] Tests de la API:
  - En `apps/api/tests/unit/test_authentication_templates.py`, el alta del panel y la de la consola son el mismo `TemplateCreateIn`, y el del panel ya no acepta `components` ni `otp`.
  - En `apps/api/tests/unit/test_endpoint_admin_template_create.py`, `POST /admin/tenants/{id}/whatsapp/templates`:
    - arma lo que va a Meta con `to_components`: cabecera, pie, botones, ejemplos con nombre y `parameter_format`;
    - arma Autenticación con `otp_*`;
    - responde 422 a `components`;
    - deja la auditoría como hoy.

  _Requisitos: 10.5, 9.3_

### Implementación

- [x] T039 `@nexus/ui`:
  - En `template-rules.ts`:
    - `TemplateSubmission` pasa a ser una unión por categoría;
    - `toSubmission` arma Autenticación;
    - `otpPreviewText` da el texto fijo de Meta en español, uno solo para las dos pantallas.
  - En `template-editor.tsx`:
    - los campos de autenticación y su vista previa (`OtpPreview`, exportada), con los textos en `labels.otp`;
    - Autenticación solo en `create`.

  T035 pasa a verde. _Requisitos: 10.1–10.4, 1.4_
- [x] T040 Consola:
  - `template-composer.tsx` usa solo `TemplateEditor`: el conflicto con la 077 se resolvió sin su formulario propio, y se borraron `OtpFields` y `OtpPreview`;
  - `template-editor-labels.ts` lleva los textos de autenticación;
  - el texto fijo de Meta sale de `@nexus/ui`, así que se quitan del diccionario `tpl.otp.preview.body`, `.security`, `.expiry` y `.expiry.one`;
  - `TemplateEditDialog` estrecha la unión: una de autenticación nunca se edita (3.2).

  T036 pasa a verde. _Requisitos: 10.1–10.4_
- [x] T041 Panel:
  - «Nueva plantilla» abre `TemplateEditor` en un diálogo, como editar;
  - se borran el formulario propio y `otp-template.ts`;
  - `TEMPLATE_EDITOR_LABELS_ES` lleva los textos de autenticación;
  - el alta toma `TemplateSubmission`, y la acción la valida con `zod` estricto antes de llamar a la API.

  T037 pasa a verde. _Requisitos: 10.1, 10.5, 10.6_
- [x] T042 API:
  - `TemplateCreateIn` pasa a `nexus_api/schemas/whatsapp_templates.py`, y `schemas_channels` lo reexporta;
  - `services/whatsapp_templates.create_template` es el alta en Meta, con `to_components` y `parameter_format`;
  - la usan la ruta de la consola y la del panel;
  - se borran `OtpTemplateIn` y el `TemplateCreateIn` del panel;
  - las dependencias de autorización de las rutas no cambian.

  T038 pasa a verde. _Requisitos: 10.5, 9.3_
- [x] T043 [P] Documentación: `docs/canales.md` (el panel crea con el editor completo y con Autenticación) y el quickstart de la 075 (pasos de staging nuevos). _Requisitos: 10.1, 10.5_
- [x] T044 Puertas de la constitución:
  - las cuatro de UI sobre lo nuevo (el editor con Autenticación y el diálogo del panel);
  - `/cso` sobre el cambio de entrada del alta del panel.

  _Requisitos: 10.1, 10.5_

  _Hecho (2026-11-25): las cinco skills, acotadas al diff, en revisión estática (sin navegador). Ningún bloqueante._
  - _`ui-states-checklist`: pasa. Un 🟡, corregido:_
    - _un 422 de validación de la API (`detail` en lista) habría roto el editor del panel al pintarlo;_
    - _`toError` de `setup-actions.ts` ahora da una frase, con prueba._
  - _`a11y-audit`: pasa (axe en las pruebas). El contraste en el render real no está medido: axe lo apaga en jsdom._
  - _`responsive-audit` y `design-tokens`: pasan._
  - _`/cso`: sin hallazgos por encima del umbral._
  - _Notas menores, que no bloquean y quedan para después:_
    - _la caducidad con `type="number"` toma «1e» como vacía (igual que en la 077);_
    - _con la plantilla en otro idioma no se previsualiza el botón;_
    - _cerrar el diálogo descarta lo escrito (como en la consola);_
    - _`sm:max-w-5xl` deja el diálogo de borde a borde entre 640 y ~1056 px;_
    - _`text-primary` en vez de `text-primary-text` en el botón de la vista previa;_
    - _el alta audita `admin:<token>` y no al operador (patrón anterior, 47 rutas);_
    - _el idioma del alta solo se valida por longitud en la API._

- [x] T045 Verificación local:
  - `./scripts/verify.sh lint`;
  - pytest de lo tocado, con base propia (`nexus_test_075`);
  - vitest y `tsc` de `@nexus/ui`, consola y panel;
  - `next build` de los dos.

  _Requisitos: todas_

  _Hecho (2026-11-25), sobre `origin/develop` `e7e6a71d` y otra vez sobre `56837b98` (con la 078, PR 59 y 61, y la 074, PR 60):_
  - _Rojo antes de implementar, por aserción: 11 en `@nexus/ui`, 6 en la consola (los cinco de la 077 y «Duplicar»), 9 en el panel y 6 en la API._
  - _`./scripts/verify.sh lint` en verde._
  - _pytest con `NEXUS_DATABASE_URL=…/nexus_test_075`:_
    - _API: 2162 sobre `e7e6a71d`; 2796 sobre `56837b98`, con además el contrato OpenAPI (Schemathesis), `test_v1_contract` y las pruebas de aislamiento que barren rutas del panel. Las de la primera pasada: `test_authentication_templates`, `test_endpoint_admin_template_create`, `test_endpoint_template_edit`, `test_template_edit_rules`, `test_endpoint_console_channels`, `isolation/test_template_edit_scope`, `isolation/test_console_scope` e `integration/reservas`;_
    - _canales: 30 (`test_meta_client`);_
    - _worker: 34 (`-k cobranza`)._
  - _`scripts/export_openapi.py --check` al día._
  - _vitest: 332 en `@nexus/ui`, 2581 en la consola y 794 en el panel (sobre `56837b98`, con `server-actions-require-operator` de la 078 en verde)._
  - _`tsc` y eslint en verde en los tres; para el panel, antes se compilaron `apps/admin/packages/ucm-*`._
  - _`next build` de la consola y del panel compilan._
  - _El CI del PR 63 encontró tres guardas que las pasadas locales no corrían, las tres de la 075:_
    - _`test_52_partner_never_sees_bodies`: `TemplateButtonOut.phone_number` entra en el inventario de excepciones. Es el número de un botón «Llamar» del propio negocio._
    - _`test_console_audit_words` y `test_every_console_action_written_has_vocabulary`: la migración `0243_template_edit_vocabulary` añade las frases de `console.template.edit` y `admin.template.edit`._
    - _La auditoría de editar guarda también `name` y `language` en `after` (8.4), para que la frase nombre la plantilla; hay prueba, vista en rojo._

---

## Dependencies & Execution Order

- **Fase 2**:
  - T001 → T003.
  - T002 y T004 → T005.
  - T005 → T006.
  - T007 → T008 → T009.
  - T003 y T005 son independientes de T007 a T009.
- **Fase 2b**: T010 se escribe tras T004 y queda en rojo hasta T016.
- **US1**: necesita toda la fase 2.
  - T011 a T014 en paralelo.
  - T015 → T016.
  - T017 en paralelo con T015.
  - T018 depende de T009 y T017.
  - T019 depende de T008 y T016.
- **US2 y US3**: dependen de T015 y T016, porque extienden `edit_template`, y de T008, por el editor. Entre ellas son independientes, salvo que las dos tocan `edit_template` y `template-editor.tsx`: se hacen en serie, US2 y después US3.
- **Fase 6**: al final. T030 puede avanzar en cuanto Meta apruebe la plantilla de prueba.
- **Fase 7**: T034 primero. T035 a T038 en paralelo y en rojo. Después T039, y tras él T040 y T041, que dependen del editor. T042 es independiente de T039 a T041. T043 a T045, al final.

## Parallel Example: User Story 1

```text
T011  tests de la ruta de la consola      (apps/api/tests/unit/test_endpoint_template_edit.py)
T013  tests de la sección de la consola   (apps/console/.../__tests__/templates-section.test.tsx)
T014  tests del diálogo del panel         (apps/admin/.../__tests__/whatsapp-templates-dialog.test.tsx)
T017  backend y acción de la consola      (apps/console/src/lib/backend/channels.ts, actions.ts)
```

## Implementation Strategy

1. Fases 2 y 2b: la API y el editor compartido, con la consola igual que antes.
2. US1 (MVP): rechazadas y pausadas en la consola y el panel. Se valida con el quickstart, paso 1.
3. US2: aprobadas con confirmación.
4. US3: plantillas de sistema.
5. Fase 6: documentación, la prueba de Meta, las puertas de UI, `/cso` y la verificación local.

## Notes

- Los commits los ejecuta la persona: el agente entrega los mensajes y para.
- Cada tarea entregada se anota como `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
