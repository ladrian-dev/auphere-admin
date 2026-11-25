# Bug Assessment: el aviso `cache_ratio_low` cuenta la caché dos veces

- **Slug**: cache-ratio-cuenta-la-cache-dos-veces
- **Created**: 2026-11-25
- **Source**: avisos `cache_ratio_low` de producción, investigados con Logs Insights (7 días de Jemma's Hair, 615 llamadas)
- **Verdict**: valid
- **Severity**: low. Solo afecta a un aviso por correo; el agente y el cobro no cambian.

## Report

En 30 días llegaron 15 correos «[Auphere] Prompt cache degradado», 14 de ellos desde el 18-11. En cada hora con aviso, todos los tokens contados eran de un mismo cliente.

## Symptom

El aviso salta con lecturas de caché reales de entre el 32 % y el 43 %, por encima del umbral de 0,30.

## Root cause

`platform_watcher.py` calculaba `cache_read / (input + cache_read)`. Pero `input` es `prompt_tokens`, que ya incluye los tokens leídos de caché: `llm._call_cost_micros` lo da por hecho, y en las 615 llamadas medidas se cumple. El denominador contaba la caché dos veces, así que el aviso saltaba en cuanto la lectura real bajaba del 42,9 %.

## Remediation

Calcular `cache_read / input`. El umbral (0,30) y el mínimo de volumen (100 000 tokens) se quedan, y el mínimo se mide ahora sobre `input`.

## Fuera

- El fallo de caché real, que sigue existiendo: la primera llamada GPT de cada turno no lee caché porque la hora `HH:MM` va como tercer mensaje de sistema, por encima de lo estable. Moverla cambia lo que recibe el modelo en todos los agentes, así que lleva su propia enmienda con evaluación.
- El aviso sigue siendo global, no por cliente.
