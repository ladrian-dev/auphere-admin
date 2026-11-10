# Bug Assessment: un lote de medición se cobra según su primera fila

- **Slug**: un-lote-cobra-por-su-primera-fila
- **Created**: 2026-11-05
- **Source**: Encontrado el 2026-11-05 al preparar el cobro de pruebas a la bolsa (requisito 68).
- **Verdict**: valid
- **Severity**: high

## Symptom

El consumidor de medición junta en un lote las filas de cada cliente, y `_debit_channel_wallet` miraba el origen y el agente de la primera. Un turno de canal leído junto a una prueba se quedaba sin cobrar si la prueba iba primero. Si iba después, la prueba se cobraba a la bolsa como un turno, y todos los turnos del lote se apuntaban al agente de la primera fila.

## Reproduction

`apps/api/tests/integration/wallet/test_tests_on_the_bag.py`: un lote con `tests` y `channel`, en los dos órdenes, y uno con dos turnos de dos agentes.

## Root cause

`consumer.py` agrupa por cliente (`parsed.setdefault(tenant_id, []).extend(rows)`) y `_debit_channel_wallet` leía `rows[0]`. No se ha medido cuánto dinero movió: staging casi nunca mezcla, y producción mezcla si alguien usa el playground o las pruebas mientras el cliente conversa.
