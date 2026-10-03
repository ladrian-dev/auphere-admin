# Bug Assessment: una prueba en el Playground cuenta como canal conectado y primera conversación

- **Slug**: el-playground-cuenta-como-canal-y-conversacion
- **Created**: 2026-09-23
- **Source**: auditoría UX de la consola, evidencia viva del 2026-09-22 (KB `nexus/AUDITORIA-UX-CONSOLA-2026-09-22.md`, problema transversal T1)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim)

> **La pantalla miente en tres sitios**: onboarding marca «Conecta un canal de
> WhatsApp» y «Recibe la primera conversación» como hechos porque el Playground crea
> un canal `web / qa_playground` activo y una conversación; la portada cuenta
> «Conversaciones del mes 1» y la pestaña Conversaciones lista la prueba como canal
> «Web».

Partner `demo-audit`, cliente `panaderia-la-espiga` recién creado, sin WhatsApp.
Tras un único mensaje en el Playground:

- `/`: «Primeros pasos 4 de 5 completados», con «Conecta un canal de WhatsApp» y
  «Recibe la primera conversación» tachados; «Conversaciones del mes: 1».
- `/clients/panaderia-la-espiga/conversations`: una fila «Abierta · Web · 2 turnos».
- La ficha sigue diciendo «Falta: WhatsApp conectado» (esa sí es verdad).
- En BD: `channels` tiene una fila `type=web, provider=qa_playground, status=active`
  para el tenant, y `conversations` una fila sobre ese canal.

## Symptom

Tres pantallas afirman que el cliente ya atiende clientes cuando solo se ha
probado el agente. El copy de Consumo y de Alertas promete lo contrario («las
pruebas del playground no cuentan»). Viola el principio V de la constitución y
deja el onboarding sin sentido: los dos pasos que de verdad faltan aparecen hechos.

## Reproduction

1. Stack local; partner con un cliente sin canal de WhatsApp.
2. Abrir el Playground del cliente, «Nueva conversación», enviar cualquier texto.
3. Volver a `/`: la checklist marca canal y primera conversación; el contador de
   conversaciones del mes vale 1. Abrir Conversaciones del cliente: una fila «Web».

## Suspected Code Paths

- `apps/api/src/nexus_api/api/qa.py:438-487` — `_ensure_qa_channel` crea a
  propósito un `Channel(type=WEB, provider="qa_playground", status=ACTIVE)` por
  tenant para que las conversaciones de QA tengan canal propio. Correcto por diseño.
- `apps/api/src/nexus_api/api/console/onboarding.py:107-131` —
  `channel_connected` = cualquier `Channel.status == ACTIVE`; `conversations` =
  cualquier `Conversation`. Ni uno ni otro distinguen el canal de QA.
- `apps/api/src/nexus_api/services/console_home.py:88-100` — `_snapshot_stmt`
  cuenta todas las `Conversation` del mes y todos los `Message` fallidos.
- `apps/api/src/nexus_api/api/console/conversations.py:75-92, 128-158` — lista y
  estadísticas sin filtro de canal.

## Root Cause Hypothesis

El canal de QA se introdujo como «un canal más» (ADR-020, cierre de la fase 5) para
que el Playground funcionara antes de conectar WhatsApp. Las tres consultas de la
consola que hablan de «clientes» se escribieron sin conocer esa fila, y como el
canal está `active`, cumplen todas las condiciones.

## Proposed Remediation

Una sola definición de «tráfico de clientes» en un módulo de servicio
(`services/console_traffic.py`): predicado `customer_facing_channel()` (`provider !=
"qa_playground"`) y sub-select `customer_conversation_ids()`. Las tres consultas
lo usan; la constante `QA_PLAYGROUND_PROVIDER` pasa al modelo `channel.py` y
`api/qa.py` la importa de ahí para que no haya dos literales.

Se **excluye** (no se etiqueta) el tráfico de QA de la lista de Conversaciones y
de sus estadísticas: el Playground ya tiene su propia lista de hilos y el copy de
esa pantalla remite al Playground para depurar.

## Files likely to change

- `apps/api/src/nexus_api/db/models/channel.py` (constante)
- `apps/api/src/nexus_api/services/console_traffic.py` (nuevo)
- `apps/api/src/nexus_api/api/qa.py` (importa la constante)
- `apps/api/src/nexus_api/api/console/onboarding.py`
- `apps/api/src/nexus_api/services/console_home.py`
- `apps/api/src/nexus_api/api/console/conversations.py`
- `apps/api/tests/unit/test_endpoint_console_home_usage.py` (test de regresión)

## Tests to add or update

- Un test que siembre agente activo + canal `qa_playground` activo + conversación +
  mensaje fallido y compruebe: onboarding `channel_connected=false`,
  `first_conversation=false`; home `conversations_period.count == 0` y sin
  incidencia de fallidos; conversaciones `total == 0` y stats a cero.

## Risks & Considerations

- Solo lectura: no cambia qué se guarda, solo qué se cuenta. Sin migración.
- Un futuro widget web de clientes finales (también `type=web`) seguirá contando
  porque el filtro es por `provider`, no por tipo.
- `Message` no tiene tenant-scoped join directo con `Channel`; el filtro va por
  `conversation_id IN (…)`, que RLS acota igual.

## Open Questions

- Ninguna.
