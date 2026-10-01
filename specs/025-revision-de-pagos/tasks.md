# Tasks: el equipo confirma o rechaza los pagos desde WhatsApp

**Input**: documentos de diseño de `/specs/025-revision-de-pagos/`

**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/payment-review.md

**Tests**: NO son opcionales (constitución §VII): cada bloque se escribe
primero, se ve en rojo, y solo entonces se implementa.

**Organization**: H1 = el comprobante llega con botones · H2 = la pulsación
resuelve y el cliente se entera · H3 = el partner elige revisores · H4 =
Conversaciones (iteración 2). **Orden de entrega**: datos → herramienta (H1)
→ resolución (H2) → Ajustes (H3) → cierre. Iteración 2 al final.

## Reglas de este repo *(constitución)*

- Cada tarea cita sus requisitos: `_Requisitos: N.m_`.
- Cada tarea entregada se anota: `Entregado: rama, YYYY-MM-DD`.
- Test primero; aislamiento con tarea propia (T-ISO); licencias (T-LIC);
  medidor (T-MET).
- Cierre: suites en verde → evidencia → KB → merge a `develop` → staging.

## Format: `[ID] [P?] [Story] Description`

## Phase 1: Setup

- [X] T001 Migración `apps/api/alembic/versions/0137_payment_reviews.py`: tablas `payment_reviews` y `payment_review_notices` con las columnas, CHECK, índice y único de `data-model.md`, RLS forzada con `*_tenant_isolation`; fila `payments.request_review` en `tool_catalog`; filas `payment_review.opened`/`payment_review.resolved` en `console_audit_vocabulary`. Downgrade simétrico. _Requisitos: 1.1, 2.1, 5.2_ Entregado: `025-revision-de-pagos`, 2026-10-01.
- [X] T002 [P] Modelos `PaymentReview` y `PaymentReviewNotice` en `apps/api/src/nexus_api/db/models/payment_review.py`, exportados en `db/models/__init__.py`. _Requisitos: 1.1_ Entregado: `025-revision-de-pagos`, 2026-10-01.

## Phase 2: Foundational

- [X] T003 [P] Test rojo `apps/api/tests/unit/test_agent_payment_review.py` y servicio `apps/api/src/nexus_api/services/agent_payment_review.py` (`reviewers_of`, `apply_reviewers`, `ReviewerInvalidPhone` con `.code`), espejo de `agent_audience.py`: normaliza con `to_e164`, deduplica, descarta inútiles con error, máx. 10, conserva nombre. _Requisitos: 4.1_ Entregado: `025-revision-de-pagos`, 2026-10-01.

## Phase 3: Historia 1 — el comprobante llega con botones (P1)

- [X] T004 [H1] Test rojo (escrito contra Postgres en `apps/api/tests/unit/test_payment_reviews_resolve.py`, porque las pruebas de MCP no tienen base de datos; la herramienta es un envoltorio fino de `open_review`): sin revisores → `ToolError` que nombra `escalate.escalate_to_human`; dos revisores con ventana abierta → revisión `pending`, dos avisos `interactive`, por revisor un mensaje con el comprobante y otro con botones `prv:<token>:ok|no`; revisor con ventana cerrada → aviso `undelivered`/`window_closed`; segundo comprobante con pendiente → se suma, `already_pending=true`, sin avisos nuevos; `link` con `processing` → `informed` y mensaje sin botones; el texto al cliente no contiene números ni nombres de revisores. _Requisitos: 1.1–1.6, 6.1–6.3_ Entregado: `025-revision-de-pagos`, 2026-10-01.
- [X] T005 [H1] Servidor `apps/mcp/src/nexus_mcp/servers/payments/` (`schemas.py`, `tools.py`, `__init__.py`) con `RequestPaymentReview` y registro en `apps/mcp/src/nexus_mcp/registry.py`; conteo del registro 60 → 61 en `apps/mcp/tests/test_registry_unit.py`, de `tool_catalog` 31 → 32 en `apps/api/tests/unit/test_repo_tool_catalog.py`. _Requisitos: 1.1–1.6_ Entregado: `025-revision-de-pagos`, 2026-10-01.
- [X] T006 [P] [H1] Nombre de negocio en `apps/api/src/nexus_api/api/console/capability_names.py`: «Pedir revisión de un pago», función `orders`. _Requisitos: 1.1_ Entregado: `025-revision-de-pagos`, 2026-10-01.

