# Evidencia del quickstart (T184) · 2026-10-28

Cada paso de `quickstart.md` §2 y §3, con las pruebas automáticas que lo recorren.
Se comprobó en cada archivo que la prueba existe y cubre el paso. Lo que solo se
puede ver en staging, en un teléfono o con un modelo real queda al final, sin
inventar cobertura.

Prefijos: `A/` = `apps/api/tests/`, `W/` = `apps/worker/tests/unit/`,
`C/` = `apps/console/` (vitest en `src/components/<área>/__tests__/`, Playwright en
`e2e/` contra la API simulada), `M/` = `apps/mobile/`, `D/` = `apps/admin/src/app/(dashboard)/`.

## §2 — Recorridos por ola

| Paso | Qué se comprueba | Pruebas | Cobertura |
|---|---|---|---|
| 1.1 | Bolsa vacía: el mensaje se guarda y espera «Sin saldo»; avisa al partner y a la persona | `A/integration/test_dispatcher_persist_first.py::test_an_empty_bag_still_saves_the_message`, `A/integration/test_dispatcher_reason_notices.py::test_no_balance_tells_the_partner_and_the_client_once_a_day`, `::test_with_the_inbox_the_people_hear_once_per_wait`; textos en `M/__tests__/fabrica-avisos.test.tsx` | Completa (por `process_inbound`, no por el webhook HTTP) |
| 1.2 | Tres mensajes en < 3 s, un turno | `A/integration/test_turn_coalescing.py` (3 pruebas) | Completa |
| 1.3 | Un turno reintentado no duplica reserva ni respuesta | `A/integration/test_turn_effects_idempotent.py` (2), `test_dispatcher_persist_first.py::test_a_retried_entry_does_not_save_the_message_twice` | Completa (la caída se simula) |
| 2.1 | Tres datos, chips, el correo no es una web | `A/unit/test_link_detection.py`, `A/integration/clients/test_create_three_fields.py`, `C/e2e/new-client.spec.ts`, `client-modal.test.tsx` | Completa |
| 2.2 | El Panel con la lectura; lo leído para revisar; lo que contradice queda como sugerencia | `C/e2e/new-client.spec.ts`, `A/integration/clients/test_client_panel.py`, `test_client_read_job.py` (3), `client-read-card.test.tsx` | Completa |
| 2.3 | Turno nocturno, fecha especial cerrada y con horario, la frase | `A/unit/test_business_hours_engine.py` (4), `A/integration/business/test_hours_and_locations.py` (2), `hours-section.test.tsx` | Parcial: el editor de fechas especiales de la consola del partner no tiene prueba de interacción (sí la lite y la app) |
| 2.4 | Servicios sin duración, gratis, en CLP y «Solo Ventas mayoristas» | `A/integration/business/test_services.py` (5), `services-section.test.tsx` | Completa |
| 2.5 | Marta cambia el horario desde la app; el siguiente mensaje lo usa; el partner ve el aviso y la procedencia | `A/integration/lite/test_lite_agents_business.py::test_the_hours_need_if_match_and_carry_the_person_and_where`, `A/integration/business/test_next_message_uses_ficha.py`, `test_provenance_history.py::test_a_change_by_the_clients_person_tells_the_partner_once_an_hour`, `M/__tests__/negocio.test.tsx` | Parcial: la escritura del horario se prueba con origen `lite_web`; `app` se prueba en pausas y políticas. El texto del quickstart decía «Escrito por…»; se corrigió a «Editado por…», que es lo que dice el producto |
| 3.1 | «Nuevo agente» por bloques, ≤ 5 preguntas, cuántas descartó | `A/integration/builder/test_agent_draft_job.py` (4), `C/e2e/builder.e2e.ts`, `builder-new.test.tsx` | Parcial: los 30 s con un modelo real, en staging |
| 3.2 | Playground con hora y agenda simuladas | `A/integration/builder/test_playground_draft.py` (2), `C/e2e/agent-quality.e2e.ts`, `agent-playground.test.tsx` | Completa |
| 3.3 | 8 + 12 pruebas, 3 pasadas, inestable y crítica | `test_agent_draft_job.py` (2), `A/integration/builder/test_agent_suite.py`, `test_review_and_catalog.py`, `C/e2e/agent-quality.e2e.ts` | Completa |
| 3.4 | La puerta bloquea; el builder no la salta, el owner sí con motivo | `A/integration/builder/test_publish_gate.py`, `publish-bar.test.tsx` (2), `C/e2e/agent-quality.e2e.ts` | Completa |
| 3.5 | Guardar, «Deshacer» antes de 10 min, «Restaurar» | `A/integration/builder/test_versions.py` (2), `publish-bar.test.tsx`, `agent-history.test.tsx` | Completa |
| 4.1 | Pausar y reanudar desde la consola y la app, con motivo y autor | `A/integration/agents/test_agent_lifecycle.py` (2), `test_lite_agents_business.py` (2), `C/e2e/agent-life.e2e.ts`, `M/__tests__/agentes.test.tsx` | Completa (el flujo de Maestro necesita un dispositivo) |
| 4.2 | Conectar WhatsApp desde el agente (asistente de la 046) | Modo prueba: `A/integration/channels/test_channel_config.py`, `test_owner_link.py`; «El número lo conecta Auphere»: `whatsapp-connect.test.tsx`; catálogo: `D/channels/__tests__/catalog-grid.test.tsx` | Parcial: el asistente desde el agente, la pregunta de coexistencia y «Próximamente» desde el agente esperan a la 046 (T101, T107, T109, T115) |
| 4.3 | Enlace del dueño: crear, copiar, uno pendiente, revocar | `A/integration/channels/test_owner_link.py` (2), `agent-channels.test.tsx` (3), `C/e2e/agent-channels.e2e.ts` | Completa (el enlace en un teléfono real, en staging) |
| 4.4 | Página del canal: audiencias, escalado, deshacer | `test_channel_config.py` (3), `test_escalation_recipients.py`, `channel-page.test.tsx`, `C/e2e/agent-channels.e2e.ts` | Completa |
| 4.5 | Eco de coexistencia: «La lleva una persona» 2 h | `A/integration/channels/test_coexistence_events.py` | Completa (un número real, en staging) |
| 5.1 | Google Calendar una vez, dos agentes con permisos distintos, un tercero sin herramientas | `A/integration/connectors/test_activations.py` (3), `A/isolation/test_45_tools_only_from_activations.py` (2) | Parcial: API y runtime (Composio simulado). La pestaña Conectores del agente (T129) está en construcción. OAuth real, en staging |
| 5.2 | «Enseñar» con «Solo este agente»; el hermano no lo sabe | `A/integration/knowledge/test_layers.py` (2), `A/isolation/test_44b_agent_knowledge.py`, `agent-knowledge.test.tsx`, `C/e2e/agent-channels.e2e.ts` | Completa (en el prompt y la búsqueda) |
| 6.1 | «Automático» y `llm.route_decision` con sus campos | `W/test_router_policy.py`, `W/test_pipeline_router.py` (2) | Completa con un catálogo sintético; con el de hoy un agente «Automático» da `no_model` (D44) |
| 6.2 | Argumento inválido: escala en subllamada | `W/test_pipeline_router.py` (2), `W/test_router_policy.py` | Parcial: ninguna prueba lee la línea `llm.route_decision` con `escalated=true` |
| 6.3 | «No disponible» en el admin; el turno siguiente usa la alternativa | `A/integration/models/test_model_lifecycle.py`, `test_admin_models_api.py`, `D/models/__tests__/deployment-dialogs.test.tsx` | Completa (en la elección de ruta) |
| 6.4 | «Solo UE» sin alternativa: «Sin modelo disponible» | `W/test_router_policy.py`, `W/test_pipeline_router.py`, `A/integration/test_react_final_answer.py[no_model]`, `test_dispatcher_persist_first.py::test_no_model_available_saves_and_waits` | Parcial: las palabras en pantalla no tienen prueba |
| 6.5 | Calidad: «Máximo», precio estimado, «Comprobando la calidad…» | `A/integration/models/test_agent_quality.py` (2) | Parcial: API. La pantalla Avanzado › Calidad (T147) está en construcción |
| 7.1 | Asignar 20 USD desde una cuenta en EUR con el cambio del BCE | `A/integration/wallet/test_assign_and_request.py`, `test_bags_ledger.py`, `assign-dialog.test.tsx` (2), `C/e2e/money.spec.ts` | Completa |
| 7.2 | Bajar, mover, «Rellenar cada mes hasta 50», día 1 con la cuenta corta | `A/integration/wallet/test_bags_ledger.py` (4), `assign-dialog.test.tsx` | Parcial: los diálogos de mover y rellenar de la consola no tienen prueba |
| 7.3 | Tope de 15 USD: aviso al 80 %, al 100 % «Tope del agente» y el resto sigue | `A/integration/wallet/test_agent_cap_and_alerts.py` (2), **nueva** `A/integration/agents/test_agent_lifecycle.py::test_an_agent_at_its_cap_keeps_the_messages_as_tope_del_agente`, `money-entry-points.test.tsx` | Completa |
| 7.4 | «Pedir saldo» dos veces: «Pedido hace…» | `test_assign_and_request.py` (2), `money-entry-points.test.tsx`, `C/e2e/money.spec.ts` | Completa |
| 7.5 | Consumo: partidas, gráfica 7/30/90, CSV | `A/integration/wallet/test_usage_lines.py` (3), `C/e2e/money.spec.ts` | Completa |
| 8.1 | ⌘K «Recep» | `C/e2e/shell.spec.ts`, `console-command-palette-v2.test.tsx`, `A/integration/test_console_search.py` | Completa (contra el mock) |
| 8.2 | 390 px sin desbordar; «Reducir transparencia» | `C/e2e/shell.spec.ts`, `fabrica-lite.e2e.ts`, `fabrica-partner.e2e.ts` y los 390 px de las demás e2e | Parcial: los barridos de todas las pantallas (`a11y.spec.ts`, `lite.spec.ts`) necesitan la API sembrada y no se corrieron |
| 8.3 | App: Agentes y Negocio sin conexión; los avisos push abren su pantalla | `M/__tests__/agentes.test.tsx`, `negocio.test.tsx`, `fabrica-avisos.test.tsx`, `A/integration/test_push_fanout.py` | Completa en Jest y la API (push real y simulador, en un dispositivo) |
| 9.1 | Sugerencias de la semana sin cuerpos de mensaje | `A/integration/improvement/test_suggestions.py` (3), `A/isolation/test_52_partner_never_sees_bodies.py` (2) | Completa con un modelo simulado (8 conversaciones, no 12) |
| 9.2 | «Corregir esta respuesta»: un dato se aplica, un comportamiento llega al partner | `A/integration/improvement/test_corrections.py` (4), `M/__tests__/corregir.test.tsx`, `C/e2e/fabrica-lite.e2e.ts` | Completa |
| 9.3 | Recepción deriva y a la tercera ida y vuelta pasa a una persona | `W/test_pipeline_reception.py`, `A/integration/reception/test_reception_handoff.py` (2), `C/e2e/fabrica-partner.e2e.ts` | Completa con un modelo guionado |
| 10.1 | Ensayo con la copia anonimizada | `A/integration/migration/test_console_v2_dry_run.py` (2), `D/partners/[id]/console-v2/__tests__/console-v2.test.tsx` | Parcial: la copia real es de staging (T181) |
| 10.2 | Activar, repartir en bolsas y desactivar antes de confirmar | `test_console_v2_dry_run.py::test_disabling_is_possible_only_until_the_wallet_split_is_confirmed`, `test_bags_ledger.py::test_the_split_into_bags_can_be_adjusted_before_confirming`, `A/integration/test_console_me_version.py`, `layout.test.tsx`, `console-v2.test.tsx` | Parcial: cada pieza, no el flujo entero en una prueba |

