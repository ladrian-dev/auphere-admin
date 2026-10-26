# Contrato — estados, motivos, avisos, auditoría y eventos

Lo que la API, el worker, la consola, la consola lite y la app tienen que
nombrar igual. Los códigos son estables; los textos en español son los de la
interfaz.

## 1. Estados

### 1.1 Estado de vida del agente (se guarda)

| Código | Cuándo |
|---|---|
| `draft` | Nunca publicado |
| `published` | Tiene versión activa y no está en pausa ni archivado |
| `paused` | En pausa, con `pause_reason` |
| `archived` | Archivado; se restaura a `paused` (requisito 28.2) |

`pause_reason`: `manual`, `no_balance`, `agent_cap`, `client_paused`,
`client_archived`. Cada pausa guarda también quién la puso (persona o sistema),
desde dónde (`console`, `lite_web`, `app`, `admin`, `api`, `system`) y el estado
anterior, para devolverlo al reanudar (requisitos 6.5 y 27.3).

### 1.2 Estado del canal

**Se guarda** `channels.status` (`active`, `paused`, `degraded`, `disconnected`),
con `problem_reason` cuando es `degraded`: `quality`, `auth_expired`,
`coexistence_inactive` (unos 14 días sin abrir la app) o `meta_error`. También se
guarda `audience_mode` (`unset`, `team_only`, `everyone`).

**Se deriva** el estado visible, en este orden:

| Código | Regla | Texto | Tono |
|---|---|---|---|
| `pending_link` | Enlace del dueño pendiente y sin número todavía | «Pendiente · enlace enviado» | info |
| `disconnected` | `status = disconnected` | «Desconectado» | muted |
| `problem` | `status = degraded` | «Con problemas · {motivo}» | danger |
| `paused` | `status = paused` | «En pausa» | warn |
| `unconfigured` | `audience_mode = unset` | «Sin configurar» | muted |
| `team_only` | `audience_mode = team_only` | «Solo mi equipo» | info |
| `everyone` | `audience_mode = everyone` | «A todos» | positive |

### 1.3 Estado visible del agente (se deriva, un solo cálculo en la API)

En este orden, la primera regla que se cumple:

| Código | Texto | Tono | Regla |
|---|---|---|---|
| `archived` | «Archivado» | muted | vida = `archived` |
| `paused` | «Pausado · {motivo}» | warn | vida = `paused` |
| `draft` | «Borrador» | muted | vida = `draft` |
| `serving` | «Atendiendo» | positive | algún canal `everyone` |
| `testing` | «En prueba» | info | algún canal `team_only` y ninguno `everyone` |
| `ready_no_channel` | «Listo · sin canal» | info | publicado sin canales configurados |

Un canal `paused` o `problem` no cuenta como `everyone` ni como `team_only`.
La consola, la consola lite, la app y el Panel del partner leen `visible_state`
de la API; ninguna lo recalcula (requisito 25.5).

### 1.4 Estado de la bolsa (se deriva)

`ok`, `low` (por debajo del 20 % de su base), `not_enough` (no llega a fin de mes
al ritmo de 7 días), `empty`. Los días restantes salen del ritmo medio de los
últimos 7 días completos; con menos de 3 días de consumo, `days_left` es nulo y
la interfaz dice «Aún no hay datos para estimarlo» (requisito 14.2).

## 2. Motivos de una conversación sin respuesta (lista cerrada)

Se guardan en la conversación (requisito 2.3). Salvo `out_of_audience`, la
conversación pasa a «Espera a una persona» en la Bandeja.

| Código | Texto en la Bandeja | Origen |
|---|---|---|
| `no_balance` | «Sin saldo» | Bolsa vacía |
| `agent_cap` | «Tope del agente» | Requisito 44.3 |
| `paused_agent` | «Agente en pausa» | Requisito 27 |
| `paused_channel` | «Canal en pausa» | Requisito 27 |
| `paused_client` | «Cliente en pausa» | Requisito 27 |
| `archived_client` | «Cliente archivado» | Requisito 6.4 |
| `channel_problem` | «Canal con problemas» | Requisito 2.2 |
| `agent_unpublished` | «Agente sin publicar» | Requisito 2.3 |
| `out_of_audience` | (no va a la Bandeja) | Requisito 32 |
| `no_model` | «Sin modelo disponible» | Requisito 40.7 |
| `provider_failure` | «El modelo falló» | Requisito 1.5 |
| `turn_limit` | «Límite del turno» | Requisito 40.10 |
| `escalated` | «Pidió una persona» / «{disparador}» | Requisito 33 |
| `human_takeover` | «La lleva una persona» | Una persona tomó el control, o un eco de coexistencia (requisito 30.11) |
| `reception_loop` | «Derivaciones en bucle» | Requisito 53.5 |

