# Tasks: el número se puede mover

**Input**: documentos de diseño de `/specs/021-el-numero-se-puede-mover/`

**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/unlink.md

**Tests**: NO son opcionales (constitución §VII): cada bloque se escribe
primero, se ve en rojo, y solo entonces se implementa.

**Organization**: por historia. H1 = un número desvinculado no ocupa sitio ·
H2 = desvincular deshace en Meta · H3 = si Meta falla, se sabe. **H2 y H3 se
entregan juntas**: separarlas dejaría el modo de fallo sin cubrir (plan,
§Orden de entrega).

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: termina con `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: rama, YYYY-MM-DD`.
- **Test primero (§VII)**; **aislamiento (§I)** con tarea propia (T-ISO);
  **licencias (§VIII)**: ninguna dependencia nueva (T-LIC); **medidor**: nada
  gasta (T-MET).
- **Cierre**: tests rojos → código → suites en verde → paridad → evidencia →
  log de sesión en la KB → merge a `develop` → staging.

## Format: `[ID] [P?] [Story] Description`

## Path Conventions

API en `apps/api/src/nexus_api/` con tests en `apps/api/tests/{unit,integration,isolation}/`;
cliente de Meta en `apps/channels/src/nexus_channels/whatsapp_meta/`; consola
en `apps/console/src/` con tests junto al código; KB en
`/Users/matos/workspace/kb/Auphere/nexus/`.

---

## Phase 1: Setup

- [X] T001 [P] Crear `specs/021-el-numero-se-puede-mover/evidence/README.md` y anotar en `parity.md` qué hacía desvincular en la spec 019 (marcar la fila, conservarla, no tocar Meta) y qué de eso cambia: **nada se retira** — la fila se sigue conservando; se añade lo que faltaba. _Requisitos: ninguno — ritual de cierre_ Entregado: rama 021, 2026-09-29 — `evidence/README.md` y `parity.md`: nada de la 019 se retira; se añade lo que faltaba.
- [X] T002 [P] T-LIC · `pnpm-lock.yaml` y `uv.lock` no cambian en toda la spec. Se corre al abrir y al cerrar. _Requisitos: ninguno — puerta §VIII_ Entregado: rama 021, 2026-09-29 — hashes de `pnpm-lock.yaml` y `uv.lock` en `evidence/locks-at-open.sha256`; se comparan al cerrar.
- [X] T003 [P] T-MET · Test en `apps/api/tests/unit/test_endpoint_console_channels.py` de que desvincular **no** escribe ningún evento de consumo: las llamadas a Meta no son modelo, reloj ni herramienta de pago. _Requisitos: ninguno — puerta del medidor_ Entregado: rama 021, 2026-09-29 — `test_disconnect_costs_nothing_the_meter_sees`: cero filas en `usage_events` antes y después.

---

## Phase 2: Foundational

- [X] T004 T-ISO · `apps/api/tests/isolation/test_channel_number_scope.py`: con dos tenants, (a) la fila desvinculada de A **no bloquea** el alta de B y B no puede leerla ni alterarla; (b) con el número **vivo** en A, el 409 que recibe B lleva `number_in_use` y **nada más** —ni tenant, ni partner, ni nombre—; (c) desvincular con un id de canal ajeno es 404; (d) **barrido**, no enumeración: recorrer todas las rutas de canal montadas bajo `/console/clients/{ref}/channels` y afirmar que ninguna acepta `tenant_id` ni `partner_id` en parámetros ni en cuerpo, como hizo la 019 con el alta. _Requisitos: 1.2, 1.4, 1.5 · puerta §I_ Entregado: rama 021, 2026-09-29 — cuatro casos, el cuarto barre las 9 rutas de canal por OpenAPI. Dos trampas del arnés quedaron anotadas en el propio test: la sesión rota tras un `IntegrityError` hay que `rollback`-ear y releer con consulta, y `session.get` contesta desde la caché de identidad sin pasar por la RLS.
- [X] T005 [P] `deregister_phone(phone_number_id, access_token)` en `apps/channels/src/nexus_channels/whatsapp_meta/meta_client.py` → `POST /{phone_number_id}/deregister`, con test unitario sobre el cliente HTTP simulado (200 → dict; 4xx → la excepción que ya lanza el resto). Existe `unsubscribe_app`; falta su pareja. _Requisitos: 2.1_ Entregado: rama 021, 2026-09-29 — `deregister_phone` en `meta_client.py`, dos tests con `respx` (sin cuerpo, y el rechazo de Meta sube como `MetaAPIError`).

---

## Iteración 1 · Un número desvinculado no ocupa sitio (H1) 🎯 MVP

