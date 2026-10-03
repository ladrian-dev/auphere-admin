# Bug Fix: una prueba en el Playground cuenta como canal conectado y primera conversación

- **Slug**: el-playground-cuenta-como-canal-y-conversacion
- **Fixed**: 2026-09-23
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Hay ahora una sola definición de «tráfico de clientes» para la consola
(`services/console_traffic.py`): un canal es de clientes si su `provider` no es
`qa_playground`, y una conversación cuenta si vive en uno de esos canales. El
onboarding, la portada y la pestaña Conversaciones consultan a través de ese
módulo, así que las tres pantallas vuelven a decir lo mismo que el copy de Consumo:
las pruebas no cuentan. La constante del proveedor de QA vive en el modelo
`channel.py` y `api/qa.py` la importa de ahí.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/db/models/channel.py` | añadida `QA_PLAYGROUND_PROVIDER` | Con el porqué escrito al lado |
| `apps/api/src/nexus_api/services/console_traffic.py` | añadido | `customer_facing_channel()` y `customer_conversation_ids()` |
| `apps/api/src/nexus_api/api/qa.py` | modificado | `_QA_CHANNEL_PROVIDER` importa la constante compartida |
| `apps/api/src/nexus_api/api/console/onboarding.py` | modificado | `channel_connected` ignora el canal de QA; `first_conversation` solo cuenta conversaciones de clientes |
| `apps/api/src/nexus_api/services/console_home.py` | modificado | `_snapshot_stmt`: conversaciones del mes y mensajes fallidos filtrados |
| `apps/api/src/nexus_api/api/console/conversations.py` | modificado | Lista y `/stats` excluyen el canal de QA (el `outerjoin` conserva conversaciones sin canal) |
| `apps/api/tests/unit/test_endpoint_console_home_usage.py` | añadido test | `test_playground_channel_and_conversation_do_not_count_anywhere` |

## Diff Highlights

```py
# services/console_traffic.py
def customer_facing_channel() -> sa.ColumnElement[bool]:
    return Channel.provider != QA_PLAYGROUND_PROVIDER

def customer_conversation_ids() -> sa.Select[tuple[uuid.UUID]]:
    return (
        sa.select(Conversation.id)
        .join(Channel, Channel.id == Conversation.channel_id)
        .where(customer_facing_channel())
    )
```

```py
# api/console/onboarding.py — después
sa.select(Channel.id).where(Channel.status == ChannelStatus.ACTIVE, customer_facing_channel()).limit(1)
…
conversations = (await session.scalar(customer_conversation_ids().limit(1))) is not None
```

## Tests Added or Updated

`test_playground_channel_and_conversation_do_not_count_anywhere`: siembra agente
activo, canal `web/qa_playground` activo, una conversación sobre él y un mensaje
fallido, y comprueba en una pasada `GET /console/onboarding`
(`channel_connected=false`, `first_conversation=false`, `agent_published=true`),
`GET /console/home` (`conversations_period.count == 0`, sin incidencia de
fallidos), `GET …/conversations` (`total == 0`) y `GET …/conversations/stats`
(todo a cero).

## Local Verification

```
uv run ruff check … && uv run ruff format … && uv run mypy --strict …   # limpios
uv run pytest tests/unit/test_endpoint_console_home_usage.py \
              tests/unit/test_endpoint_console_onboarding.py \
              tests/unit/test_endpoint_conversations.py -x -q
  48 passed in 51.67s
```

En el navegador, tras reiniciar la API, con el partner `demo-audit` y el mismo
hilo de Playground de ayer: `/` dice **«Primeros pasos 2 de 5 completados»** (canal
y primera conversación vuelven a estar pendientes) y **«Conversaciones del mes 0»**;
la pestaña Conversaciones del cliente ya no lista la prueba.

## Deviations from Assessment

Ninguna.

## Follow-ups

- Cuando exista un widget web de clientes finales (`type=web`, otro `provider`),
  seguirá contando: el filtro es por proveedor a propósito.
- El aviso `client.activated` que llega con `can_serve: true` sin canal es el punto
  A4 del plan, no de este bug.
