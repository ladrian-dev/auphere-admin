# Tareas: 043 — Reservas

**Entrada**: [spec.md](spec.md), [plan.md](plan.md), [data-model.md](data-model.md), [contracts/](contracts/)

Test primero (§VII). Rutas desde la raíz del repo. `[P]` = paralelizable.

## Fase 1 — Base (bloquea todo)

- [x] T001 Migración `0172_reservations_schema.py`: las tablas de `data-model.md` (sin P3), RLS FORCE con `WITH CHECK`, FK compuestas (con `UNIQUE (tenant_id, id)` en `customers`, `conversations` si faltan), grants, CHECK de módulos con `reservas` y de tipos de push. Modelos en `db/models/reservation.py`. `test_21`/`test_22` en verde con las tablas nuevas; reversibilidad.
  _Requisitos: 1.1, Entidades clave_
- [x] T002 [P] Pruebas unitarias en rojo del motor puro (`apps/api/tests/unit/test_reservations_engine.py`): franjas de turnos y franjas (última inclusiva), presencia, `fits` con guardadas, llegada sin reserva, bloqueos, estancia que cruza franjas, `first_fit`; huecos de Servicios con dos tramos, reservas vivas, ofertas retenidas, pasado, antelación del agente, día cerrado, sin horario.
  _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5_
- [x] T003 Motor `services/reservations/engine.py` hasta verde.
  _Requisitos: 4.1–4.5_
- [x] T004 [P] `services/reservations/settings.py`: valores de partida por modo y tipo; validación de rangos (pruebas unitarias).
  _Requisitos: 1.3, 2.4–2.7_

## Fase 2 — Historia 1: activar y elegir modo (P1)

- [x] T005 [US1] Pruebas en rojo del admin (`apps/api/tests/unit/test_admin_client_access_reservas.py`): activar sin modo 422; con modo crea ajustes por defecto; cambiar con vivas 409 `live_reservations`; `cancel_and_notify` cancela, encola avisos y cambia; versiones preparadas por agente activo con `reservas.*` y sin `booking.*`, la activa intacta; auditoría.
  _Requisitos: 1.2–1.7_
- [x] T006 [US1] `ClientModule.RESERVAS`, `api/admin/client_access.py` (`reservas`, `max_length=4`), `services/client_access.py`, `services/reservations/admin.py` (hecho ahí: activación, cambio de modo y versiones del agente). Espejos: `tests/unit/test_lite_me_nav.py`, `make_client_access`.
  _Requisitos: 1.1–1.7_
- [x] T007 [US1] Panel de operador: pestaña Acceso con Reservas, modo y tipo, diálogo de vivas, aviso de versiones por promover (`apps/admin/src/app/(dashboard)/tenants/[id]/access/*`, `lib/backend.ts`), con su vitest.
  _Requisitos: 1.2, 1.4, 1.5, 9.1_

## Fase 3 — Historias 2 y 3: la API de la agenda (P1)

- [x] T008 [US2] Servicio de dominio `services/reservations/{core,waitlist,views}.py` (así quedó el reparto): crear/mover/cancelar/transiciones con candado + revalidación, eventos, outbox, `allowed`, `local`, `late_minutes`.
  _Requisitos: 5.2, 5.4, 5.5, 5.6, 5.8_
- [x] T009 [US2] Pruebas de integración en rojo de la API (`apps/api/tests/integration/reservas/`): ajustes y horario; equipo y servicios (archivar con vivas 409); reservas en los dos modos (crear, mover, cancelar con preview y oferta, confirmar, pedir confirmación, llegar, no vino, deshacer, walk-in), `Idempotency-Key`, `If-Match` 412, `wrong_mode`, `hours_missing`; huecos; ocupación; resumen; bloqueos; lista de espera y ofertas.
  _Requisitos: 2.1–2.7, 3.1–3.4, 4.1–4.5, 5.1–5.9_
- [x] T010 [US2] Prueba de concurrencia en rojo: N peticiones simultáneas por la API y por la herramienta sobre la misma hora → una reserva (Servicios) y nunca por encima del aforo (Aforo).
  _Requisitos: 5.2, 6.2, CE-001_
