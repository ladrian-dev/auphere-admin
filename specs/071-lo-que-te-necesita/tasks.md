---

description: "Tareas de la spec 071 (API y worker): lo que te necesita"
---

# Tasks: Lo que te necesita (API y worker)

**Input**: Design documents from `/specs/071-lo-que-te-necesita/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md), [research.md](research.md), [contracts/api.md](contracts/api.md)

**Tests**: obligatorios (constitución §VII). Cada tarea de test se escribe y se ve en rojo antes de la tarea de implementación que la sigue.

## Reglas de este repo *(constitución)*

- **Cada tarea cita sus requisitos**: `_Requisitos: N.m_`.
- **Cada tarea entregada se anota**: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- **Test primero (§VII)**: rojo antes que implementación. Ningún `skip`.
- **Aislamiento (§I)**: garantía 1, rozada. Su test es T004.
- **Licencias (§VIII)**: no entra ninguna dependencia.
- **Medidor**: nada nuevo.
- **Sin commits**: los hace Luis.
- **La consola** (`apps/console`) tiene su propio reparto: aquí solo API y worker.

## Format: `[ID] [P?] Description`

- **[P]**: se puede hacer en paralelo (ficheros distintos, sin dependencias pendientes)

---

## Fase 1: Tests en rojo

- [X] T001 [P] `apps/api/tests/unit/test_attention_071.py`: la regla del partner (partida al 80 % y al 100 %; cuenta baja por el 20 %, por los 7 días y por el aviso; vacía; cobro); la gravedad del contrato; el orden (gravedad, partner primero, `ATTENTION_REASONS`, `ref`); la tabla de avisos de condición igual a la de spec §2.1; los umbrales iguales a los de `build_budget` y `wallet_alerts`.

  _Requisitos: 1.1, 1.2, 2.1_
- [X] T002 [P] `apps/api/tests/integration/attention/test_attention_list.py`: `GET /console/attention` con filas del partner y de clientes, `scope`, `severity`, `data` y orden; `/console/home` → `panel.attention` es la misma lista; quien no asigna ve «Pedir saldo»; la persona de facturación no ve clientes; sin el módulo `billing` no hay fila de cobro; `errors` vacío.

  _Requisitos: 1.1, 1.3, 1.4, 4.4_
- [X] T003 [P] `apps/api/tests/integration/attention/test_resolve_cleared.py`: se resuelve al asignar saldo, al subir el tope del agente, al subir la partida (admin), al empezar el mes (repaso horario), al volver la cuenta a tener saldo, al volver la suscripción a `current`, y al reconectarse el canal (webhook de Meta, con un segundo problema que vuelve a avisar); no se resuelve lo que sigue en la lista ni «bajo» mientras está «agotado»; los informativos no se tocan; resolver no envía nada.

  _Requisitos: 2.1, 2.2, 2.3, 2.5_
- [X] T004 [P] `apps/api/tests/isolation/test_071_attention_scope.py`: dos partners con la consola nueva y condiciones en los dos; la lista, el Panel, la campana y su contador de cada uno solo dicen lo suyo, ni un `ref` ni un nombre del otro; «Marcar todo» y `resolve_cleared` de uno no tocan los avisos del otro, ni uno del otro que lleve el mismo `ref`.

  _Requisitos: encabezado (garantía 1), 1.1, 2.2, 3.1_
- [X] T005 [P] `apps/api/tests/integration/attention/test_bell_071.py`: `condition` en cada aviso; `unread-count` sin los de condición y `read-all` solo los informativos, para la consola nueva; la de antes, como hoy.

  _Requisitos: 3.1, 3.3_
- [X] T006 [P] `apps/worker/tests/unit/test_attention_071_worker.py`: `build.budget.*` sale al partner sin cliente; el repaso horario resuelve a cada partner con la consola nueva; `attention-resolve-cron` está en el planificador (`test_bootstrap_split.py`).

  _Requisitos: 2.3, 2.4_

## Fase 2: La regla y la lista

- [X] T010 `services/attention.py`: `PARTNER_REASONS`, `PartnerFacts`, `partner_attention()`, gravedad, arreglos del partner, `AttentionItem`, `order_items()`, `CONDITION_CODES` y `COVERED_BY`. `FIXES` y `REQUEST_INSTEAD` pasan aquí desde `partner_panel`.

  _Requisitos: 1.1, 1.2, 2.1_
- [X] T011 `services/attention_live.py`: `Gate`, `live_attention()` (lecturas del partner y de los clientes, puerta, `errors`, lo leído) y `account_facts()` (research.md §R2–R3). `BagBlock.balance_micros`; `client_overview.read_client` cuenta también los conectores en `needs_reauth` (§R8).

  _Requisitos: 1.1, 1.2, 1.4_
- [X] T012 `GET /console/attention` (`api/console/attention.py`), `PanelAttentionOut` ampliada y `AttentionListOut`; el Panel (`partner_panel.build_panel`, `home._panel`) lee la misma lista con la puerta de quien mira (§R10).

  _Requisitos: 1.1, 1.3, 1.4, 4.4_

## Fase 3: Los avisos que se resuelven solos

- [X] T020 `resolve_cleared`, `resolve_cleared_detached`, `resolve_cleared_for_tenant` (plan §3, research.md §R4, §R6, §R7).

  _Requisitos: 2.2, 2.5_
- [X] T021 Llamadas: `client_bags` (asignar, mover, tope del agente), `admin/partner_money` (partida), `whatsapp_account_events` (cuenta reconectada, alerta resuelta), `connectors/service` (consentimiento activo, clave nueva).

  _Requisitos: 2.3_
- [X] T022 Worker: `attention_resolve_tick` y `run_attention_resolve_cron` (cada hora) en `wallet_crons.py` y en el planificador; el relleno del día 1 resuelve tras reanudar los topes; `_record_build_line` emite `build.budget.*` al partner con `emit_detached`, sin `external_client_ref`.

  _Requisitos: 2.3, 2.4_

## Fase 4: La campana

- [X] T030 `NotificationOut.condition`; `Viewer.conditions`; `unread-count` y `unread` sin los de condición; `read-all` solo los informativos (research.md §R6, §R7).

  _Requisitos: 3.1, 3.3_

## Fase 5: Cierre

- [X] T040 La suite entera de la API y la del worker, `ruff` y `mypy`.