**Goal**: el índice deja de contar los desvinculados. Se puede soltar a
producción sin tocar Meta: lo único observable que cambia es que B deja de
recibir un «en uso» falso.

**Independent Test**: A desvincula, B conecta, A conserva su historial.

### Tests primero

- [X] T006 [P] [US1] Test en `apps/api/tests/unit/test_endpoint_console_whatsapp.py`: B conecta un número que A desvinculó → **201**; la fila de A sigue existiendo, `disconnected`, con su mismo id; la de B es otra. **Este test cubre también R4.1**: B llega al 201 sin ningún paso de aprobación por medio. _Requisitos: 1.1, 1.2, 4.1_ Entregado: rama 021, 2026-09-29 — rojo con `409 number_in_use` antes del índice, verde después. Simula solo `build_meta_client`, no el orquestador, para que el upsert corra contra la base.
- [X] T007 [P] [US1] Test: A desvincula y **vuelve a conectar** → recupera **el mismo** `channel.id`, y las conversaciones que colgaban de él siguen colgando. Ya se comporta así (el lookup no filtra por estado): el test lo fija para que nadie lo «arregle». _Requisitos: 1.3_ Entregado: rama 021, 2026-09-29 — ya era verde; queda fijado.
- [X] T008 [P] [US1] Test: con el número **vivo** en A, B conecta → **409** `number_in_use`; A no cambia en nada; el cuerpo no nombra a A. _Requisitos: 1.4, 1.5_ Entregado: rama 021, 2026-09-29 — el 409 no lleva ni tenant ni partner de A.

### Implementación

- [X] T009 [US1] Migración `apps/api/alembic/versions/0132_number_unique_when_live.py`: `DROP CONSTRAINT uq_channels_type_provider_id` y `CREATE UNIQUE INDEX uq_channels_live_number ON channels (type, provider_identifier) WHERE status <> 'disconnected'`. **La bajada se niega** si hay dos filas con el mismo número: mejor un `downgrade` que no corre que uno que borra. Id de revisión ≤ 32 caracteres. _Requisitos: 1.1, 1.2_ Entregado: rama 021, 2026-09-29 — `0132_number_unique_when_live` (28 caracteres), aplicada en `nexus` y `nexus_test`; la bajada se niega ante duplicados.
- [X] T010 [US1] `apps/api/src/nexus_api/db/models/channel.py`: sustituir el `UniqueConstraint` en `__table_args__` por `Index("uq_channels_live_number", …, unique=True, postgresql_where=…)`, con el comentario de por qué. _Requisitos: 1.1, 1.2_ Entregado: rama 021, 2026-09-29 — `Index(..., unique=True, postgresql_where=text("status <> 'disconnected'"))`.
- [X] T011 [US1] `apps/api/src/nexus_api/api/console/whatsapp.py`: `_NUMBER_UNIQUE` pasa a buscar `uq_channels_live_number`. Sin esto, el 409 se convierte en 500 el día que el índice cambie de nombre — y T008 lo vería. _Requisitos: 1.4_ Entregado: rama 021, 2026-09-29 — `_NUMBER_UNIQUE = "uq_channels_live_number"`.

---

## Iteración 2 · Desvincular deshace en Meta, sin quedarse a medias (H2 + H3)

**Goal**: dar de baja el número; desuscribir la app solo si era el último de
su WABA; borrar las credenciales que toquen; y si Meta falla, dejarlo escrito
y reintentable.

**Independent Test**: desvincular con Meta simulado en tres modos —bien, con
hermano vivo, caído— y leer el canal después.

### Tests primero

