# Tareas: 048 — Retirar AgendaPro y dejar Reservas como la única agenda

**Entrada**: `spec.md` y `plan.md` de esta carpeta. Es el único plan de ejecución.
`T/` = `apps/api/tests/`. Las tareas `[P]` de una fase van en paralelo.

## Fase 1 — Pruebas en rojo

- [X] T001 [P] `T/integration/migrations/test_0205_retire_agendapro.py`: con un cliente con
  `agendapro_public_url`, la migración falla y lo nombra sin cambiar nada; sin él, borra el
  conector y sus `tenant_connectors`, las filas `agendapro.*` (también
  `get_today_appointments` y `scrape_no_shows`), las dos columnas y el índice, cancela los
  `scheduled_jobs` pendientes de los dos tipos y marca `booking.*` retiradas.
  _Requisitos: 1.5, 1.6, 2.2_
  Hecho (2026-10-29): `T/integration/test_migration_0205_retire_agendapro.py` (junto a las demás pruebas de migración, no en `migrations/`): rojo sin la 0205, verde con ella; también la vuelta atrás.

- [X] T002 [P] `apps/worker/tests/unit/test_bootstrap_split.py`: `ALL_EXPECTED` sin
  `no-show-scrape-cron` ni `async-booking-cron`, y el contexto sin `agendapro_public_pool`.
  _Requisitos: 1.3_
  Hecho (2026-10-29): `ALL_EXPECTED` sin los dos crons, `_dummy_ctx` sin el pool y `test_agendapro_left_the_worker` (contrato y `WorkerContext`).

- [X] T003 [P] `apps/mcp/tests/test_registry_unit.py`: ninguna herramienta `agendapro_public.*`
  ni interna de AgendaPro; el total de nombres, el nuevo.
  _Requisitos: 1.3_
  Hecho (2026-10-29): conjunto interno vacío, ningún nombre con `agendapro`; el total público sigue en 71 (las de AgendaPro eran internas).

- [X] T004 [P] `T/unit/test_agent_spec_validator.py`: un borrador con `booking.create_appointment`
  se rechaza con `tool_retired` y propone `reservas.create`; una versión ya publicada con
  `booking.*` sigue cargando en el runtime.
  _Requisitos: 2.2, 2.3, 5.3_
  Hecho (2026-10-29): `tool_retired` con `replacement` en `tools` y en un procedimiento, retirada por nombre aunque el catálogo diga `active`, y el registro sigue dando `booking.*` a una lista que la nombra.

- [X] T005 [P] `T/unit/test_seed_templates.py` y `test_seed_templates_connectors.py`: ninguna
  plantilla nombra `booking.*` ni recomienda `agendapro`; las 9 de citas llevan `reservas.*`.
  _Requisitos: 1.1, 2.1_
  Hecho (2026-10-29): las nueve que reservan llevan `reservas.find_slots` y `reservas.create`; ninguna plantilla nombra una herramienta `booking.*` ni `agendapro`; las de citas recomiendan solo `calendly`.

- [X] T006 [P] `T/integration/reservations/test_pass_to_reservas.py`: un agente con `booking.*` en
  `tools`, `spec.tools`, un procedimiento y su texto recibe un borrador con `reservas.*` en los
  cuatro sitios, sin promover; de tres citas futuras, dos se importan y la tercera sale en el
  informe; repetir no duplica; todo bajo la RLS del cliente.
  _Requisitos: 3.2, 3.3, 3.4, 3.5, 3.6_
  Hecho (2026-10-29): `T/integration/reservations/test_pass_to_reservas.py`: la lista del operador, el paso (borrador en los cuatro sitios, dos importadas, la tercera con `service_missing`, nada a B, auditoría), la repetición sin duplicar, el 409 sin Reservas y la activación que hace el paso.

- [X] T007 [P] `T/integration/mcp/test_history_reads_reservas.py`: `client.get_history` y
  `commission.*` cuentan las citas de Reservas y las de `appointments` no importadas, sin
  duplicar.
  _Requisitos: 4.1, 4.2_
  Hecho (2026-10-29): `client.get_history` (la importada una vez, con `source`) y `commission.get_barber_earnings`/`get_daily_report` (tres, 32 000, 40 %); y el historial de otra persona u otro cliente no sale.