## 3. Avisos

Columnas: tipo · gravedad · a quién · por dónde · deduplicación · enlace.
«Partner» = destinatarios de alertas del partner, o owners y admins si no hay.
«Cliente» = todas las personas del cliente (campana, correo y push).

| Tipo | Gravedad | A quién | Por dónde | Deduplicación | Enlace |
|---|---|---|---|---|---|
| `client.wallet.low` | Aviso | Partner y cliente | Campana, correo, push | 1 al mes por cliente; se rearma al subir | Asignar saldo (partner) / Consumo (cliente) |
| `client.wallet.not_enough` | Aviso | Partner y cliente | Campana, correo, push | 1 al mes por cliente | Ídem |
| `client.wallet.empty` | Crítico | Partner y cliente | Campana, correo, push | 1 al día por cliente | Ídem |
| `client.wallet.refill_short` | Aviso | Partner | Campana, correo | 1 al mes | Consumo |
| `client.balance_request` | Aviso | Owners y admins | Campana, correo | 1 al día por cliente | Modal «Asignar saldo» |
| `agent.cap.warning` | Aviso | Partner y cliente | Campana, correo, push | 1 al mes por agente | Tope del agente |
| `agent.cap.reached` | Crítico | Partner y cliente | Campana, correo, push | 1 al mes por agente | Tope del agente |
| `agent.paused` / `agent.resumed` | Info | Partner (si lo hizo el cliente) y cliente (si lo hizo el partner) | Campana, push | Ninguna | Agente |
| `channel.paused` / `channel.resumed` | Info | Ídem | Campana, push | Ninguna | Canal |
| `channel.problem` | Crítico | Partner y cliente | Campana, correo, push | 1 por canal y motivo hasta que se resuelve | Página del canal |
| `channel.connected` | Info | Partner | Campana, correo | Ninguna | Página del canal |
| `integration.reauth_required` | Aviso | Partner | Campana, correo | 1 por conexión hasta que se resuelve | Página de la integración |
| `client.business_changed` | Info | Partner | Campana | Agrupa por cliente y hora | Negocio › sección |
| `client.read.done` / `client.read.failed` | Info / Aviso | Quien lanzó la lectura | Campana | Ninguna | Negocio |
| `agent.tests.failing` | Aviso | Partner | Campana | 1 por agente y día | Pruebas del agente |
| `agent.suggestions.ready` | Info | Partner | Campana | 1 por agente y semana | Rendimiento |
| `agent.correction.proposed` | Info | Partner | Campana | Ninguna | Mejoras del agente |
| `build.budget.warning` | Aviso | Owners, admins y builders | Campana, correo | 1 al mes | Consumo |
| `build.budget.exhausted` | Crítico | Owners, admins y builders | Campana, correo | 1 al mes | Consumo |
| `model.retirement` | Aviso | Partner con agentes fijados | Campana, correo | 1 por despliegue y partner, a 30 días y a 7 días | Calidad del agente |
| `model.price_change` | Aviso | Partner afectado | Campana, correo | 1 por cambio | Calidad del agente |
| `ops.build_budget_extension` | — | Auphere | Admin | 1 al día por partner | Partner en el admin |
| `ops.router_anomaly` | — | Auphere | Admin | Agrupa por tarea y hora | Router |
| `ops.ledger_mismatch` | — | Auphere | Admin, correo | 1 al día | Libro |
| `ops.meta_reconciliation` | — | Auphere | Admin, correo | 1 al día | Canales |

Al activar la consola nueva de cada partner, tres avisos de hoy se reemplazan por
los de esta tabla: `client.out_of_quota` y `client.balance_out` (por los de la
bolsa) y `qa.cap_reached` (por los de «Construcción y pruebas»). Hasta entonces
siguen como están. Los avisos de la cuenta del partner (`wallet.low` y
`wallet.empty`, al 80 % y al 100 %) y los del tope comercial de mensajes no cambian.

### 3.1 Push de la app Auphere Customers

| Tipo push | Pantalla que abre |
|---|---|
| `client.wallet.low`, `client.wallet.not_enough`, `client.wallet.empty` | Consumo |
| `agent.cap.warning`, `agent.cap.reached` | Agentes › {agente} |
| `agent.paused`, `agent.resumed` | Agentes › {agente} |
| `channel.paused`, `channel.resumed`, `channel.problem` | Agentes › {agente} |
| `inbox.waiting` (existe) | Bandeja › conversación, con el motivo |

El texto del push nunca lleva datos de un cliente final.

## 4. Auditoría