## Phase 4: Historia 2 — la pulsación resuelve y el cliente se entera (P1)

- [X] T007 [H2] Test rojo `apps/api/tests/unit/test_payment_reviews_resolve.py` y servicio `apps/api/src/nexus_api/services/payment_reviews.py::resolve_tap`: primera pulsación `ok` → `confirmed`, encola acuse, aviso al otro revisor y texto al cliente con fecha y rango; `no` → `rejected`, texto de rechazo y `agent_active=false` con `takeover_context`; segunda pulsación → no cambia y responde quién; remitente no avisado → nada; cliente con ventana cerrada → `customer_notified=false`; auditoría `payment_review.resolved`. _Requisitos: 2.1–2.5, 3.1–3.3, 5.2_ Entregado: `025-revision-de-pagos`, 2026-10-01.
- [X] T008 [H2] Test rojo `apps/api/tests/unit/test_webhook_payment_review_tap.py` y desvío en `apps/api/src/nexus_api/api/webhooks/meta.py` tras el preludio: `payload_id` que empieza por `prv:` → `resolve_tap` y 200 sin encolar; otro `payload_id` sigue al agente. _Requisitos: 2.4, 2.6_ Entregado: `025-revision-de-pagos`, 2026-10-01.
- [X] T-ISO [H2] `apps/api/tests/isolation/test_payment_reviews_scope.py`: revisión de A invisible bajo el scope de B; un token de A pulsado en el número de B no resuelve. _Requisitos: 2.5_ Entregado: `025-revision-de-pagos`, 2026-10-01.

## Phase 5: Historia 3 — el partner elige revisores (P2)

- [X] T009 [H3] Test rojo `apps/api/tests/unit/test_endpoint_console_agent_settings_payment_review.py`; `payment_review` en `AgentSettingsIn/Out` (`schemas_agent_tools.py`), GET/PUT en `agent_settings.py` (422 `payment_reviewer_invalid_phone` con `phone`), fila `payment_review` en `agent_drafts.settings_changes`. _Requisitos: 4.1, 4.2_ Entregado: `025-revision-de-pagos`, 2026-10-01.
- [X] T010 [H3] Consola: sección «Revisión de pagos» en `agent-settings-form.tsx` con un editor de filas (`reviewers-editor.tsx`, reutiliza `audience-lines.ts`), tipos en `lib/backend/agent-tools-types.ts`, `putAgentSettings` con `payment_review`, claves i18n en `i18n/lanes/agent-tools.ts` y `record.ts` (sin punto y coma), valor del borrador en `draft-setting-value.ts`; tests vitest. _Requisitos: 4.1, 4.2, 4.5_ Entregado: `025-revision-de-pagos`, 2026-10-01.

## Phase 6: Cierre de la iteración 1

- [X] T-LIC Ninguna dependencia nueva en `pyproject.toml` ni `package.json`. Entregado: `025-revision-de-pagos`, 2026-10-01.
- [X] T-MET Avisos y respuestas son filas salientes que mide el despachador; la pulsación no llama al modelo (aserción en T007: cero llamadas al modelo). Entregado: `025-revision-de-pagos`, 2026-10-01.
- [ ] T011 Ruff, mypy, typecheck y lint; suites de API, MCP y consola en verde; merge a `develop`; staging.
- [ ] T012 Prompt de Flor y Encanto: paso 7 llama a `payments.request_review`; KB y memoria.

## Phase 7: Iteración 2 — ventana cerrada y Conversaciones

- [ ] T013 Tipo `button` en `apps/channels/.../webhook_adapter.py` → `InteractiveReply(kind="quick_reply")`. _Requisitos: 1.3_
- [ ] T014 Plantilla de utilidad con tres respuestas rápidas creada en un clic desde Ajustes; aviso por plantilla con la ventana cerrada; «Ver comprobante» manda el adjunto y los botones. _Requisitos: 1.3, 4.3_
- [ ] T015 Marca «pago por revisar» y resultado en Conversaciones; lectura del Companion. _Requisitos: 5.1, 5.3_

## Dependencies

T001 → T002 → (T003 ∥ T006) → T004 → T005 → T007 → T008 → T-ISO → T009 → T010 → cierre.