- [X] T008 [P] `T/unit/test_agent_review.py`: la promesa «reservar» ya no acepta `agendapro.` y
  sigue aceptando `booking.` y `reservas.`.
  _Requisitos: 1.9, 2.4_
  Hecho (2026-10-29): `PROMISES` sin `agendapro.`; `booking.` y `reservas.` cumplen la promesa de reservar.

## Fase 2 — Retirar AgendaPro

- [X] T010 Borrar `apps/mcp/servers/agendapro_public_mcp/` y la etapa `node-build` del
  `apps/worker/Dockerfile` (con la copia, el `chown` y las dos variables de entorno).
  _Requisitos: 1.3_
  Hecho (2026-10-29): fuera `apps/mcp/servers/agendapro_public_mcp/` y la etapa `node-build` (Node, `dist`, `node_modules`, `chown` y las dos variables).

- [X] T011 Borrar `apps/mcp/src/nexus_mcp/servers/agendapro_public/`, `subprocess_tool.py`,
  `transports/{stdio,pool}.py` y su registro en `registry.py`; limpiar los comentarios.
  _Requisitos: 1.3_
  Hecho (2026-10-29): fuera `servers/agendapro_public/`, `subprocess_tool.py`, `transports/` y el registro interno; `dispatch_internal` se queda, vacío; comentarios y `README.md` al día.

- [X] T012 Worker: `bootstrap.py` sin el pool ni los dos crons (y sus nombres en
  `SCHEDULER_TASK_NAMES`); borrar `streams/async_booking_cron.py` y
  `streams/no_show_scrape_cron.py`; `config.py` sin `no_show_scrape_tick_seconds`;
  `operator_alerts.py`, `turn_effects.py` y las skills sin AgendaPro.
  _Requisitos: 1.3_
  Hecho (2026-10-29): `bootstrap.py` sin pool ni crons; borrados los dos crons; `config.py`, `operator_alerts.py`, `turn_effects.py`, comentarios del pipeline y las skills (`anti-hallucination-booking`, `phi-redaction`, las rúbricas y las que nombraban `booking.*`, que ahora nombran `reservas.*`).

- [X] T013 API: borrar `api/console/integrations.py` y la ruta de `api/admin/integrations.py`
  (y sus montajes); `schemas_agent_tools.py`, `console/tools.py`, `capabilities_client.py`,
  `capability_names.py` (fuera `agendapro.*` y `requires="agendapro"` de `booking.*`),
  `agent_spec/validator.py` (fuera el slug conectado), `agent_spec/compiler.py` (`PROMISES`),
  `db/models/tenant.py`, `appointment.py`, `schemas/tenant.py`; la rama asíncrona de
  `mcp/servers/booking/tools.py`; borrar `services/connectors/seeds/agendapro.yaml`.
  _Requisitos: 1.1, 1.2, 1.4, 1.7, 1.9_
  Hecho (2026-10-29): fuera las dos rutas y sus montajes, `public_url` de `ConnectorOut`, `requires="agendapro"` y las dos `agendapro.*` de `capability_names.py`, el slug conectado del validador, `agendapro.` de `PROMISES`, las columnas de los modelos y el esquema, la rama asíncrona y `booking_status` de `booking.create_appointment`, y `agendapro.yaml`.

- [X] T014 Migración `0205_retire_agendapro` según `plan.md`, con su guarda.
  _Requisitos: 1.5, 1.6, 2.2_
  Hecho (2026-10-29): `alembic/versions/0205_retire_agendapro.py`: la guarda (URL, conexión no desconectada o credenciales; nombra a los clientes y no cambia nada), los borrados, `booking.*` a `deprecated` sin `connector_id`, los trabajos cancelados y la frase `reservations.passed`. Decisiones en `plan.md` §Decisiones.