- [X] T012 [US2] [US3] **Este va primero, por ser el modo de fallo nuevo.** Test en `apps/api/tests/unit/test_endpoint_console_channels.py`: con el cliente de Meta simulado **fallando**, desvincular → 200, canal `disconnected`, `unlink_pending == ["deregister", …]`, y `channel_agent_enabled` es falso. Nada de Meta llegó y el partner lo sabe. _Requisitos: 3.1_ Entregado: rama 021, 2026-09-29 — Meta caído: 200, `disconnected`, `unlink_pending == [deregister, unsubscribe]`, `agent_enabled` falso. Destapó que `agent_enabled` leía `config` y no el estado: un canal desvinculado decía «atiende». Corregido en `_detail`.
- [X] T013 [P] [US2] Test: último número vivo de su `waba_id` en el tenant → Meta recibe `deregister` **y** `unsubscribe`; `config_encrypted` del canal y `tenant_credentials` quedan borrados; `unlink_pending` vacío. _Requisitos: 2.1, 2.2_ Entregado: rama 021, 2026-09-29 — `deregister` + `unsubscribe`; credencial del canal y del tenant borradas; sin pendientes.
- [X] T014 [P] [US2] Test: con un **hermano vivo** bajo la misma `waba_id` → Meta recibe `deregister` y **no** `unsubscribe`; `tenant_credentials` intactas; el hermano sigue `active` y `channel_agent_enabled`. _Requisitos: 2.3_ Entregado: rama 021, 2026-09-29 — con hermano vivo solo `deregister`; credencial del tenant intacta; el hermano sigue `active`.
- [X] T015 [P] [US3] Test: sobre un canal `disconnected` con `unlink_pending`, un segundo `POST …/disconnect` con Meta ya bien **termina lo pendiente** y vacía la lista; sobre uno sin pendientes, no llama a Meta y devuelve 200. _Requisitos: 3.2_ Entregado: rama 021, 2026-09-29 — el segundo POST termina lo pendiente sin repetir lo hecho; sin pendientes no llama a Meta.
- [X] T016 [P] [US3] Test: la fila de auditoría de `console.channel.disconnect` lleva `after.meta == {"done": [...], "pending": [...]}`. _Requisitos: 3.3_ Entregado: rama 021, 2026-09-29 — `after.meta == {done, pending}`; la fila viaja con la segunda transacción (la que sabe qué pasó en Meta).
- [X] T017 [P] [US2] Test de que **el estado se escribe antes que Meta**: si el proceso muere entre la primera transacción y la llamada (simulado con una excepción tras el primer commit), la fila queda `disconnected` con `unlink_pending` completo. Es la razón de las dos transacciones (research D2). _Requisitos: 3.1_ Entregado: rama 021, 2026-09-29 — la fábrica del cliente revienta antes de Meta: el endpoint falla **y** la fila ya está `disconnected` con todo pendiente.

### Implementación

- [X] T018 [US2] `apps/api/src/nexus_api/api/console/schemas_channels.py`: `unlink_pending: list[str] = []` en `ChannelDetailOut`, leído de `config`. _Requisitos: 3.2_ Entregado: rama 021, 2026-09-29 — `unlink_pending: list[str]` leído de `config`.
- [X] T019 [US2] [US3] `apps/api/src/nexus_api/api/console/channels.py` — desvincular en dos transacciones: (1) marcar `disconnected`, calcular si es el último de su `waba_id` **bajo RLS y excluyéndose a sí mismo**, escribir `unlink_pending`, auditar, commit; (2) por cada paso pendiente llamar a Meta con las credenciales del canal o, si no tiene, las del tenant; quitar el paso al terminar; borrar `config_encrypted` tras `deregister` y `tenant_credentials` tras `unsubscribe`; commit. Un fallo de Meta **no** es error HTTP: queda en la lista. El mismo endpoint sobre un canal ya desvinculado reintenta lo pendiente. _Requisitos: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3_ Entregado: rama 021, 2026-09-29 — dos **sesiones propias** con `tenant_scoped_session` (el `client_scope` envuelve el endpoint en una sola transacción, así que las dos fases no podían salir de `scope.session`). Regla que los tests obligaron a decidir: un canal **sin credencial alguna** nunca estuvo atado a nuestra app → los pasos se anotan `skipped`, no pendientes para siempre.
- [X] T020 [US1] `apps/api/src/nexus_api/api/console/whatsapp.py`: cuando Meta rechaza el alta porque el número sigue en otra cuenta, devolver **409 `number_held_by_previous_owner`** en vez del mensaje genérico; con test. _Requisitos: 4.2_ Entregado: rama 021, 2026-09-29 — `RegisterPhoneError` → 409 `number_held_by_previous_owner` con su frase. **Pendiente de verificar en staging** que ese es el error que Meta devuelve cuando el número sigue en otra cuenta.

---

## Iteración 3 · La tarjeta lo dice, y B entiende el rechazo

### Tests primero

- [X] T021 [P] [US3] Test en `apps/console/src/components/channels/__tests__/channel-card.test.tsx`: con `unlink_pending` no vacío, la tarjeta dice qué queda pendiente en Meta y ofrece **reintentar**; con la lista vacía, no. Y el diálogo de desvincular ya no dice «sigue registrado en Meta» a secas: dice que se da de baja de nuestra aplicación, que **sacarlo de tu cuenta de Meta** se hace en el Business Manager, y —si el canal está en coexistencia— que **seguirá chateando desde su teléfono**. _Requisitos: 3.2, 2.4, 2.5_ Entregado: rama 021, 2026-09-29 — 5 tests de pendiente/reintento + 2 del diálogo (`disconnectBodyKey`, coexistencia). El menú sigue sin abrirse bajo jsdom: lo que se fija es la copia y el botón de reintentar, que sí se pulsa.
- [X] T022 [P] [US1] Test en `apps/console/src/components/channels/__tests__/whatsapp-connect.test.tsx`: el 409 `number_held_by_previous_owner` se enseña con su frase —el dueño anterior tiene que soltarlo en Meta— y no como fallo de la consola. _Requisitos: 4.2_ Entregado: rama 021, 2026-09-29 — `signupFailureKey()` como costura pura: el diálogo de Base UI tampoco se abre bajo jsdom, y la clave es lo que hay que fijar. La frase nombra al Business Manager, no dice «error» ni «fallo», y no dice de quién es el número.