Categorías de hoy: Agentes, Conocimiento, Canales, Clientes, Consumo, Equipo,
Claves de API, Operador (más Teammates y Máquinas, fuera de alcance). Se añade
**Negocio** (la ficha). Toda fila lleva la persona (o Companion, Auphere, clave
de API, sistema) y el origen (`console`, `lite_web`, `app`, `admin`, `api`,
`system`).

| Categoría | Acciones nuevas | Sensible |
|---|---|---|
| Clientes | `client.created`, `client.updated` (antes y después), `client.archived`, `client.restored`, `client.deleted` | `client.deleted` |
| Negocio | `business.section_updated`, `business.section_undone`, `business.read_applied`, `business.correction_applied` | — |
| Agentes | `agent.created`, `agent.published` (resultado de la puerta y, si lo hubo, el motivo de saltarla), `agent.publish_undone`, `agent.version_restored`, `agent.paused`, `agent.resumed`, `agent.archived`, `agent.restored`, `agent.renamed`, `agent.default_changed`, `agent.quality_changed`, `agent.cap_changed` | `agent.published` con motivo |
| Constructor | `builder.proposal_decided` (entrada resumida, propuesta, decisión y coste) | — |
| Canales | `channel.connected`, `channel.config_updated`, `channel.config_undone`, `channel.moved`, `channel.paused`, `channel.resumed`, `channel.disconnected`, `owner_link.created`, `owner_link.revoked` | `channel.disconnected` |
| Integraciones | `connection.authorized`, `connection.disconnected_all`, `activation.changed` | `connection.disconnected_all` |
| Conocimiento | `source.added`, `source.removed`, `source.reread`, `knowledge.taught` (alcance) | — |
| Consumo | `wallet.assigned`, `wallet.lowered`, `wallet.moved`, `wallet.refill_set`, `wallet.currency_changed`, `balance.requested`, `build_budget.extension_requested` | — |
| Mejora | `suggestion.accepted`, `suggestion.discarded`, `correction.proposed` | — |
| Operador | `deployment.created`, `deployment.activated`, `deployment.retired`, `deployment.unavailable`, `router.policy_changed`, `certification.run`, `partner.console_v2_enabled`, `partner.build_budget_changed`, `beta.whatsapp_login_country`, `client.sovereign_set` | `deployment.unavailable` |

La agrupación «{n} más como esta» junta filas seguidas con la misma persona,
acción, cliente y día (requisito 49.1).

## 5. Eventos de log y trazas (garantía 6)

Todos llevan `tenant_id` y, cuando hay agente, `agent_id`. Ninguno lleva texto de
mensajes, cuerpos de herramientas ni teléfonos de clientes finales.

| Evento | Campos |
|---|---|
| `inbound.persisted` | `conversation_id`, `channel_id`, `message_id`, `gate` (`open` o el código de motivo) |
| `turn.coalesced` | `conversation_id`, `messages` (número), `window_ms` |
| `turn.effect` | `turn_id`, `effect` (`reserve`, `charge`, `send_link`, `reply`), `idempotency_key`, `replayed` |
| `llm.route_decision` | `turn_id` o `job_id`, `task`, `profile`, `policy_version`, `candidates_rejected` (lista de `{deployment, reason}`), `chosen`, `fallback_used`, `escalated`, `latency_ms`, `cost_micros`, `price_micros` |
| `builder.job` | `job_id`, `kind` (`agent_draft`, `client_profile`, `tests`, `fix`, `copilot`), `status`, `duration_ms`, `cost_micros`, `validator_errors` |
| `suite.run` | `run_id`, `version_id`, `policy`, `passed`, `flaky`, `failed`, `cost_micros` |
| `gate.decision` | `version_id`, `result` (`published`, `blocked`, `override`), `blocking` (códigos) |
| `wallet.transfer` | `transfer_id`, `kind`, `amount_micros`, `currency`, `fx_rate`, `fx_date` |
| `channel.echo_takeover` | `conversation_id`, `until` |
| `reception.handoff` | `conversation_id`, `from_agent_id`, `to_agent_id`, `hop` |

## 6. Avisos de Meta que se consumen (coexistencia, requisito 30)

| Campo del webhook | Efecto |
|---|---|
| `smb_message_echoes` | Guarda el mensaje como de una persona del negocio y pone la conversación en `human_takeover` durante 2 horas desde el último eco |
| `history` | Solo si el negocio aceptó importar: guarda los mensajes, marcados como históricos, sin abrir turnos ni avisos |
| `smb_app_state_sync` | Actualiza los contactos del negocio que Meta envía |
| `account_update` | Desconexión de la coexistencia o cambio de estado: el canal pasa a `problem` con su motivo y avisa (requisito 30.12) |
