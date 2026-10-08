---

description: "Tareas de la spec 030 — la consola lite del cliente final"
---

# Tasks: la consola lite — el cliente final entra en la misma consola

**Input**: `specs/030-consola-lite-del-cliente/` — [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: NO son opcionales (constitución §VII). Cada bloque «Tests» se escribe y
se ve en rojo antes de su implementación.

## Reglas de este repo *(constitución)*

- Cada tarea termina con `_Requisitos: N.m_` (requisitos de la spec).
- Cada tarea entregada se anota: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- Test primero (§VII). Un barrido de aislamiento en rojo bloquea el merge (§I).
- Una suite de pytest a la vez: comparten base de datos.
- Trabajo en desarrollo y staging; producción cuando el owner promueve.
- **Antes de abrir Consumo o el saldo a un cliente real**, el doble débito del
  tope tiene que estar arreglado (sesión aparte, flujo de bug).

## Format: `[ID] [P?] [Story] Descripción`

- **[P]**: paralelizable (archivos distintos, sin dependencias pendientes).
- **[USn]**: historia de la spec. Rutas relativas a la raíz del repo.

---

## Phase 1: Setup

**Propósito**: lo que todas las historias comparten y no es lógica.

- [X] T001 [P] Crear los carriles de textos vacíos y registrarlos: `apps/console/src/i18n/lanes/lite.ts` y `apps/console/src/i18n/lanes/inbox.ts` (estructura `{es, en}` como los demás carriles), y añadirlos donde `apps/console/src/i18n/messages.ts` agrega los carriles; `no-orphan-keys.test.ts` en verde. _Requisitos: 3.6_
- [X] T002 [P] Empezar la spec viva `docs/consola-lite.md` con el índice (acceso, identidad, rutas lite, Bandeja, multiagente) y enlazarla desde `docs/console.md`; se completa en el mismo commit que cada iteración. _Requisitos: 1.1, 2.1_

---

## Phase 2: Foundational — la identidad de cliente

**Propósito**: sin un usuario de cliente que la API reconozca y la consola pinte, ninguna historia se puede probar.

**⚠️ CRITICAL**: ninguna historia empieza antes de este checkpoint.

### Tests (rojo primero)

- [X] T003 [P] Fábricas de prueba en `apps/api/tests/conftest.py`: `make_client_access(tenant, modules, enabled)`, `make_client_member(tenant, email, status)` y `client_token(member)` que acuña un token de consola con `{sub, partner_id, role: "client"}` con la clave de pruebas existente. _Requisitos: 2.1_
- [X] T004 [P] `apps/api/tests/unit/test_client_principal.py`: `require_client_principal("panel")` da 401 sin token, caducado o repetido; 403 a una persona del partner, a una membresía `revoked`, con `client_access.enabled = false`, con el partner suspendido, con el tenant archivado y sin el módulo pedido; con todo en orden devuelve `ClientPrincipal` con `tenant_id`, `client_ref`, nombre del cliente, módulos, `actor == "client:<correo>"`, y deja `app.tenant_id` fijado en la sesión. **No** exige `partners.console_enabled`. _Requisitos: 2.1, 2.2, 2.4, 2.7_
- [X] T005 [P] `apps/api/tests/unit/test_console_identity_client.py`: `load_principal_view` de una cuenta con membresía de cliente devuelve `kind = "client"`; acceso apagado → `access = "disabled"`; persona revocada → `"suspended"`; `PrincipalOut` lleva `kind`, `client_name`, `modules`, `partner_name`; una cuenta de partner sigue saliendo `kind = "partner"` sin cambios. `POST /console/auth/login` y `/session` devuelven lo mismo. _Requisitos: 2.6, 2.7_
- [X] T006 [P] `apps/api/tests/unit/test_lite_me.py`: `GET /console/lite/me` según [contracts/lite-api.md](contracts/lite-api.md) — `balance_contact` = `{kind: "partner", name}` para cliente de partner y `{kind: "auphere"}` para cliente de Auphere Internal Partner; 403 a una persona del partner. _Requisitos: 2.1, 4.6_
- [X] T007 [P] `apps/console/src/lib/__tests__/principal-access.test.ts`: `toResolution` mapea `kind: "client"` a un `Principal` con `kind`, `clientName`, `modules` y `partnerName`; un payload de cliente sin módulos degrada a `no-membership`. _Requisitos: 2.1, 3.1_
- [X] T008 [P] `apps/console/src/app/__tests__/page-guards.test.ts`: barrido que lee cada `page.tsx` bajo `apps/console/src/app/(console)/` y falla si no llama a `requirePartnerPrincipal` o a `requireClientPrincipal`; un segundo caso comprueba que `requirePartnerPrincipal` lleva a una persona de cliente a su primer módulo y que `requireClientPrincipal("inbox")` lleva al primer módulo si su cliente no tiene Bandeja. _Requisitos: 2.2, 2.4, 3.4_

### Implementación

- [X] T009 Migración `apps/api/alembic/versions/0147_client_access.py` y modelos en `apps/api/src/nexus_api/db/models/client_access.py` (exportados en `db/models/__init__.py`) según [data-model.md](data-model.md): `client_access` (PK `tenant_id`, `modules text[]` con CHECK `modules <@ ARRAY['panel','inbox','usage']`, RLS por tenant), `client_memberships` (`status` CHECK `active|revoked`, índice único `user_id`, índice `tenant_id`), `client_invitations` (`token_hash char(64)` único, `status` CHECK `pending|accepted|revoked|expired`, único parcial `(tenant_id, email) WHERE status = 'pending'`, caducidad 21 días). Permisos para `nexus_app`. _Requisitos: 1.1, 1.4, 2.1_
- [X] T010 `apps/api/src/nexus_api/core/client_auth.py`: `ClientPrincipal` y `require_client_principal(*modules)` (D2): reutiliza `_verify_bearer`, resuelve la membresía en `client_memberships` por `(partner_id, sub)`, comprueba acceso, partner, tenant y módulo, fija el tenant con `apply_tenant_to_session`, enlaza `structlog`. `require_console_principal` no se toca. _Requisitos: 2.1, 2.2, 2.4, 2.5, 2.7_
- [X] T011 `apps/api/src/nexus_api/services/console_identity.py` (`load_principal_view` busca en `client_memberships` cuando no hay membresía de partner) y `apps/api/src/nexus_api/api/console/schemas_auth.py` (`PrincipalOut.kind`, `client_name`, `modules`); auditoría de login/logout con `target = tenant:<id>` para clientes en `apps/api/src/nexus_api/api/console/auth.py`. _Requisitos: 2.6, 2.7_
- [X] T012 Paquete `apps/api/src/nexus_api/api/console/lite/` con `__init__.py` (router `/lite`) y `me.py` (`GET /console/lite/me`), registrado en `apps/api/src/nexus_api/api/console/__init__.py`. _Requisitos: 2.1, 4.6_
- [X] T013 Consola: `apps/console/src/lib/principal-access.ts` (tipo `Principal` con `kind`), `apps/console/src/lib/backend.ts` (`ApiPrincipal`), `apps/console/src/lib/jwt.ts` (acuña `role: "client"` para clientes) y `apps/console/src/lib/principal.ts` (`requirePartnerPrincipal(from?)`, `requireClientPrincipal(module, from?)` y `firstModulePath(principal)`). _Requisitos: 2.1, 2.4, 3.4_
- [X] T014 Sustituir `requirePrincipal` por `requirePartnerPrincipal` en todas las páginas del partner bajo `apps/console/src/app/(console)/` (y en las acciones de servidor y rutas `app/api/*` que hoy lo usan) hasta que T008 pase en verde. _Requisitos: 2.2, 3.3_ · Hecho 2026-10-08 en la rama: las páginas usan `requirePartnerPrincipal`; las acciones de servidor siguen con `requirePrincipal` + `can()`, que ahora responde `false` para `role: "client"` (la API también da 403).

**Checkpoint**: una cuenta de cliente entra, la API la reconoce y ninguna página del partner la deja pasar.

---

## Phase 2b: Las puertas de la constitución

- [X] T015 [P] `apps/api/tests/isolation/test_lite_route_scope.py` — **barrido**: recorre todas las `APIRoute` de `/console/*`; con un token de cliente, todas responden 403 salvo las de `/console/lite/*` y las de servicio (login, sesión, invitaciones, recuperar contraseña); con un token de partner, todas las de `/console/lite/*` responden 403. Ninguna ruta lite acepta `ref`, `tenant_id`, `partner_id` ni `customer_id`. Se vuelve a ejecutar en cada historia porque barre. _Requisitos: 2.2, 2.5, 17.1_
- [X] T016 [P] `apps/api/tests/isolation/test_lite_client_vs_client.py` — **barrido**: dos clientes del mismo partner con datos sembrados; para cada `GET` de `/console/lite/*` el usuario del primero no ve ningún identificador ni nombre del segundo; cada ruta con id de objeto del segundo da 404 idéntico byte a byte al de un id inexistente. _Requisitos: 2.3, 17.3_
- [X] T017 [P] `apps/api/tests/isolation/test_lite_tables_rls.py` — garantía 1: toda tabla creada por 0147–0153 con `tenant_id` tiene RLS `ENABLE` + `FORCE`, y con `app.tenant_id = A` las filas de B no se leen ni se modifican (recorre las tablas desde el catálogo, no una lista escrita). _Requisitos: 2.1, 17.3_ · Hecho 2026-10-08: el barrido de catálogo ya existía (`test_21`) y quedó en rojo con `client_memberships`/`client_invitations`, que son identidad: justificadas allí. `test_lite_tables_rls.py` prueba el comportamiento de `client_access`.
- [X] T018 [P] Ampliar `apps/api/tests/isolation/test_console_scope.py` y crear `apps/api/tests/isolation/test_lite_bodies_only_in_inbox.py` — eje C8: los campos de cuerpo solo se admiten en esquemas de respuesta de `/console/lite/inbox/*`, con la excepción escrita y razonada junto a la del Companion; ninguna persona del partner alcanza esas rutas; ninguna ruta del partner devuelve cuerpos, notas ni archivos. _Requisitos: 2.5, 16.2, 17.2_ — Al ampliar el barrido apareció que **el eje C8 de `test_console_scope.py` era vacío**: `_walk_schema` empezaba en el envoltorio `content → schema` de OpenAPI y no recogía ninguna propiedad, para ninguna ruta (respuestas ni cuerpos de petición). Corregido; los 11 «infractores» que salieron en rutas del partner son vocabularios cerrados (`Literal`) o el error de Meta de un catálogo (`CatalogErrorOut.message`, excepción por esquema razonada). Nuevo control `test_the_walk_reads_real_responses` sobre el OpenAPI real.
- [X] T019 [P] `apps/api/tests/isolation/test_contact_notes_never_reach_agent.py` — **barrido** (D18): falla si `ContactNote` o `contact_notes` aparecen en `apps/worker/src` o `apps/mcp/src`, y si el contexto que arma el despachador para un turno contiene el texto de una nota sembrada. _Requisitos: 13.5_
- [X] T020 [P] `apps/api/tests/isolation/test_agent_scope_within_tenant.py` — garantías 2, 4 y 5: con dos agentes del mismo cliente en dos números, un turno en el número de B recibe solo la lista blanca, el prompt renderizado y la versión de B; la caché del cargador no mezcla agentes; el hilo de LangGraph del número de A no ve los turnos de B; los dos agentes leen el mismo conocimiento del cliente. _Requisitos: 14.3, 14.4, 14.10, 17.4_ — Hecho 2026-10-08, en verde: turno en el número de Ventas con solo su prompt, su lista blanca y su versión; caché del cargador por agente (invalidar uno no tira el otro); un hilo por número; el KG sin dimensión de agente. **Comprobado que no es vacío**: con el turno sin `agent_id` (carga el principal) el primer caso falla. Añadido un quinto caso tras encontrar que una clave foránea de una columna dejaba colgar una versión o un número del cliente A de un agente de B (el admin recibe `agent_id` por la URL): ahora lo rechaza la base de datos (`0155`).
- [ ] T021 Garantía 8: confirmar que ninguna herramienta nueva acepta cliente final como argumento — `apps/api/tests/isolation/test_37_customer_axis_contract.py` sigue barriendo sin cambios y en verde al cerrar cada iteración (esta spec no añade herramientas de agente). _Requisitos: 17.4_ — Iteración 1: verde en `./scripts/verify.sh py` (2026-10-08).
- **Licencias**: puerta sin tarea — el plan no añade ninguna dependencia; se comprueba en la revisión del diff de cada PR.
- **Medidor**: no se añade nada que gaste; la comprobación de que los mensajes de la Bandeja se miden está en T061 y la dimensión agente en T093 y T100.

**Checkpoint**: las puertas tienen dueño. Los barridos T015–T018 quedan en rojo hasta que existan las rutas lite y vuelven a ejecutarse en cada historia.

---

## Phase 3: User Story 1 — Auphere da acceso a un cliente desde el admin (P1) 🎯 MVP · Iteración 1

**Goal**: el operador activa la consola lite de un cliente, elige módulos e invita personas.

**Independent Test**: activar el acceso de un cliente de prueba con Panel y Consumo, invitar un correo, aceptar la invitación y entrar.

### Tests (rojo primero)

- [X] T022 [P] [US1] `apps/api/tests/unit/test_admin_client_access.py` según [contracts/admin-api.md](contracts/admin-api.md): `GET` con `eligible`/`ineligible_reason` (`no_partner`, `archived`) y `whatsapp_connected`; `PUT` con 422 `no_modules`, 422 `inbox_requires_whatsapp`, 409 `no_partner`; apagar el acceso cierra las sesiones de sus personas; 401 sin `X-Operator-Id`; auditoría `actor = operator:<correo>` con vocabulario sembrado. _Requisitos: 1.1, 1.2, 1.3, 1.7, 1.8_
- [X] T023 [P] [US1] `apps/api/tests/unit/test_admin_client_members.py`: invitar envía correo (capturado) y crea `client_invitations` con caducidad de 21 días; 409 `account_is_partner_member`, `account_is_other_client`, `already_member`, `access_disabled`; reenviar revoca el enlace anterior; revocar una persona la pasa a `revoked` y cierra sus sesiones; revocar es idempotente; la lista mezcla personas e invitaciones con su estado. _Requisitos: 1.4, 1.5, 1.6, 1.7, 1.9_
- [X] T024 [P] [US1] `apps/api/tests/unit/test_client_invitation_accept.py`: `GET /console/invitations/{token}` y su aceptación encuentran invitaciones de cliente; aceptar crea la cuenta con la contraseña elegida y la `client_membership`; con cuenta existente pide su contraseña; una cuenta de cliente entra también con Google y la sesión la resuelve como cliente; caducada o revocada responde igual que la del partner; una cuenta de partner no puede aceptar una invitación de cliente (invariante entre tablas, bajo bloqueo consultivo). _Requisitos: 1.4, 1.5, 2.6_
- [X] T025 [P] [US1] `apps/admin/src/app/(dashboard)/tenants/[id]/access/__tests__/access-form.test.tsx`: Bandeja no se puede marcar sin WhatsApp (con su línea), «Guardar» no se activa con el acceso encendido y sin módulos, el diff solo envía lo cambiado, la lista pinta cada estado y el formulario de invitación valida el correo. _Requisitos: 1.1, 1.3, 1.9_

### Implementación

- [X] T026 [US1] Migración `apps/api/alembic/versions/0148_client_audience_vocab.py`: `console_notifications.audience varchar(10) not null default 'partner'` con CHECK `IN ('partner','client')` e índice `(partner_id, audience, external_client_ref, created_at desc)`; siembra en `console_audit_vocabulary` `client_access.updated`, `client_member.invited`, `client_member.resent`, `client_member.revoked`, `client_member.joined` con su frase. _Requisitos: 1.8, 15.1_
- [X] T027 [US1] `apps/api/src/nexus_api/services/client_access.py`: `read_access`, `set_access` (reglas de elegibilidad, ≥ 1 módulo, Bandeja con WhatsApp), `invite`, `resend`, `revoke`, `accept_invitation`; cierre de sesiones con la función que usa el canje de la spec 011; bloqueo consultivo por correo para el invariante partner/cliente. _Requisitos: 1.1–1.7_
- [X] T028 [US1] `apps/api/src/nexus_api/api/admin/client_access.py` (los cinco endpoints del contrato) con una dependencia `require_operator` que exige `X-Operator-Id` resuelto contra la identidad del operador (ADR-034) y registrada en el router de admin. _Requisitos: 1.1–1.9_ · Hecho 2026-10-08: sin operador identificado responde 400, igual que la suplantación (el contrato decía 401).
- [X] T029 [US1] Correo de invitación de cliente en `apps/api/src/nexus_api/services/email.py` («Te dieron acceso a la consola de {cliente}», ES/EN, enlace a `/invite/{token}`) y búsqueda/aceptación de invitaciones de cliente en `apps/api/src/nexus_api/api/console/invitations.py`. _Requisitos: 1.4, 2.6_
- [X] T030 [US1] Admin: métodos en `apps/admin/src/lib/backend.ts` (enviando `X-Operator-Id`), pestaña «Acceso» en `apps/admin/src/app/(dashboard)/tenants/[id]/tabs.tsx`, y `apps/admin/src/app/(dashboard)/tenants/[id]/access/{page.tsx,access-form.tsx,members-list.tsx,invite-form.tsx,actions.ts}` con el patrón de filas + «Guardar» con diff de `agent/runtime-capabilities.tsx` y `react-hook-form` + `zod` para invitar; estados cargando, error y vacío («Nadie tiene acceso todavía»). _Requisitos: 1.1–1.9_
- [X] T031 [US1] Script `apps/api/scripts/dev_seed_client_access.py` (`--client <ref> --modules … --email …`, imprime el enlace) para la consola local y el [quickstart](quickstart.md). _Requisitos: 1.4_

**Checkpoint**: un operador da acceso, la persona acepta y su cuenta existe.

---

## Phase 4: User Story 2 — El cliente entra y ve solo lo suyo (P1) · Iteración 1

**Goal**: la consola lite: solo los módulos del cliente, sin nada del partner.

**Independent Test**: con dos clientes del mismo partner, entrar como usuario del primero e intentar llegar a cualquier pantalla del partner y a cualquier dato del segundo.

### Tests (rojo primero)

- [X] T032 [P] [US2] `apps/console/src/components/shell/__tests__/nav.test.ts`: `navForPrincipal` de un cliente devuelve, en orden, Panel, Bandeja de entrada, Consumo filtrados por sus módulos y sin grupos del partner; de un partner, lo de hoy. _Requisitos: 3.1, 3.3_
- [X] T033 [P] [US2] `apps/console/src/components/shell/__tests__/app-sidebar-lite.test.tsx`: con un cliente, la barra tiene la insignia «lite», al pie el nombre de la persona y el del negocio, y ningún elemento del partner ni del Companion; la paleta ⌘K solo ofrece sus módulos. _Requisitos: 3.1, 3.2, 3.3_
- [X] T034 [P] [US2] `apps/api/tests/unit/test_lite_notifications.py`: el cliente solo ve filas `audience = 'client'` de su `external_client_ref`; el partner deja de ver filas `audience = 'client'`; leído por persona; 403 cruzados; cuando el tope del cliente se agota o queda en riesgo se crea una fila `audience = 'client'` (`client.balance_out` / `client.balance_low`) **solo** si el cliente tiene acceso lite, y su correo va a las personas del cliente, nunca a miembros del partner. _Requisitos: 15.1, 15.2, 15.3_ · **Corrección 2026-10-08**: la parte de emisión (`client.balance_out`/`client.balance_low`) estaba marcada sin existir — ni código ni test. Ahora: `tests/unit/test_client_balance_alerts.py` (rojo visto) y la regla única `lite_home.balance_notice`, compartida por el Panel y la campana.

### Implementación

- [X] T035 [US2] `apps/console/src/components/shell/nav.ts` (`LITE_NAV` y `navForPrincipal`), `apps/console/src/components/shell/app-sidebar.tsx` (insignia «lite», pie con negocio), `apps/console/src/components/shell/console-command-palette.tsx` (entradas lite) y `apps/console/src/app/(console)/layout.tsx` (rama por `principal.kind`: campana lite, sin Companion). Textos en `i18n/lanes/lite.ts`. _Requisitos: 3.1–3.4, 3.6_
- [X] T036 [US2] `apps/api/src/nexus_api/api/console/lite/notifications.py` (cuatro rutas del contrato) filtro `audience = 'partner'` en `apps/api/src/nexus_api/api/console/notifications.py`; emisión de `client.balance_out`/`client.balance_low` con `audience = 'client'` en `apps/api/src/nexus_api/services/wallet_alerts.py` y el riesgo de saldo; `apps/console/src/components/shell/notifications-bell.tsx` usa la ruta lite para clientes. _Requisitos: 15.1, 15.2_ · Hecho 2026-10-08: la lógica de avisos es una sola (`Viewer` en `api/console/notifications.py`) para las dos campanas. · **Corrección 2026-10-08**: emisión real en `services/wallet_alerts.py` — agotado junto al aviso de «cliente sin cupo» del despachador (uno por día) y «no llega a fin de mes» en `evaluate_client_balance_alerts`, llamado por `usage_alerts_cron` (uno por mes); solo clientes con consola encendida, `audience = client`, correo a sus personas.
- [X] T037 [US2] Raíz para clientes en `apps/console/src/app/(console)/page.tsx` (sin Panel → `firstModulePath`) y textos de cliente en `apps/console/src/app/(auth)/no-access/page.tsx` (acceso apagado o revocado). _Requisitos: 2.4, 2.7, 3.4_
- [X] T038 [US2] Ejecutar T015 y T016 contra las rutas existentes y dejarlos en verde. _Requisitos: 2.2, 2.3, 17.1, 17.3_

**Checkpoint**: el cliente entra en su consola lite y no alcanza nada del partner ni de otro cliente.

---

## Phase 5: User Story 3 — El Panel de un solo cliente (P1) · Iteración 1

**Goal**: el Panel con las cifras del partner para ese cliente.

**Independent Test**: con 7 días de actividad sembrada, cada cifra del Panel del cliente coincide con la del partner para ese cliente.

### Tests (rojo primero)

- [X] T039 [P] [US3] `apps/api/tests/unit/test_lite_home.py` según [contracts/lite-api.md](contracts/lite-api.md): paridad al céntimo con `/console/home` y `/console/usage/spend?client=` del partner para el mismo cliente (CE-003); un agente → sin `by_agent`; sin Bandeja → `waiting = null` y sin fila `waiting`; `prev_7d = null` sin semana anterior; `days_left = null` sin gasto; `assigned = false` sin tope; filas `balance_low`/`balance_out`; bloque que falla → `null` y nombre en `errors`. _Requisitos: 4.1–4.8_
- [X] T040 [P] [US3] `apps/console/src/components/lite/__tests__/lite-panel.test.tsx`: cada bloque en cargando (esqueleto con sus medidas), error, parcial, vacío e ideal; saludo con nombre y negocio; sin Bandeja no hay tarjeta ni fila de espera; saldo corto dice a quién pedir (partner o Auphere) sin botón de compra; nada pendiente → una línea. _Requisitos: 4.2–4.8, 3.6_

### Implementación

- [X] T041 [US3] `apps/api/src/nexus_api/services/lite_home.py` que llama a las mismas funciones que `/console/home` (`tenant_snapshots`, `credit_burn`, `allocations_for`, serie diaria) con `[tenant_id]`; extraer de `apps/api/src/nexus_api/api/console/home.py` y `services/console_home_blocks.py` lo que hoy vive dentro del endpoint, sin cambiar su respuesta (sus tests actuales en verde). _Requisitos: 4.1–4.7_
- [X] T042 [US3] `apps/api/src/nexus_api/api/console/lite/home.py` (`GET /console/lite/home`, módulo `panel`). _Requisitos: 4.1–4.8_
- [X] T043 [US3] Consola: `apps/console/src/lib/backend/lite.ts` (`liteApi(call)` con `me` y `home`), `apps/console/src/components/lite/{lite-panel.tsx,lite-greeting.tsx,lite-spend-card.tsx,lite-attention.tsx}` reutilizando `SpendCard`, `HighlightMetric`, `Metric`, `ConversationsChart` y `AttentionBlock`, y la rama de cliente en `apps/console/src/app/(console)/page.tsx`. Solo tokens de `@nexus/ui`. _Requisitos: 4.1–4.8, 3.6_

**Checkpoint**: el Panel lite enseña las cifras del cliente, iguales a las del partner.

---

## Phase 6: User Story 4 — El Consumo de un solo cliente (P1) · Iteración 1

**Goal**: saldo de solo lectura, gasto, gasto por día y detalle técnico del cliente.

**Independent Test**: con gasto sembrado, comparar con el partner para ese cliente y descargar el CSV.

### Tests (rojo primero)

- [X] T044 [P] [US4] `apps/api/tests/unit/test_lite_usage.py`: `summary`, `spend`, `detail` y `export.csv` con paridad con las rutas del partner para ese cliente; `projection_cents = null` cuando no se puede proyectar; el CSV solo trae filas del cliente; ningún esquema lleva saldo del partner, gasto fuera de clientes ni coste propio (`cost_usd`); `agent` de otro cliente → 404. _Requisitos: 5.1–5.6_
- [X] T045 [P] [US4] `apps/console/src/components/lite/__tests__/lite-usage.test.tsx`: tarjetas, gasto por día 7/30/90, detalle plegado y exportar; sin botón de compra, sin «Alertas de consumo», sin tope editable; estados cargando/error/parcial/vacío; vocabulario de dinero de las specs 027/028 (`money-words.test.ts` sigue en verde). _Requisitos: 5.1–5.6_

### Implementación

- [X] T046 [US4] `apps/api/src/nexus_api/services/lite_usage.py` y `apps/api/src/nexus_api/api/console/lite/usage.py` (cuatro rutas del contrato), llamando a las funciones de `api/console/usage.py` y `metering/wallet.py` con el cliente fijo e `include_outside = false`; extraer sin cambiar respuestas del partner. _Requisitos: 5.1–5.6_
- [X] T047 [US4] Consola: `liteApi` gana `usageSummary`, `usageSpend`, `usageDetail`; `apps/console/src/components/lite/lite-usage.tsx` reutilizando `SpendChart`, `SpendControls` (sin selector de cliente) y `MeterList`; ruta BFF `apps/console/src/app/api/lite/usage/export/route.ts`; rama de cliente en `apps/console/src/app/(console)/usage/page.tsx`. _Requisitos: 5.1–5.6_
- [X] T048 [US4] Completar `docs/consola-lite.md` (acceso, identidad, Panel y Consumo) y `docs/console.md` en el mismo commit; cerrar la iteración 1 con T015–T017 y `./scripts/verify.sh` en verde. _Requisitos: 1.1, 2.1, 17.1, 17.3_

**Checkpoint (fin de la iteración 1)**: un cliente entra y ve su Panel y su Consumo.

---

## Phase 7: User Story 5 — La Bandeja: ver y leer (P1) · Iteración 2

**Goal**: lista, hilo, archivos recibidos y tiempo real.

**Independent Test**: con conversaciones sembradas, filtrar, buscar, abrir una y ver llegar un mensaje nuevo sin recargar.

### Tests (rojo primero)

- [X] T049 [P] [US5] `apps/worker/tests/unit/test_conversation_upsert_lifecycle.py` (D11): el alta toma la última fila del contacto en ese número, sea cual sea su estado; `ESCALATED` sigue en la misma fila; `CLOSED` se reabre a `OPEN` con evento `reopened` de `contact`; `last_message_at` se actualiza con entrantes y salientes. _Requisitos: 11.3, 12.2, 7.1_ — *Desviación*: vive en `apps/api/tests/integration/test_conversation_upsert_lifecycle.py` (necesita la base y sus fixtures, como `test_dispatcher_tenant_lifecycle.py`); rojo visto antes de implementar.
- [X] T050 [P] [US5] `apps/api/tests/unit/test_lite_inbox_list.py`: filtros `all|unread|waiting|resolved` (resueltas fuera por defecto), búsqueda por nombre, teléfono y texto, orden `last_message_at desc, id`, cursor, `counts`, `has_any`, `preview` ≤ 140 caracteres con su autor (`contact|agent|member` con `is_me`|`operator`), `state` derivado (D12), sin leer por persona; sin pestañas cuando hay un solo tipo de canal (`channel_kinds`); `GET …/inbox/counts` da `unread` y `waiting` de la persona. _Requisitos: 3.5, 6.1, 6.3, 7.1–7.4, 7.6_ — *Desviación de orden*: la API de la Bandeja (T057, T064, T075, T079, T085) se escribió antes que estos tests; al escribirlos aparecieron y se corrigieron dos fallos reales (`actor_id` = UUID de la membresía, no el `user_id` de texto; el aviso de escalado salía antes del commit → `mark_waiting` + `announce_waiting`).
- [X] T051 [P] [US5] `apps/api/tests/unit/test_lite_inbox_thread.py`: mensajes y eventos intercalados en orden, paginación hacia atrás, metadatos de archivo sin clave de S3, `delivery` y `failure_reason`; `POST …/read` marca leída solo para esa persona. _Requisitos: 8.1–8.5_
- [X] T052 [P] [US5] `apps/api/tests/unit/test_lite_inbox_media_and_stream.py`: `…/messages/{id}/media` sirve los bytes por streaming con su tipo, 404 si es de otro cliente; `…/stream` solo emite eventos de `inbox:{tenant de la sesión}` y manda `ping`. _Requisitos: 7.5, 8.3_
- [X] T053 [P] [US5] `apps/console/src/components/inbox/__tests__/inbox-list.test.tsx` y `thread.test.tsx`: cargando (filas esqueleto), bandeja vacía distinta de «No hay conversaciones con estos filtros», error, «Reconectando…» al caer el SSE, ideal; textos largos recortados sin romper la fila; imagen visible, documento con nombre, audio con transcripción; número de no leídas junto a «Bandeja de entrada». _Requisitos: 3.5, 6.2, 7.2, 7.5, 7.6, 8.1, 8.3_ — Más `inbox-model.test.ts` (decisiones puras) e `inbox-view.test.tsx` (la Bandeja entera con las acciones simuladas: envío optimista, 412, «Reconectando…», reintento).

### Implementación

- [X] T054 [US5] Migraciones `apps/api/alembic/versions/0149_inbox_conversations.py` (`conversations.assigned_user_id varchar(64) null`, `closed_at`, `last_message_at` rellenado con `max(messages.created_at)`, índice `(tenant_id, last_message_at DESC, id)`; tabla `conversation_events` con `kind` `escalated|takeover|released|resolved|reopened|agent_changed`; `actor_kind` admite `member`) y `0150_inbox_tables.py` (`inbox_reads` PK `(conversation_id, user_id)`; `conversation_tags` `tag varchar(40)` PK `(conversation_id, lower(tag))`; `contact_notes` `body ≤ 4.000`; `saved_replies` `title varchar(80)`, `body ≤ 1.000`), todas con RLS `FORCE`; modelos en `apps/api/src/nexus_api/db/models/inbox.py`. _Requisitos: 7.1, 8.5, 12.4, 13.4, 13.5, 10.4_
- [X] T055 [US5] `apps/worker/src/nexus_worker/persistence/messages.py`: alta de conversación de D11 y `last_message_at` en entrantes y salientes. _Requisitos: 11.3, 12.2, 7.1_
- [X] T056 [US5] `apps/api/src/nexus_api/services/inbox_stream.py` (`publish(tenant_id, event)` y `subscribe(tenant_id)` sobre `inbox:{tenant_id}`, según [contracts/realtime.md](contracts/realtime.md)); publicar desde el worker al guardar entrante y mensaje del agente (`apps/worker/src/nexus_worker/runtime/dispatcher.py`, `streams/outbound.py`) y desde el webhook de estados de Meta (`apps/api/src/nexus_api/api/webhooks/meta.py`). _Requisitos: 7.5_
- [X] T057 [US5] `apps/api/src/nexus_api/api/console/lite/{inbox.py,inbox_media.py,inbox_stream.py}`: lista, `counts`, detalle, mensajes, leer, archivos y SSE del contrato (módulo `inbox`). _Requisitos: 6.1, 7.1–7.6, 8.1–8.5_
- [X] T058 [US5] Consola: `liteApi` gana las lecturas de la Bandeja; rutas BFF `apps/console/src/app/api/lite/inbox/stream/route.ts` y `apps/console/src/app/api/lite/inbox/media/[id]/route.ts` (patrón del Playground con `tokenFor`); `apps/console/src/app/(console)/inbox/page.tsx` con `requireClientPrincipal("inbox")`; `apps/console/src/components/inbox/{inbox-view.tsx,conversation-list.tsx,conversation-row.tsx,inbox-filters.tsx,thread.tsx,message-bubble.tsx,media-preview.tsx,use-inbox-stream.ts}`; contador de no leídas en la barra desde `GET …/inbox/counts`, refrescado con los eventos del SSE. Distribución del diseño: lista 320 px, hilo flexible, panel de contacto plegable que arranca plegado por debajo de 1280 px. _Requisitos: 3.5, 6.1–6.3, 7.1–7.6, 8.1–8.5_ — *Desviación de nombres*: los filtros viven en `conversation-list.tsx` y la vista previa de archivos en `message-bubble.tsx` (`MediaPreview`); las URL del navegador en `lib/inbox-urls.ts` (módulo puro: `lib/backend` es solo de servidor y el `next build` lo exige). El contador de no leídas es `components/shell/use-inbox-unread.ts` (al montar, al navegar, cada 60 s visible y al instante cuando la Bandeja anuncia recuentos).

**Checkpoint**: la Bandeja se lee entera y se mueve sola.

---

## Phase 8: User Story 6 — Tomar el control, contestar y devolver (P1) · Iteración 2

**Goal**: la persona entra en la conversación, escribe y se la devuelve al agente.

**Independent Test**: tomar el control, enviar un mensaje que llega al WhatsApp del contacto, devolver y ver que el agente responde sin volver a saludar.

### Tests (rojo primero)

- [X] T059 [P] [US6] `apps/api/tests/unit/test_conversation_control_service.py`: el servicio extraído hace la toma de control y la devolución con `If-Match` (412 con el estado real), `takeover_context`, auditoría con el actor recibido y evento; los tests actuales del admin sobre `PATCH …/agent` siguen en verde. _Requisitos: 9.2, 9.4, 9.5_
- [X] T060 [P] [US6] `apps/api/tests/unit/test_lite_inbox_control_and_send.py`: tomar el control asigna a la persona, silencia al agente y pasa `ESCALATED` a `OPEN`; devolver exige ser quien atiende y deja el `takeover_context`; enviar da 409 `not_assigned_to_you`, `window_closed` (más de 24 h desde `last_inbound_at`) y `channel_disconnected`; el mensaje es `actor_kind = "member"` con `actor_id`; auditoría `inbox.takeover|released|message_sent` con `client:<correo>` y sin texto. _Requisitos: 9.1–9.5, 10.1, 10.2_
- [X] T061 [P] [US6] `apps/worker/tests/unit/test_member_messages.py`: el despachador de salida envía los mensajes `member` como los del operador y los mide como mensaje saliente (`record_channel_message`); al devolver, el resumen para el agente incluye los mensajes `member` desde `started_at`. _Requisitos: 9.3, 10.5_ — *Desviación*: vive en `apps/api/tests/integration/channels/test_member_messages_outbound.py` junto a T083 (necesita la base). El despachador de salida ya enviaba cualquier `pending` sin mirar `actor_kind`: el test fija ese comportamiento; el resumen pasa por `takeover_messages()` (operator + member).
- [X] T062 [P] [US6] `apps/console/src/components/inbox/__tests__/composer.test.tsx` y `apps/console/src/app/(console)/inbox/__tests__/actions.test.ts` (arnés `src/test/actions.ts`): con el agente respondiendo solo se ofrece «Tomar el control»; con la persona, Enter envía y Mayúsculas+Enter salta; ventana cerrada y número desconectado bloquean con su frase; 412 enseña el estado real; mensaje fallido marcado con motivo; las acciones permiten al cliente con Bandeja y niegan sin módulo. _Requisitos: 9.1, 9.4, 10.1, 10.2, 8.4_

### Implementación

- [X] T063 [US6] Extraer `apps/api/src/nexus_api/services/conversation_control.py` de `apps/api/src/nexus_api/api/admin/conversations.py` (que pasa a llamarlo) con el actor como parámetro. _Requisitos: 9.2, 9.4, 9.5_
- [X] T064 [US6] Rutas `takeover`, `release` y `messages` en `apps/api/src/nexus_api/api/console/lite/inbox.py` y migración `apps/api/alembic/versions/0151_inbox_audit_vocab.py` (`inbox.takeover`, `inbox.released`, `inbox.message_sent`, `inbox.attachment_sent`, `inbox.resolved`, `inbox.reopened`, `inbox.tagged`, `inbox.untagged`, `inbox.note_saved`, `inbox.reply_saved` con su frase); la Auditoría del partner las enseña con el nombre de la persona y sin contenido. _Requisitos: 9.1–9.5, 10.1, 10.2, 16.1_
- [X] T065 [US6] Worker: el resumen de la devolución en `apps/worker/src/nexus_worker/runtime/dispatcher.py` incluye `actor_kind = "member"`. _Requisitos: 9.3_
- [X] T066 [US6] Consola: `apps/console/src/components/inbox/{composer.tsx,assign-menu.tsx,thread-header.tsx}` y `apps/console/src/app/(console)/inbox/actions.ts` (`useOptimistic` al enviar, revertido si falla). _Requisitos: 9.1–9.4, 10.1, 10.2_ — *Desviación*: sin `assign-menu.tsx` en esta iteración. Con un agente, quién atiende se dice en la cabecera y el compositor ofrece tomar/devolver; el menú con la lista de agentes del diseño llega con multiagente (iteración 3, T101).

**Checkpoint**: la Bandeja ya sirve para atender.

---

## Phase 9: User Story 7 — Lo que espera a una persona (P2) · Iteración 2

**Goal**: el escalado silencia al agente si hay Bandeja, avisa y no parte el hilo.

**Independent Test**: hacer que el agente pida ayuda y ver el aviso en la campana, la cifra en el Panel y el estado en la Bandeja.

### Tests (rojo primero)

- [X] T067 [P] [US7] `apps/api/tests/unit/test_inbox_lifecycle_mark_waiting.py`: con Bandeja, `mark_waiting` pasa a `ESCALATED`, silencia al agente (`agent_active = false`, `takeover_context.reason = "escalated"`), deja el evento con `reason` y `customer_summary`, publica el evento, crea una notificación `inbox.waiting` con `audience = 'client'` y manda correo a las membresías activas de cliente —nunca a miembros del partner—, una vez por escalado; sin Bandeja, solo estado y evento y el agente sigue; quitar la Bandeja o apagar el acceso devuelve al agente las conversaciones silenciadas por escalado, con evento. _Requisitos: 11.1–11.5, 15.3, 6.1_ — Incluye la devolución al quitar la Bandeja o apagar el acceso (rojo visto antes de T070).
- [X] T068 [P] [US7] `apps/mcp/tests/test_escalate_marks_waiting.py`: `escalate.escalate_to_human` llama a `mark_waiting` y conserva lo de hoy (auditoría, consulta al dueño por el backchannel). _Requisitos: 11.1_ — Rojo visto antes de T071.
- [X] T069 [P] [US7] `apps/console/src/components/inbox/__tests__/waiting.test.tsx`: aviso «Esta conversación espera a una persona» con el motivo y «Tomar el control»; filtro «Necesita humano · N»; la campana enseña el aviso y al pulsarlo abre esa conversación (`/inbox?c=<id>`) con «Tomar el control» a la vista: tres clics del aviso a escribir (CE-005). _Requisitos: 11.1, 11.4, 7.3, 15.1_

### Implementación

- [X] T070 [US7] `apps/api/src/nexus_api/services/inbox_lifecycle.py` (`mark_waiting` y `release_escalated_for_tenant`, al que llama `services/client_access.set_access` al quitar la Bandeja o apagar el acceso) y `audience` en `apps/api/src/nexus_api/services/console_notifications.py` (destinatarios de correo de cliente = membresías activas de cliente del tenant). _Requisitos: 11.1–11.5, 15.1, 15.3_
- [X] T071 [US7] `apps/mcp/src/nexus_mcp/servers/escalate/tools.py` llama a `mark_waiting`. _Requisitos: 11.1, 11.2_
- [X] T072 [US7] Consola: aviso de espera en `apps/console/src/components/inbox/composer.tsx`, filtro y cifra, y enlace del aviso de la campana a la conversación (`/inbox?c=<id>`); el Panel lite ya cuenta `waiting` (T042). _Requisitos: 11.1, 11.4, 4.5_

**Checkpoint**: nadie se entera tarde de que el agente pidió ayuda.

---

## Phase 10: User Story 8 — Resolver, reabrir y marcar como no leída (P2) · Iteración 2

**Goal**: cerrar lo atendido y volver a lo pendiente.

**Independent Test**: resolver, escribir desde el contacto y ver que se reabre con el agente; marcar como no leída.

### Tests (rojo primero)

- [X] T073 [P] [US8] `apps/api/tests/unit/test_lite_inbox_resolve.py`: resolver es idempotente, pone `CLOSED` y `closed_at`, deja de esperar, evento y auditoría; reabrir devuelve al agente (`agent_active = true`, sin persona asignada); `unread` marca solo para esa persona. _Requisitos: 12.1–12.4, 11.5_
- [X] T074 [P] [US8] `apps/console/src/components/inbox/__tests__/resolve.test.tsx`: aviso de resuelta con «Reabrir», aviso breve «Conversación resuelta» con `role="status"`, marcar como no leída vuelve a contar. _Requisitos: 12.1, 12.3, 12.4_

### Implementación

- [X] T075 [US8] `resolve` y `reopen` en `services/inbox_lifecycle.py`; rutas `resolve`, `reopen`, `unread` en `api/console/lite/inbox.py`. _Requisitos: 12.1–12.4_
- [X] T076 [US8] Consola: botones de la cabecera del hilo y acciones en `apps/console/src/components/inbox/thread-header.tsx` y `apps/console/src/app/(console)/inbox/actions.ts`. _Requisitos: 12.1–12.4_

---

## Phase 11: User Story 9 — El panel de contacto (P2) · Iteración 2

**Goal**: resumen, datos, actividad, etiquetas y notas internas.

**Independent Test**: abrir una conversación escalada y otra sin escalar, poner etiquetas y guardar una nota.

### Tests (rojo primero)

- [X] T077 [P] [US9] `apps/api/tests/unit/test_lite_inbox_contact.py`: `summary` y `waiting_reason` del último escalado, `null` sin escalado; `first_message_at` y número de conversaciones (1 + reaperturas por el contacto + filas anteriores del contacto); actividad de la más reciente a la más antigua; `PUT …/tags` recorta, ignora vacíos, sin duplicados sin distinguir mayúsculas, ≤ 20 etiquetas de ≤ 40 caracteres; sugerencias = etiquetas distintas del cliente; `PUT …/note` ≤ 4.000; la auditoría guarda longitudes y nombres de etiqueta, nunca el texto de la nota. _Requisitos: 13.1–13.5, 16.1_
- [X] T078 [P] [US9] `apps/console/src/components/inbox/__tests__/contact-panel.test.tsx`: sin resumen no hay sección; etiquetas con quitar y sugeridas; la nota guarda con estados guardando/guardado/error; el panel se pliega y recuerda su estado (con `try/catch` en el almacenamiento). _Requisitos: 13.1–13.5_

### Implementación

- [X] T079 [US9] Rutas `tags`, `note` y `GET /console/lite/inbox/tags` en `api/console/lite/inbox.py`. _Requisitos: 13.4, 13.5_
- [X] T080 [US9] Consola: `apps/console/src/components/inbox/{contact-panel.tsx,tag-editor.tsx,internal-note.tsx,activity-list.tsx}`. _Requisitos: 13.1–13.5_ — *Desviación de nombres*: `TagEditor`, `InternalNote` y `ActivityList` se exportan desde `contact-panel.tsx`; la redacción de eventos es una sola (`event-text.ts`) para el hilo y la actividad, con verbos propios de segunda persona («Tomaste el control», no «Tú tomó»).
- [X] T081 [US9] Ejecutar T019 en verde. _Requisitos: 13.5_

---

## Phase 12: User Story 10 — Respuestas guardadas y archivos (P2) · Iteración 2

**Goal**: insertar respuestas guardadas y adjuntar imágenes y PDF.

**Independent Test**: crear una respuesta guardada, insertarla y enviar una imagen.

### Tests (rojo primero)

- [X] T082 [P] [US10] `apps/api/tests/unit/test_lite_inbox_replies_and_attachments.py`: respuestas guardadas (`title ≤ 80`, `body ≤ 1.000`) del cliente: crear, editar y `DELETE` que **archiva** (`archived_at`) y deja de listarla (constitución §IV); adjuntos JPEG/PNG ≤ 5 MB y PDF ≤ 16 MB, 415/413 diciendo el límite, guardados con `MediaStorage.put_outbound`, mismos 409 que el texto. _Requisitos: 10.3, 10.4_
- [X] T083 [P] [US10] `apps/worker/tests/unit/test_member_attachments.py`: el despachador de salida envía el archivo de un mensaje `member` por enlace firmado como los del agente. _Requisitos: 10.3_ — En el mismo archivo que T061.
- [X] T084 [P] [US10] `apps/console/src/components/inbox/__tests__/replies-and-files.test.tsx`: elegir una respuesta deja el texto sin enviar; crear, editar y borrar desde el desplegable; el archivo no válido se rechaza antes de subir con el límite. _Requisitos: 10.3, 10.4_

### Implementación

- [X] T085 [US10] Rutas `attachments` y `replies` en `api/console/lite/inbox.py`. _Requisitos: 10.3, 10.4_
- [X] T086 [US10] Consola: `apps/console/src/components/inbox/{saved-replies.tsx,attach-button.tsx}` y ruta BFF de subida `apps/console/src/app/api/lite/inbox/attachments/[id]/route.ts`. _Requisitos: 10.3, 10.4_ — *Desviación*: adjuntar vive en `composer.tsx` (botón + validación antes de subir); la ruta BFF valida otra vez y reenvía multipart.
- [X] T087 [US10] Completar `docs/consola-lite.md` (Bandeja, ciclo de vida, tiempo real) en el mismo commit; cerrar la iteración 2 con T015–T019 y `./scripts/verify.sh` en verde. _Requisitos: 17.1–17.3, 13.5_ — Cerrada 2026-10-08: `./scripts/verify.sh` completo en verde (API 4748, worker 431, channels 61, MCP 123; consola 730 + `next build`; lint tras formatear dos ficheros).

**Checkpoint (fin de la iteración 2)**: la Bandeja completa con un agente.

---

## Phase 13: User Story 12 — Buscar desde cualquier pantalla (P3) · Iteración 2

**Goal**: ⌘K enfoca la búsqueda y Enter abre la Bandeja filtrada.

**Independent Test**: desde el Panel, ⌘K, escribir un nombre y Enter.

- [X] T088 [P] [US12] `apps/console/src/components/shell/__tests__/lite-search.test.tsx`: ⌘K/Ctrl+K enfoca la búsqueda; Enter navega a `/inbox?q=…`; sin módulo Bandeja no hay búsqueda. _Requisitos: 7.4_
- [X] T089 [US12] Búsqueda de la barra superior para clientes en `apps/console/src/app/(console)/layout.tsx` y lectura de `q` en `apps/console/src/app/(console)/inbox/page.tsx`. _Requisitos: 7.4_ — `components/shell/lite-search.tsx` (con `ShortcutKbd`); en `/inbox` se aparta y ⌘K enfoca la búsqueda de la lista. La página se remonta con `key` cuando cambian `?c=`/`?q=`/`?filter=` por navegación real (campana, búsqueda).

---

## Phase 14: User Story 11 — Varios agentes por cliente (P2) · Iteración 3

**Goal**: N agentes por cliente, cada número con su agente, y la Bandeja, el Panel y el Consumo por agente.

**Independent Test**: con dos agentes en dos números, escribir a cada uno, ver que responde su agente, que la Bandeja enseña la etiqueta y que el gasto cae en su fila.

### Tests (rojo primero)

- [X] T090 [P] [US11] `apps/api/tests/integration/test_migration_agents.py`: tras 0152–0153, un agente «Agente principal» por tenant con configuraciones, todas las `agent_configs` con `agent_id`, los canales de rol agente asignados, una versión activa por agente; la migración aborta si queda alguna sin agente. _Requisitos: 14.1, 14.2, 14.8_ — Hecho; en verde con `0155` encima.
- [X] T091 [P] [US11] `apps/worker/tests/unit/test_agent_by_channel.py`: el despachador y el preludio del webhook resuelven el agente por `channel.agent_id`; canal sin agente → agente principal; el cargador cachea por `(tenant_id, agent_id)`; la promoción invalida solo ese agente y un mensaje antiguo con solo `<tenant_id>` invalida todos los del tenant. _Requisitos: 14.3, 14.6_ — Hecho. El suscriptor entiende `<tenant_id>` y `<tenant_id>:<agent_id>`.
- [X] T092 [P] [US11] `apps/api/tests/unit/test_agent_versions_per_agent.py`: `_next_version`, `promote` (archiva solo la activa de ese agente) y `rollback` por agente. _Requisitos: 14.1_ — Hecho, con la decisión de numerar por cliente (ver T097).
- [X] T093 [P] [US11] `apps/worker/tests/unit/test_agent_metering.py`: `usage_turn` lleva `agent_id`; el consumidor lo escribe en `usage_records` y en los asientos de `usage_ledger`; los mensajes del agente guardan `messages.agent_id`. _Requisitos: 14.7_ — Hecho.
- [X] T094 [P] [US11] `apps/api/tests/unit/test_agents_api.py` según [contracts/agents-api.md](contracts/agents-api.md): listar, crear (borrador v1 desde plantilla), renombrar, archivar (409 `agent_has_channels`, `last_agent`); asignar número (409 si no es de rol agente); `?agent=` en Agente, ajustes, Capacidades y Playground, y sin él el agente principal; el hilo de Playground fija su agente; admin con las mismas reglas. _Requisitos: 14.1, 14.2, 14.5, 14.9_ — Hecho 2026-10-08. Ajustes al contrato, escritos en él: el alta lleva `placeholders`; el 409 del número es `channel_send_only` (lo decide `agent_enabled`, no el rol); además `GET …/playground/threads?agent=` (visto en rojo), `agent_id` en el `from-seed` del admin y 404 con el agente de otro cliente (visto en rojo).
- [X] T095 [P] [US11] `apps/api/tests/unit/test_lite_by_agent.py`: con más de un agente, `by_agent` en home y usage suma el total al céntimo y el filtro `agent` de la Bandeja y del gasto por día funciona; con uno, no aparece. _Requisitos: 4.2, 5.3, 14.7_ — Hecho; el filtro `agent` del gasto por día (`/console/lite/usage/spend?agent=`) y `agents` en `/console/lite/me` se escribieron en rojo y luego se implementaron.
- [X] T096 [P] [US11] Vitest de la consola: selector de agente en `apps/console/src/app/(console)/clients/[ref]/__tests__/agent-selector.test.tsx`, «Nuevo agente», agente por número en Canales; en la Bandeja lite, etiqueta y filtro de agente solo con más de uno. _Requisitos: 14.5, 4.2, 5.3_ — Hecho: `clients/[ref]/__tests__/agent-selector.test.tsx` (selector, «Nuevo agente», renombrar/archivar, barra del borrador por agente, pestañas que conservan `?agent=`, «Contesta» por número), `clients/[ref]/agents/__tests__/actions.test.ts`, `components/inbox/__tests__/agents.test.tsx` y el filtro del gasto en `components/lite/__tests__/lite-usage.test.tsx`; en el admin, `agent/__tests__/agent-picker.test.tsx`. **Honestidad**: estas pruebas de la consola se escribieron después de la UI, no se vieron en rojo.

### Implementación

- [X] T097 [US11] Migraciones `apps/api/alembic/versions/0152_agents.py` (tabla `agents` con `name varchar(80)` único entre activos por tenant y `status` `active|archived`, RLS `FORCE`; `agent_configs.agent_id`, unicidad `(agent_id, version)` en lugar de `(tenant_id, version)`, único parcial `(agent_id) WHERE status = 'active'`; `channels.agent_id`; `messages.agent_id`, `usage_records.agent_id`, `usage_ledger.agent_id` anulables; `agent_id` en los hilos de Playground) y `0153_agents_backfill.py` (relleno y comprobación de [data-model.md](data-model.md)); modelo `Agent` en `apps/api/src/nexus_api/db/models/agent.py`. _Requisitos: 14.1, 14.2, 14.8_ — Hecho, con **desviación**: las versiones siguen únicas **por cliente** `(tenant_id, version)` (decisión en `data-model.md`), no `(agent_id, version)`; el único parcial `(agent_id) WHERE status = 'active'` sí. Añadida `0155_agents_tenant_fk.py`: unicidad `(tenant_id, id)` en `agents` y claves `(tenant_id, agent_id)` desde `agent_configs` (CASCADE) y `channels` (`SET NULL (agent_id)`, Postgres 15+).
- [X] T098 [US11] `apps/api/src/nexus_api/repositories/agent_config.py` por agente y `apps/api/src/nexus_api/services/agents.py` (crear con `stage_from_seed`, renombrar, archivar con sus reglas, asignar número, agente principal). _Requisitos: 14.1, 14.2, 14.5, 14.9_ — Hecho; el repositorio rechaza además un agente que no es activo del cliente (`UnknownAgent`).
- [X] T099 [US11] Runtime: `apps/api/src/nexus_api/api/webhooks/meta.py` (preludio por agente del número), `apps/worker/src/nexus_worker/runtime/{dispatcher.py,agent_loader.py,promote_subscriber.py}`, publicación de la promoción con `<tenant_id>:<agent_id>` en todos los sitios que hoy la publican, y crones sin canal (`cobranza_reminder_cron.py`, `continuous_eval_cron.py`, `operator_alerts.py`, revisores de pagos en `apps/mcp/src/nexus_mcp/servers/payments/tools.py`) con el agente del canal o el principal. _Requisitos: 14.3, 14.4, 14.6_ — Hecho, con **una decisión**: quien publica la promoción sigue mandando `<tenant_id>` (siete sitios: promoción, modelos, zona horaria, alta de cliente…), lo que invalida la caché de **todos** los agentes del cliente. Es correcto —solo cuesta una relectura por agente— y cambiarlo no aporta nada más que riesgo; el suscriptor ya acepta `<tenant_id>:<agent_id>` si algún día hace falta.
- [X] T100 [US11] Medidor: `apps/worker/src/nexus_worker/metering/{collector.py,consumer.py}` con `agent_id`; `messages.agent_id` en `apps/worker/src/nexus_worker/persistence/messages.py`; gasto por agente en `apps/api/src/nexus_api/metering/wallet.py`. _Requisitos: 14.7_ — Hecho.
- [X] T101 [US11] Consola del partner: `apps/api/src/nexus_api/api/console/agents_list.py` y `PATCH …/channels/{id}/agent` en `api/console/channels.py`; `?agent=` en `agents.py`, `agent_drafts.py`, `agent_settings.py`, `capabilities_client.py`, `playground.py`; UI con selector en `apps/console/src/app/(console)/clients/[ref]/layout.tsx` (barra de borrador), `agent/`, `capabilities/`, `playground/`, diálogo «Nuevo agente» y agente por número en `channels/`. _Requisitos: 14.1, 14.2, 14.5, 14.9_ — Hecho. `PATCH …/channels/{id}/agent` vive en `agents_list.py`, no en `channels.py`. UI: `components/clients/{agent-switcher,new-agent-dialog,agent-draft-bars}.tsx`, `clients/[ref]/agents/actions.ts`, `?agent=` leído en `agent/`, `capabilities/` y `playground/` (`data.ts: agentChoice`), «Contesta» en `channels/channel-card.tsx`. El modelo de lenguaje sigue siendo del cliente.
- [X] T102 [US11] Admin: `apps/api/src/nexus_api/api/admin/agents.py` y `?agent_id=` en `api/admin/agent_configs.py`; selector y «Nuevo agente» en `apps/admin/src/app/(dashboard)/tenants/[id]/agent/`. _Requisitos: 14.1, 14.5_ — Hecho: `agent-picker.tsx` en la pestaña Agente; editor y «Aplicar plantilla» guardan en el agente elegido.
- [X] T103 [US11] Lite: `by_agent` en `services/lite_home.py` y `services/lite_usage.py`, filtro `agent` y etiqueta en la Bandeja (`api/console/lite/inbox.py`, `components/inbox/conversation-row.tsx`, `inbox-filters.tsx`), desglose por agente en `components/lite/`. _Requisitos: 4.2, 5.3, 14.7_ — Hecho. No hay `services/lite_usage.py` ni `inbox-filters.tsx`: el desglose del Consumo vive en `api/console/lite/usage.py` y el filtro en `components/inbox/conversation-list.tsx`; la cabecera del hilo nombra al agente.
- [X] T104 [US11] Ejecutar T020 en verde; completar `docs/consola-lite.md` y la nota de KB `architecture/agent-assembly.md` (agente ↔ número) en el mismo commit. _Requisitos: 14.3, 14.4, 17.4_ — Hecho: T020 en verde; `docs/consola-lite.md` («Varios agentes por cliente») y KB `architecture/agent-assembly.md` actualizados.

**Checkpoint (fin de la iteración 3)**: varios agentes por cliente, cada uno en sus números.

---

## Phase 15: Polish & verificación

- [ ] T105 [P] `apps/console/e2e/lite.spec.ts`: como usuario de cliente (`E2E_CLIENT_EMAIL`/`E2E_CLIENT_PASSWORD`), axe sin incidencias graves ni críticas en `/`, `/inbox` y `/usage`, sin desbordes a 360 y 1920 px, ES y EN, claro y oscuro. _Requisitos: 3.6, 2.2_
- [X] T106 Pasar sobre las pantallas lite los cuatro filtros del Workspace en orden: `ui-states-checklist`, `a11y-audit`, `responsive-audit` (incluido el texto alemán de +30 %), `design-tokens`; sin ningún rojo pendiente. _Requisitos: 3.6_ — Hecho 2026-10-08 **por inspección del código** (la base local de desarrollo está en otra rama de migraciones): 5 estados 8/10 (arreglados: reintentar la lista, volver a «todas», sesión caducada → la guarda decide, imagen rota); WCAG 2.2 AA en papel 6/10 (arreglados: panel modal bajo el ancho de columna —2.4.11—, anillo de foco del compositor, «Reconectando…» anunciado); adaptable 8/10 (arreglados: respuestas guardadas a 360 px, imagen y audio dentro de la burbuja, `title` en lo recortado, columna o panel por el ancho de la Bandeja); tokens 7/10 (arreglado: burbuja del agente ilegible en oscuro). Falta la verificación en vivo: `e2e/lite.spec.ts` (T105). **Iteración 3** (2026-10-08, por inspección): sin rojos. Arreglado lo importante: «Contesta» ya no reasigna el número al cambiar el desplegable (una flecha en un desplegable cerrado lo hacía) y pide confirmación; el error de archivar y de reasignar se dice dentro del diálogo, y archivar un agente con números lo dice antes de confirmar; «Reintentar» si las plantillas no cargan; aviso al renombrar; `title` en «Atiende: …»; si la lista de agentes no se puede leer, el agente de la URL pasa a la API en vez de caer en silencio en el principal; el desplegable del admin con el anillo de foco de su `Input`. Queda de pulido, anterior a esta spec: el anillo de foco de `NativeSelect` en `@nexus/ui` es de 1 px más un halo al 30 %.
- [X] T107 `/cso` y `tenant-security-audit` sobre el diff (toca autenticación, aislamiento y archivos); ningún HIGH/CRITICAL sin mitigar. _Requisitos: 2.1–2.5, 17.1–17.4_ — Hecho 2026-10-08: `/cso` (sin hallazgos ≥ 8/10; endurecido el servir archivos con el tipo que declara el remitente y corregido el 500 con nombres no latin-1) y `tenant-security-audit` (SAFE TO SHIP para iteraciones 1–2; la 3 depende de T020). **Iteración 3** (2026-10-08): `tenant-security-audit` SAFE TO SHIP, 0 críticos y 0 altos. El medio (las lecturas por agente del Consumo lite fuera de la RLS, solo con el filtro escrito a mano) está arreglado: van en una sesión del cliente (`tenant_scoped_session`) y conservan el filtro. Además, `agent_scope` comprueba el cliente aunque la RLS ya lo haga, y una prueba usa el agente real de un cliente vecino (404 en el gasto, lista vacía en la Bandeja). Antes de la auditoría ya se había cerrado, con `0155`, que una versión o un número pudiera apuntar al agente de otro cliente.
- [X] T108 Rendimiento: sembrar 5.000 conversaciones en un cliente y medir la primera página de la Bandeja (< 1,5 s p95, CE-007), la latencia de un mensaje nuevo (< 5 s, CE-004) y el Panel lite (< 1 s p95). _Requisitos: 7.1, 7.5, 4.1_ — Hecho 2026-10-08 en local, en `apps/api/tests/integration/test_lite_performance.py` (se queda en la suite): primera página p95 165 ms, «Necesita humano» 25 ms, búsqueda 31 ms, Panel lite 44 ms ([evidencia](evidence/T108-rendimiento.md)). **Falta** la latencia de un mensaje nuevo (CE-004), que depende del worker y del SSE: se mide en staging con T110.
- [ ] T109 Regresión del multiagente: la batería de evaluación de los clientes existentes da el mismo resultado antes y después de 0152–0153 (CE-006). _Requisitos: 14.8_
- [ ] T110 Recorrer el [quickstart](quickstart.md) en la consola local con datos sembrados y luego en staging, con evidencia en `specs/030-consola-lite-del-cliente/evidence/`; `./scripts/verify.sh` en verde. _Requisitos: 1.1–17.4_

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (1)** → **Foundational (2)** → **Puertas (2b)** → historias.
- **Iteración 1**: US1 → US2 → US3 ∥ US4 (US3 y US4 en paralelo tras US2).
- **Iteración 2** (necesita la 1): US5 → US6 → US7 ∥ US8 ∥ US9 ∥ US10 → US12.
- **Iteración 3** (necesita la 2 para la parte de la Bandeja; el runtime T097–T100 puede empezar tras la iteración 1): US11.
- **Polish** al final de cada iteración que se quiera llevar a staging (T105–T107, T110), y T108–T109 al final.

### Dependencias fuera de la spec

- **Doble débito del tope** (sesión aparte, flujo de bug) antes de abrir Consumo o el saldo a un cliente real.

### Within Each User Story

- Tests en rojo → modelos → servicios → rutas → UI. Los barridos T015–T020 se vuelven a ejecutar al cerrar cada historia.

### Parallel Opportunities

- Todas las tareas de tests marcadas [P] de una historia, juntas.
- En la iteración 1, US3 (Panel) y US4 (Consumo) en paralelo.
- En la iteración 2, tras US6: US7, US8, US9 y US10 tocan archivos de UI distintos; las rutas API comparten `api/console/lite/inbox.py`, así que su implementación va en serie.
- En la iteración 3, runtime (T099–T100), consola del partner (T101) y admin (T102) en paralelo tras T097–T098.

---

## Parallel Example: User Story 5

```bash
Task: "test_conversation_upsert_lifecycle.py en apps/worker/tests/unit/"
Task: "test_lite_inbox_list.py en apps/api/tests/unit/"
Task: "test_lite_inbox_thread.py en apps/api/tests/unit/"
Task: "test_lite_inbox_media_and_stream.py en apps/api/tests/unit/"
Task: "inbox-list.test.tsx y thread.test.tsx en apps/console/src/components/inbox/__tests__/"
```

---

## Implementation Strategy

### MVP (iteración 1: US1–US4)

Acceso desde el admin, entrada del cliente, Panel y Consumo de un cliente.
Reutiliza casi todo lo que existe y abre la frontera nueva con sus barridos. Se
valida en local y staging; a un cliente real solo tras el arreglo del doble
débito.

### Entrega incremental

1. Iteración 1 → staging → demo al owner.
2. Iteración 2 (Bandeja con un agente) → staging → primer cliente con WhatsApp.
3. Iteración 3 (varios agentes) → staging → regresión CE-006 → producción cuando el owner promueve.

## Notes

- [P] = archivos distintos, sin dependencias pendientes.
- Los commits los ejecuta la persona: el agente entrega el mensaje y para.
- Cada iteración actualiza `docs/consola-lite.md` en el mismo commit que cambia lo que describe.