- [X] T015 [P] Panel de operador: fuera `AgendaProSetupDialog`, sus acciones, la página del
  conector y `lib/backend.ts`.
  _Requisitos: 1.1_
  Hecho (2026-10-29): fuera el asistente, `agendaProSetPublicUrlAction`, sus ramas en
  `connectors/[slug]/page.tsx`, `setAgendaProPublicUrl` y `Tenant.agendapro_public_url`.
  `apps/admin/src/lib/__tests__/no-agendapro.test.ts` barre el panel.
- [X] T016 [P] Consola: fuera la tarjeta y el diálogo de AgendaPro (`connector-card.tsx`), sus
  acciones, `lib/backend/agent-tools*.ts`, i18n, `builder-model.ts` y la ruta del logo; las
  historias de `packages/ui`.
  _Requisitos: 1.1_
  Hecho (2026-10-29): fuera `PublicLinkCard`, `setAgendaProUrlAction`, `setAgendaProUrl`,
  `AgendaProPublicUrlOut`, `ConnectorOut.public_url`, las claves `connectors.agendapro.*` y
  `connectors.desc.agendapro`, la marca en `builder-model.ts` y el comentario de la ruta del
  logo; las historias y las pruebas y mocks de e2e usan Google Calendar.
  `apps/console/src/__tests__/no-agendapro.test.ts` barre la consola y las historias.
- [X] T017 [P] Terraform: fuera los secretos `BROWSERBASE_*` de `infra/terraform/20-services`
  (y del guion de Doppler). Lo aplica Luis.
  _Requisitos: 1.8_
  Hecho (2026-10-29): fuera `BROWSERBASE_*` de `variables.tf` (la entrada `runner` de `taskdefs.tf` no se tocó) y de `migrate_doppler_secrets.sh`; `terraform fmt -check` en verde. Lo aplica Luis.

- [X] T018 Pruebas existentes: actualizar o borrar las 44 que nombran AgendaPro (inventario
  del 2026-10-29), sin debilitar ninguna de aislamiento: `test_connectors_isolation.py` cambia
  su conector de ejemplo por otro sembrado.
  _Requisitos: 1.1_
  Hecho (2026-10-29): borradas `test_agendapro_public_proxy.py`, `test_booking_async_facade.py` y `test_no_show_scrape_cron.py`; el resto, al día. `test_connectors_isolation.py` usa `woocommerce` (sembrado) y `test_9` etiqueta sus credenciales con `woocommerce`: la misma prueba de RLS. Nueva `T/unit/test_no_agendapro.py` (CE-001 en lo que se despliega).

## Fase 3 — Reservas, la única agenda

- [X] T020 Las 9 plantillas (`services/templating/seeds/*.yaml`) con `reservas.*` en
  `tools.required` y en su texto; `connectors.recommended` sin `agendapro`; los cinco
  conjuntos de evaluación y `prompt_library/snippets/tool_call_verify_first.yaml`.
  _Requisitos: 2.1_
  Hecho (2026-10-29): las 9 plantillas con las nueve `reservas.*`, el texto reescrito (y a mano lo que describía AgendaPro), sin `agendapro` en `connectors.recommended`; los cinco conjuntos de evaluación, la batería de certificación y `tool_call_verify_first.yaml`.

- [X] T021 Catálogo y validador: `booking.*` retiradas; el validador las rechaza en borradores
  nuevos o editados con `tool_retired` y su sustituta; el catálogo del constructor y del
  copiloto no las ofrece; el runtime las sigue ejecutando.
  _Requisitos: 2.2, 2.3, 2.4, 5.3_
  Hecho (2026-10-29): catálogo (0205), `services/agent_spec/retired.py`, validador (`tool_retired`), constructor (la descarta y no la enseña), `PUT …/tools` (rechaza añadirla) y la puerta (lleva `replacement`); el runtime la sigue ejecutando.