## §3 — Estados en cada pantalla

| Qué | Pruebas | Cobertura |
|---|---|---|
| Ideal, vacío, cargando, error con «Reintentar», parcial | `C/e2e/fabrica-lite.e2e.ts` (Agentes y Negocio), `fabrica-partner.e2e.ts`, vitest de lectura, ficha, búsqueda, conocimiento y canales, `M/__tests__/states.test.tsx` | Parcial: faltan Consumo, la lista y el Panel del cliente, y «Nuevo agente» |
| Sin permiso, la acción no aparece | `publish-bar`, `hours-section`, `services-section`, `channel-page`, `agent-history`, `money-entry-points`, `A/integration/test_console_search.py`, `M/__tests__/agentes.test.tsx` | Completa por componente |
| Claro y oscuro | `C/e2e/lite.spec.ts` (claro y oscuro, no corrido), `shell.spec.ts` | Parcial |
| «Reconectando» | La Bandeja: `fabrica-lite.e2e.ts`, `inbox-view.test.tsx`, `M/__tests__/states.test.tsx` | Parcial: el progreso del constructor y el playground no |
| Alemán largo y 200 % | `fabrica-partner.e2e.ts`, `fabrica-lite.e2e.ts`, `shell.spec.ts`, `agent-draft.e2e.ts`, `new-client.spec.ts`, `client-records.spec.ts` | Parcial: Consumo, la página del canal y el constructor solo a 390 px |

## Lo que solo se ve en staging o en un dispositivo

- El borrador en menos de 30 s con un modelo real (3.1).
- Embedded Signup v5 y la coexistencia con un número de verdad (4.2, 4.5).
- El enlace del dueño en iOS y Android (4.3).
- OAuth real de Google (5.1).
- Una ruta en proveedores reales (6.1, por D44).
- Push real y el flujo de Maestro `agentes-negocio.yaml` en un simulador (2.5, 4.1, 8.3): esta máquina no tiene CocoaPods y nunca compiló iOS.
- Sugerencias y Recepción con un modelo real (9.1, 9.3).
- La copia anonimizada de producción (10.1, T181).
- Las capturas en oscuro (§3).
- `C/e2e/a11y.spec.ts` y `lite.spec.ts` con la API sembrada (8.2, §3).
