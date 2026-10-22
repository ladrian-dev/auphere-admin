# Tareas: 045 — la consola customers, mejoras y Beta

**Entrada**: [spec.md](spec.md), [plan.md](plan.md), [data-model.md](data-model.md), [contracts/lite-api.md](contracts/lite-api.md)

Test primero (§VII): cada bloque de pruebas se escribe y se ve en rojo antes de
su implementación. Rutas desde la raíz del repo.

## Fase 1 — Base

- [x] T001 Migración `apps/api/alembic/versions/0171_inbox_attended.py`: `conversations.attended_at`, `last_attended_inbound_at`, índice parcial; relleno desde `messages` (entrantes con `skipped_reason IS NULL`); `client_phones.quiet_outside_hours bool NOT NULL DEFAULT true`. Prueba de relleno e idempotencia en `apps/api/tests/integration/test_migration_0171_inbox_attended.py`. Modelos en `db/models/conversation.py` y `client_phone.py`.
  _Requisitos: 1.7, 5.2_

## Fase 2 — Historia 1: la Bandeja solo con lo atendido (P1)

- [x] T002 [US1] Pruebas en rojo del despachador: un entrante permitido fija `attended_at` (una vez) y `last_attended_inbound_at`; uno silenciado no toca nada ni encola `message_for_you` (`apps/worker/tests/…` o `apps/api/tests/integration/channels/test_dispatcher_attended.py`).
  _Requisitos: 1.1, 1.2, 2.3_
- [x] T003 [US1] `apps/worker/src/nexus_worker/runtime/dispatcher.py`: escribir las dos columnas tras la puerta; mover `enqueue_message_for_you` detrás de la puerta.
  _Requisitos: 1.1, 1.2, 2.3_
- [x] T004 [US1] Prueba de aislamiento en rojo `apps/api/tests/isolation/test_lite_inbox_attended_only.py`: con un número silenciado y un envío del sistema sin respuesta, la lista, la búsqueda, cada filtro, `/counts`, los contadores de la página, el detalle (404 idéntico), el hilo y la vista previa no los enseñan; un mensaje silenciado en una conversación visible no aparece ni la marca como no leída.
  _Requisitos: 1.3, 1.4, 1.5, 1.6, 2.1_
- [x] T005 [US1] `apps/api/src/nexus_api/services/inbox_view.py`: predicado de visibilidad en `list_conversations`, `counts`, `get_conversation`, `detail`, `thread`; `unread_expr` contra `last_attended_inbound_at`; hilo desde `attended_at` sin silenciados.
  _Requisitos: 1.3, 1.4, 1.5, 1.6, 2.1_
- [x] T006 [US1] Prueba y cambio de `services/push_fanout.py`: `compose` descarta lo invisible; la insignia cuenta con `counts`.
  _Requisitos: 2.1, 2.4_
- [x] T007 [US1] Prueba y cambio de `services/lite_home.py`: `waiting` es el de la Bandeja (mismo número con los mismos datos).
  _Requisitos: 2.2_

## Fase 3 — Historia 4: la API para la app (P2, antes que las pantallas que la usan)

- [x] T008 [P] [US4] Pruebas en rojo + `waiting {reason, since}` en `ConversationItemOut` y `waiting_since` en el detalle (`api/console/lite/inbox.py`, `inbox_view.py`).
  _Requisitos: 3.1, 3.2_
- [x] T009 [P] [US4] Pruebas unitarias en rojo + función pura `balance_horizon` (`month_days_left`, `runs_out_on`) y su uso en `home.py` y `usage.py`.
  _Requisitos: 4.1, 4.2_
- [x] T010 [P] [US4] Pruebas en rojo + `/me.business` (zona, horario canónico, etiqueta por idioma con `business_hours_label` en `services/business_hours.py`).
  _Requisitos: 5.1_
- [x] T011 [US4] Pruebas en rojo + `quiet_outside_hours` en `/phones/current/notices` y silencio en `push_fanout._targets` (no urgentes fuera de horario → `skipped/quiet_hours`; `inbox.waiting` siempre; sin horario, nada).
  _Requisitos: 5.2, 5.3, 5.4, 5.5_
- [x] T012 [US4] Exportar `apps/mobile/src/api/openapi.json` con `scripts/export_openapi.py` (y `pnpm --dir apps/mobile gen`): `verify.sh mobile` exige que el contrato sea el de esta rama, así que el fichero generado viaja con el cambio; la sesión de la app lo consume y no lo edita a mano (se le avisa).
  _Requisitos: 3.1, 4.1, 5.1, 5.2_

## Fase 4 — Historia 2: las pantallas del diseño (P1)

- [x] T013 [US2] Tipos del BFF (`apps/console/src/lib/backend/lite.ts`, `inbox.ts`) con los campos nuevos.
  _Requisitos: 3.1, 4.1, 5.1_
- [x] T014 [US2] Pruebas en rojo + Panel (`components/lite/lite-panel-view.tsx`, `lite-attention.tsx`, `lite-spend-card.tsx`): cabecera «Hola», KPI destacado, «Cubre N de M días» con tono por días, gráfica con media, «todo en orden» nuevo; cinco estados; sin «Comprar».
  _Requisitos: 4.3, 6.1, 6.4, 6.5, 6.6_
- [x] T015 [US2] Pruebas en rojo + Bandeja (`components/inbox/*`): intro con WhatsApp, motivo y espera en la fila, píldora «N agentes activos»; lo de la 030 intacto.
  _Requisitos: 6.2, 6.4, 6.5, 6.6_
- [x] T016 [US2] Pruebas en rojo + Consumo (`components/lite/lite-usage-view.tsx`): saldo primero con «Te alcanza hasta», detalle técnico en mensajes / uso del modelo / multimedia.
  _Requisitos: 6.3, 6.4, 6.5, 6.6_
- [x] T017 [US2] Esqueletos con las medidas finales (`app/(console)/loading.tsx` para el cliente, `usage/loading.tsx`).
  _Requisitos: 6.5_

## Fase 5 — Historia 3: Beta (P2)

- [x] T018 [US3] Prueba en rojo + insignia Beta en la rama de cliente de `components/shell/app-sidebar.tsx` con `shell.beta.client.hint`; fuera «lite» (y su prueba y la e2e).
  _Requisitos: 7.1, 7.2_

## Fase 6 — Cierre

- [x] T019 `docs/consola-lite.md`: la regla de la Bandeja, los campos nuevos, Beta, silencio fuera de horario.
  _Requisitos: todos_
- [x] T020 Gates de UI del workspace (`ui-states-checklist`, `a11y-audit`, `responsive-audit`, `design-tokens`) y capturas en claro y oscuro de Panel, Bandeja y Consumo en `evidence/`.
  _Requisitos: 6.5, 6.6, CE-003, CE-004_
- [x] T021 `./scripts/verify.sh` entero en verde.
  _Requisitos: todos_