- [x] T011 [US2] Rutas `api/console/lite/reservas.py` + `reservas_schemas.py` (contrato `lite-api.md`), `/me.reservas`, `nav`, `contact.next_booking` en el detalle de la Bandeja, tipos de aviso en `/phones/current/notices`.
  _Requisitos: 2.1–2.7, 3.1–3.4, 5.1–5.10_

## Fase 4 — Historia 4: el agente (P1)

- [x] T012 [US4] Pruebas en rojo de las herramientas (`apps/api/tests/integration/reservas/test_tools.py`): sin cliente se niegan; sin módulo se niegan; `too_large`, `too_soon`, `closed`, `hours_missing`; idempotencia; `list_mine`/`reschedule`/`cancel`/`confirm_attendance` solo lo propio (ajeno = inexistente); `answer_offer` resuelve la oferta de la persona; push `reservas.agent_change` encolado.
  _Requisitos: 6.1–6.6_
- [x] T013 [US4] `apps/mcp/src/nexus_mcp/servers/reservas/{schemas,tools}.py`, registro en `registry.py` (y su conteo), migración `0173_reservations_tools.py` + snapshot JSON (y el conteo del catálogo), `capability_names.py` (Citas), `_INTENT_CATEGORIES` del pipeline.
  _Requisitos: 6.1–6.6, 9.2_

## Fase 5 — Historias 5 y 6: lo automático y la lista de espera (P2)

- [x] T014 [US5] Pruebas en rojo de `reservations-cron` con reloj fijado: confirmación/recordatorio una vez; liberar Aforo 1 h antes; `done` en los dos modos; caducar entradas.
  _Requisitos: 7.1, 7.2, 7.3, 7.5_
- [x] T015 [US5] `apps/worker/src/nexus_worker/streams/reservations_cron.py`.
  _Requisitos: 7.1, 7.2, 7.3, 7.5_
- [x] T016 [US5] Pruebas en rojo + `reservation_outbox_cron.py`: texto en ventana, plantilla aprobada fuera, `skipped` con evento `notify_failed` (sin teléfono, sin plantilla, opt-out), tope de intentos.
  _Requisitos: 5.6, 7.6_
- [x] T017 [US6] Pruebas en rojo + `reservation_offers_cron.py` y la apertura de ofertas: Servicios de uno en uno 5 min hasta 5; Aforo 15 min, una abierta por franja; antelación mínima; tarde y libre = gana; tarde y ocupado = sigue en lista; «Detener».
  _Requisitos: 7.4, Historia 6_
- [x] T018 [US5] Push de Reservas: `NOTICE_KINDS`, `push_fanout` (módulo `reservas`), `push_texts.py`, `push_payloads.py`, vocabulario de auditoría (en `0173_reservations_tools.py`; los tipos de push, en el CHECK de `0172`); pruebas.
  _Requisitos: 7.7_
- [x] T019 [US5] Contrato de nombres de crons: `bootstrap.py` + `test_bootstrap_split.py`.
  _Requisitos: 7.8_

## Fase 6 — Historias 2 y 3: las pantallas (P1)

- [x] T020 [US2] Módulo `reservas` en la consola: `principal-access.ts` (`CLIENT_MODULES`, `firstModulePath`, `clientModuleOfPath`), `lite-nav.ts` (icono calendario), `messages.ts`, pruebas de guardas y nav; `e2e/lite.spec.ts` con `/reservas`.
  _Requisitos: 8.1_
- [x] T021 [US2] BFF `lib/backend/reservas.ts` + `app/(console)/reservas/actions.ts` (validación zod, `If-Match`, `Idempotency-Key`), con su prueba de acciones.
  _Requisitos: 8.1_
- [x] T022 [US2] Pantalla común: pestañas, vista/periodo separados, navegación de fechas, píldora de lista de espera, `loading.tsx`/`error.tsx` con medidas finales.
  _Requisitos: 8.1, 8.2, 8.3_