- [X] T022 «Pasar a Reservas»: ampliar `prepare_agent_versions` (AgentSpec, procedimientos y
  texto con el mapa fijo), la importación de citas futuras con su informe, la lista de
  clientes con `booking.*` y la acción en `/admin/*` y en el panel.
  _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_
  Hecho (2026-10-29): `services/reservations/passing.py` y `api/admin/reservas_pass.py`: `GET /admin/reservas/legacy-booking` y `POST /admin/tenants/{id}/reservas/pass` (contrato en `docs/reservas.md`). La activación (`admin.apply_choice`) hace el mismo paso. **La pantalla del panel queda para la consola** (otro agente).
  Pantalla del panel: hecha (2026-10-29): `/tenants/legacy-booking` («Clientes › Pasar a Reservas», botón en la cabecera de Clientes), en `apps/admin/src/app/(dashboard)/tenants/legacy-booking/` y `lib/backend-reservas.ts`. Lista con agentes, citas futuras y Reservas; confirmación con `ConfirmDialog`; informe con borradores y su versión, importadas, ya importadas y sin importar con el motivo en palabras; el 409 lleva a Acceso; los cinco estados. Pruebas: `legacy-booking/__tests__/` (modelo, componente y axe), `lib/__tests__/backend-reservas.test.ts` y la miga. Decisión 10 de `plan.md`; `docs/admin.md` y `docs/reservas.md` al día.

- [X] T023 `client.get_history` y `commission.*` leen Reservas y `appointments`.
  _Requisitos: 4.1, 4.2_
  Hecho (2026-10-29): `nexus_mcp/_agenda.py`; `client.get_history` y `commission.*` leen las dos agendas sin duplicar.

- [X] T024 Suite de aislamiento entera en verde.
  _Requisitos: 3.6_
  Hecho (2026-10-29): 3581 en verde. `test_42` cambia su capacidad de ejemplo por
  `reservas.*` (la retirada ya no se ofrece) sin tocar lo que prueba; `test_46`
  declara los dos lectores nuevos del grafo (`passing.py`, `_agenda.py`) con su
  caso adversarial (el barbero de otro cliente no casa ni cobra).
- [X] T025 Documentación del `plan.md` §Documentación.
  Hecho (2026-10-29): `RUNBOOK.md`, `docs/reservas.md` (Reservas, la única agenda; «Pasar a Reservas» y su informe), `docs/companion/capabilities.yaml` (AgendaPro `retired`) y `apps/mcp/README.md`. `docs/console.md` ya lo dejó la consola (T016).

## Fase 3b — El paso automático (enmienda del 2026-10-29)

- [X] T026 [P] `T/integration/reservations/test_auto_pass.py`, en rojo primero. Cubre los escenarios 1 a 6 de la historia 3:
  - un cliente sin Reservas, restaurante y no restaurante;
  - una versión activa con `booking.*` en los cuatro sitios;
  - un borrador del partner con otros cambios, que no se publica;
  - las citas importadas y las no importadas;
  - la segunda pasada, que no encuentra a nadie;
  - un cliente que falla mientras los demás pasan;
  - la auditoría con `platform:reservas-pass` y las pruebas desactualizadas.

  Más un caso de aislamiento en `tests/isolation/`: el paso de un cliente no lee ni escribe nada de otro.
  _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_
  Hecho (2026-10-30): `T/integration/reservations/test_auto_pass.py` (10 pruebas: activación por sector y por plantilla sin abrir el acceso ni invitar, y el agente reserva; la activa publicada sin puerta, como `platform:reservas-pass`, con las pruebas desactualizadas y el modo intacto; el borrador reescrito sin publicar, con su revisión +1; agentes sin `booking.*` intactos; citas importadas y en el informe; recién activado, todo `service_missing`; segunda pasada sin nadie; un cliente que falla deshecho entero con `reservations.auto_pass_failed` y `reservations.auto_pass_done`; el guion sale con 0; las rutas a mano dan 404), con el mundo común en `T/integration/reservations/_legacy_world.py`. Aislamiento: `T/isolation/test_reservas_auto_pass_scope.py` (B, con sector «restaurante», «Corte» y «Lucía», no se toca ni se lee; sin el cambio de rol se pone en rojo). Cableado del release en `T/unit/test_release_uses_direct_db.py`. Todo visto en rojo antes de implementar.
