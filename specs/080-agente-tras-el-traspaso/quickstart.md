# Quickstart: validar la spec 080

## Preparación

```bash
docker compose up -d postgres redis
export NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5433/nexus_test_080
export NEXUS_REDIS_URL=redis://localhost:6379/10
ps -eo pid,etime,command | grep "[p]ytest"   # nada vivo antes de lanzar
```

## Pruebas por requisito

| Requisito | Comando | Qué demuestra |
|---|---|---|
| 1 (garantía 8) | `cd apps/api && uv run pytest tests/isolation/test_080_booking_brake_customer_cycle.py tests/isolation/test_056_booking_brake_same_conversation.py -x` | La reserva del propio cliente hecha en el ciclo respalda. La de otro cliente, la cancelada y la anterior al ciclo no. |
| 1 (caso real) | `cd apps/api && uv run pytest tests/integration/test_booking_brake_turn.py -x -k acrilicos` | Reserva hecha desde la consola, devolución al agente y «gracias»: no hay paso a persona. |
| 2 | `cd apps/worker && uv run pytest tests/unit/test_intent_tool_filter.py tests/unit/test_pipeline_booking_brake.py -x` | `fallback` y `escalate` reciben las `reservas.*` del agente y nada fuera de su lista blanca. |
| 3 | `cd apps/api && uv run pytest tests/integration/reservas/test_080_find_slots_sin_fecha.py tests/integration/reservas/test_tools.py tests/integration/reservas/test_064_notice.py -x` | A las 13:24 con huecos desde las 16:00, el primer horario es el de hoy. Tope de 6, días cerrados saltados, `none_in_window`. Con fecha, igual que antes. |
| 3 (Playground) | `cd apps/worker && uv run pytest tests/unit/test_simulated_find_slots.py -x` | La agenda simulada da la misma forma. |
| 4 | `cd apps/api && uv run pytest tests/integration/reservas/test_080_cancel_del_agente.py -x` | El evento `cancelled` lleva `actor_kind=agent` y `data.by=customer`. |

## Al cierre

```bash
./scripts/verify.sh lint
cd apps/api && uv run pytest tests/isolation/test_45_tools_only_from_activations.py -x
```

## En staging, tras fusionar

Con un agente de prueba en Luna o en Haiku 5.5 y Reservas encendido:

1. Pide «quiero un corte lo antes posible» a una hora en que quede hueco hoy. Lo primero que ofrece es de hoy.
2. Toma la conversación desde la Bandeja, crea la reserva desde la agenda para ese cliente y devuélvela al agente. Escribe «gracias»: responde sin pasar a una persona.