### Implementación

- [X] T023 [US3] `apps/console/src/lib/backend/channels.ts`: `unlink_pending`. `apps/console/src/components/channels/channel-card.tsx`: el estado pendiente y el botón de reintentar (reusa `disconnectChannelAction`). `apps/console/src/i18n/lanes/channels.ts`: la copia de pendiente, reintento, el diálogo corregido y `number_held_by_previous_owner`, en ES y EN. _Requisitos: 2.4, 3.2, 4.2_ Entregado: rama 021, 2026-09-29 — `Callout` de aviso con lo que falta y **Reintentar** (solo con `channels:write`; lo pendiente se enseña a todos). Visto en local: reintentar → «Terminado en Meta.» y la tarjeta limpia. Desvincular avisa ya en el toast si algo quedó pendiente.
- [X] T024 [US1] `apps/console/src/components/channels/whatsapp-connect.tsx`: traducir el código nuevo del 409. _Requisitos: 4.2_ Entregado: rama 021, 2026-09-29 — `number_held_by_previous_owner` → `ch.connect.heldByPreviousOwner`.

---

## Cierre

- [X] T025 Recorrer `quickstart.md`: CE-001, 002, 003 y 006 **en local**; CE-004 y 005 **en staging con número real** — incluida la verificación de research D5 (`deregister` sobre un número en coexistencia). Anotar en `evidence/iteracion-1.md` qué se vio en cada uno. _Requisitos: todos · CE-001–006_ Recorrido 2026-09-29 — CE-001/002/003/006 en local (Meta simulado + tarjeta en el navegador), anotado en `evidence/README.md`. **CE-004, CE-005, R4.2 y D5 quedan para staging con el número real**, con el owner delante: no se pueden cerrar sin Meta. _21:28: el owner desvinculó el número real: Meta rechazó `deregister` (coexistencia) y la tarjeta lo dijo. D5 medido y corregido; CE-004 **cerrado** tras `7070426`: el reintento desuscribió y la tarjeta quedó limpia. 22:26: CE-001 y CE-002 cerrados con número real (otro cliente, y vuelta al mismo). CE-005 sin segundo número; R4.2 sin caso._
- [X] T026 Paridad al 100 %, log de sesión en la KB, merge a `develop`, staging. Suites: API (canales, whatsapp, aislamiento y la completa en CI), consola, e2e. _Requisitos: ninguno — ritual de cierre_ Cerrado 2026-09-29 — paridad 100 %, locks idénticos a la apertura, log en la KB (`sessions/2026-09-29-spec-021-el-numero-se-puede-mover.md`), merge a `develop`. Suites: API canales+whatsapp+aislamiento 47 ✅ (la completa la corre CI); consola 525 ✅; `@nexus/ui` 168 ✅. E2E no tocado: la tarjeta pendiente necesita un número real.

---

## Dependencias

- **T009 → T010 → T011**: el índice, el modelo y la constante del 409 van juntos; sin T011, T008 se pone rojo con un 500.
- **T005 antes de T019**: no se puede dar de baja sin la llamada.
- **T012 antes que T013–T017**: el modo de fallo se escribe primero, y el resto se apoya en el mismo simulador de Meta.
- **T019 antes de T023**: la tarjeta lee `unlink_pending`.
- **Iteración 1 se puede soltar sola**. Iteraciones 2 y 3 se sueltan juntas.

## Paralelo

- T001, T002, T003, T005 a la vez.
- T006, T007, T008 a la vez, sobre el índice ya migrado.
- T013, T014, T015, T016, T017 a la vez, tras T012.
- T021, T022 a la vez.

## Estrategia

**MVP = Iteración 1**: tres tests, una migración, dos líneas de código. Contesta
la pregunta del owner —«¿puedo activarlo en otro partner?»— con un **sí** en
nuestro lado, y se puede desplegar sin tocar Meta. Lo que queda después es que
«desvincular» también suelte el número allí, y que si Meta no contesta, nadie se
quede sin saberlo.