- [X] T027 Quitar «Pasar a Reservas» a mano, según la decisión 15 de `plan.md`. Se borran, con sus pruebas:
  - la pantalla del panel, su botón y su miga;
  - `lib/backend-reservas.ts`;
  - `api/admin/reservas_pass.py` y su registro;
  - la sección de `docs/admin.md`.

  `docs/reservas.md` pasa a contar el paso automático.
  _Requisitos: 3.8_
  Hecho (2026-10-30): fuera `api/admin/reservas_pass.py` y su registro; `test_pass_to_reservas.py` se queda con la activación desde Acceso (3.9) y pierde las pruebas de las rutas. En el panel, fuera `tenants/legacy-booking/` con sus pruebas, `lib/backend-reservas.ts` y su prueba, la miga y su caso en `crumbs.test.ts`, y el botón de `tenants/page.tsx`; `lib/__tests__/no-manual-reservas-pass.test.ts` barre el panel. Fuera la sección de `docs/admin.md`. Ningún inventario de rutas las enumeraba (barrido con grep).
- [X] T028 `apps/api/scripts/pass_booking_to_reservas.py` y su línea en `release.sh`, según las decisiones 11 a 13. Incluye la publicación desde la versión activa con el actor `platform:reservas-pass` y la activación de Reservas por sector o plantilla. La activación desde Acceso sigue igual.
  _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.9_
  Hecho (2026-10-30): `services/reservations/auto_pass.py` (modo por sector o plantilla, activación sin abrir el acceso, un cliente por transacción bajo `as_tenant`, registros) sobre `passing.py` (`publish_agent_versions`, `pass_to_reservas(automatic=…)`, `prepare_agent_versions(drafts_only=…)`), `AgentConfigService.publish_platform_copy` y `publish_copy` con sustituciones; `apply_choice(prepare_agents=…)`; `ClientAccess.reservas_on` en la puerta de `reservas.*`, en las ofertas del worker, en `reservas_enabled` y en `set_access`. El guion va a la base directa y `release.sh` lo llama tras el sembrado sin parar el despliegue. Decisiones 16 a 25 de `plan.md`.
- [X] T029 Documentación:
  - `docs/reservas.md`;
  - `apps/api/RUNBOOK.md`: qué mirar en el registro del despliegue (`reservations.auto_pass_done` y `reservations.auto_pass_failed`) y cómo repetir el paso;
  - el comentario de cabecera de `release.sh`.

  Hecho (2026-10-30): `docs/reservas.md` («El paso automático a Reservas», Reservas sin depender del acceso, el dominio y el caso de aislamiento nuevo), `apps/api/RUNBOOK.md` (paso 3 y «Paso automático a Reservas»: consulta de Logs Insights, los cuatro eventos y cómo repetirlo), la cabecera de `release.sh` y `docs/consola-lite.md` (los módulos no dependen del acceso para Reservas).

## Fase 4 — Borrado final de `booking.*` (otra entrega)

- [ ] T030 En un despliegue posterior, cuando `reservations.auto_pass_done` de producción diga que no quedó nadie: migración que borra el servidor
  `booking`, sus filas y `appointments`, con la guarda del requisito 5.2; sacar `appointments`
  del inventario de `test_43`. **No entra en esta rama**: la migración pararía el despliegue si
  alguien aún la nombra.
  _Requisitos: 5.1, 5.2_

## Cierre

- [ ] T040 `./scripts/verify.sh` en verde (lint, py, js).
  Parcial (2026-10-29, backend): `lint` en verde; API unitarias, de integración y
  de aislamiento, worker y MCP en verde salvo lo ajeno a la 048 (ver el informe:
  `test_renderer_client.py::test_own_timeout_is_enforced`, del navegador, y
  `test_dev_seed_fabrica` solo en la suite entera, por el socio «Grader» que deja
  `test_deferred_grader.py`). `js` es de la consola.
  2026-10-30: `verify.sh` entero, con lo de la 048 en verde (`lint`, `py` y `js`).
  Lo único en rojo son tres pruebas del saldo que dependen de la fecha, ajenas a esta
  spec; ver la T219 de la 047.
- [ ] T041 Medir la imagen del worker antes y después (CE-002). Pendiente: no se
  construyó la imagen en local (disco); lo dirá la próxima construcción de CI.