- [x] T023 [US2] Servicios: cuadrícula día por profesional (pausas, ahora, carriles), semana de una persona, mes; lista con filtros; detalle lateral con historial y `allowed`; nueva/mover con huecos reales; cancelar con preview y oferta; vitest de cada pieza.
  _Requisitos: 5.1–5.6, 8.2, 8.3_
- [x] T024 [US3] Aforo: mapa de ocupación (días × franjas, niveles con tokens, bloqueado con trama), lista por hora con Llegó/No vino/Deshacer, panel de la hora, llegada sin reserva, bloquear horas; vitest.
  _Requisitos: 5.1, 5.4, 5.7, 8.2, 8.3_
- [x] T025 [US2] Lista de espera y ofertas (los dos modos) y Ajustes (equipo, servicios, horario del negocio, recordatorios/confirmación, aforo y horario de reservas); vitest.
  _Requisitos: 2.1–2.7, 3.1–3.4, 8.1_
- [x] T026 [US2] Panel: bloque de Reservas por modo (de `/reservas/summary`) y fila «N reservas de hoy sin confirmar».
  _Requisitos: 5.9, 8.4_

## Fase 7 — Aislamiento (bloquea el merge)

- [x] T030 `apps/api/tests/isolation/test_reservas_client_vs_client.py`: todo GET de `/console/lite/reservas*` sin el vecino; cada ruta con id (reserva, persona, servicio, bloqueo, entrada, oferta) → 404 idéntico con el id del vecino y con uno aleatorio; las escrituras con id también. Añadir los parámetros a `_FOREIGN` de `test_lite_client_vs_client.py`.
  _Requisitos: CE-002_
- [x] T031 `apps/api/tests/isolation/test_reservas_customer_axis.py`: el agente de la persona A no lista, mueve, cancela, confirma ni acepta ofertas de B del mismo negocio; las herramientas no tienen campo de cliente.
  _Requisitos: 6.1, 6.3, 6.4, CE-003_
- [x] T032 Partner → 403 en todas y cliente sin el módulo → 403 (`test_reservas_client_vs_client.py::test_a_partner_member_and_a_client_without_the_module_get_403`); ningún parámetro ni campo de respuesta prohibido y principal obligatorio: `test_console_scope.py` ya barre toda ruta montada bajo `/console`, Reservas incluida. No hizo falta un fichero aparte.
  _Requisitos: 1.1, 8.1_

## Fase 8 — Lo mínimo en partners y la documentación

- [x] T040 Consola de partners: nombres de las herramientas en Capacidades (Citas) — cubierto por T013; nada más.
  _Requisitos: 9.2_
- [x] T041 `docs/reservas.md` (nuevo: modelo, reglas, crons, plantillas), `docs/consola-lite.md` (módulo), `docs/admin.md` (Acceso).
  _Requisitos: todos_
- [x] T042 Medidor: comprobar que los salientes de Reservas cuentan como mensajes enviados del cliente (prueba sobre el despachador de salida).
  _Requisitos: Encabezado (Qué se mide)_

## Fase 9 — Historia 7: Google Calendar (P3, independiente)

- [x] T050 [US7] Migración `0174_reservation_calendars.py` + modelos; pruebas en rojo de la lectura del ocupado (sin títulos) y de la escritura del «Ocupado» (sin cliente ni servicio) con el cliente del proveedor simulado.
  _Requisitos: 10.1–10.5_
- [x] T051 [US7] `reservation_calendar_cron.py`, rutas `/reservas/calendar` y `/staff/{id}/calendar`, el ocupado en el motor, `clash` en `Booking`, insignia de choques; contrato de nombres.
  _Requisitos: 10.1–10.4_
- [x] T052 [US7] Prueba de que las herramientas de Google Calendar del agente siguen bloqueadas.
  _Requisitos: 10.5_

## Fase 10 — Cierre

- [x] T060 Gates de UI (`ui-states-checklist`, `a11y-audit`, `responsive-audit`, `design-tokens`) y capturas de los dos modos en `evidence/`.
  _Requisitos: 8.3, CE-004_
- [x] T061 `./scripts/verify.sh` entero en verde; `/cso`.
  _Requisitos: todos_
