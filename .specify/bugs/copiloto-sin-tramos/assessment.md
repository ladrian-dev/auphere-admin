# Bug Assessment: el copiloto no cobra el tramo de precio por llamada

- **Slug**: copiloto-sin-tramos
- **Created**: 2026-11-26
- **Source**: pasted text (hallazgo de la validación del 2026-11-26; nota de KB `research/2026-11-26-beta-jemma-p0-p1.md`)
- **Verdict**: valid
- **Severity**: high. Hoy no ocurre, porque el copiloto corre en Sol y Haiku 5.5 no está habilitado para responder. Ocurrirá en cuanto se habilite Haiku, que está decidido; hasta que se arregle, bloquea la operación de habilitar Anthropic en prod.

## Report

> El copiloto (companion de la consola) no aplica el tramo de precio por llamada (Haiku 5.5: ×5 por encima de 100.000 tokens de prompt). Cobra la cuota y valora el coste con los totales del turno, y el grafo solo emite totales en `cost.updated`. Un teammate puede usar `teammate.model`, que solo se valida contra la lista del partner, y esa lista incluye Haiku 5.5 desde la 0238.

## Symptom

Un turno del companion en un modelo con tramo, como Haiku 5.5, donde alguna llamada pasa del umbral de prompt bruto, se cobra a tarifa normal en la bolsa del partner y se valora a tarifa normal en `cost_usd`. Debería cobrarse cada llamada que pasa el umbral con su multiplicador, igual que el canal (spec 065, requisito 5.9; `LaneWeights.for_prompt` y `tier_factor`).

## Reproduction

1. Un partner tiene Haiku 5.5 en su lista. Desde la 0238 lo tienen todos.
2. Crear un teammate con `model = anthropic/claude-haiku-5-5`. `teammates._check_model` lo acepta.
3. Lanzar un turno largo del companion con ese teammate, en el que una pasada del bucle supere los 100.000 tokens de prompt.
4. La cuota debitada (`_turn_quota_units`) y el `cost_usd` del turno (`_turn_cost_usd`) salen sin el ×5.

## Suspected Code Paths

- `apps/api/src/nexus_api/api/console/companion.py`, `_turn_quota_units` (~1580): calcula con los totales y su docstring reconoce que no aplica el tramo.
- `apps/api/src/nexus_api/api/console/companion.py`, `_turn_cost_usd` (~1618): valora con las tarifas de la fila, sin `tier_factor`.
- `apps/worker/src/nexus_worker/runtime/companion/graph.py`: el consumo por llamada se conoce en el bucle (~324), en `_close_the_turn` (~370), en `_answer_after_action` (~943) y en `_answer_without_tools` (~992), pero solo se acumulan totales. `cost.updated` (~725) emite totales.
- `apps/api/src/nexus_api/api/companion_streaming.py:194`: las claves permitidas de `cost.updated`.
- `apps/api/src/nexus_api/api/console/teammates.py:218`, `_check_model`: solo comprueba la lista del partner.

## Root Cause Hypothesis

El tramo se decide por llamada (prompt bruto de esa llamada por encima del umbral), y el companion solo conserva la suma del turno. Aplicarlo sobre la suma cobraría ×5 a un turno de muchas llamadas cortas, así que se decidió no aplicarlo, suponiendo que el companion nunca correría en un modelo con tramo. Esa suposición dejó de ser cierta cuando los teammates pudieron elegir modelo de la lista del partner (0238). **Confianza: alta.**

## Proposed Remediation

**Preferida: cobrar por llamada, como el canal.**
- El grafo guarda en el estado, por cada llamada al modelo, `{prompt, uncached, cache_read, cache_write, output}` (`usage_calls`) en los cuatro sitios donde ya acumula, y lo emite en `cost.updated` (clave `calls`).
- La API, al recibirlo, calcula:
  - la cuota sumando `quota_tokens` de cada llamada con `lanes.for_prompt(prompt)`;
  - el coste sumando cada llamada con `tier_factor(row, prompt)`.
- Sin `calls` (un run de antes del cambio), sigue con los totales como hoy.

**Alternativas:**
- **Que un teammate no pueda elegir un modelo con tramo.** Es más pequeño, pero quita a los teammates el modelo más barato y contradice «se cobra todo», que es la decisión de la 065.
- **Aplicar el tramo al turno entero si la última llamada pasó el umbral.** Cobra de más las llamadas cortas del mismo turno. Descartada.

**Files likely to change:**
- `apps/worker/src/nexus_worker/runtime/companion/graph.py` y `state.py`
- `apps/api/src/nexus_api/api/companion_streaming.py`
- `apps/api/src/nexus_api/api/console/companion.py`
- `apps/api/tests/unit/test_companion_streaming.py` (o un fichero nuevo de pruebas del cobro por llamada)

**Tests to add:**
- Un turno con dos llamadas, una por debajo del umbral y otra por encima: la cuota es la suma por llamada, con ×5 solo en la segunda.
- Lo mismo para `cost_usd`.
- Sin `calls`, mismo resultado que hoy.
- El grafo emite una entrada en `calls` por llamada al modelo, la de cierre incluida.

## Hallazgo en el mismo camino: la caché se acumula entre turnos del hilo

Lo probé con el grafo de verdad: dos turnos en el mismo hilo, con el mismo `checkpointer`.

| Turno | `input_tokens` | `cache_read` | `cache_write` | `steps` |
|---|---|---|---|---|
| 2.º | 1.000 (bien) | **16.000** (8.000 + 8.000) | **1.000** | **2** |

La causa:
- La entrada de cada run (`console/companion.py`, alrededor de la línea 1268) solo pone a cero `total_input_tokens` y `total_output_tokens`.
- `total_cache_read`, `total_cache_write` y `total_steps` salen del checkpoint del hilo y se van sumando.
- La API suma lo que llega en `cost.updated` al `handle` del run.

Así, cada turno cobra la caché de todos los turnos anteriores del hilo. **Pasa hoy en prod** con el copiloto en Sol: se cobra de más la cuota de caché y sale inflado el `cost_usd` de los hilos largos.

**Severidad: high (dinero).** Se arregla en el mismo cambio: la entrada pone a cero también esos tres totales y `usage_calls`. Una reanudación (`Command(resume=…)`) no los toca, porque continúa el mismo turno.

## Risks & Considerations

- `cost.updated` llega al navegador: `calls` solo lleva recuentos de tokens, sin contenido. El catálogo de claves del SSE es cerrado, así que se añade ahí.
- Un turno puede tener hasta `MAX_MODEL_STEPS + 1` llamadas, así que la lista es corta.
- Hay otros consumidores de `cost.updated` (`qa.py`, `qa_streaming.py`, `console/playground.py`, `companion/tools/playground.py`) que leen solo totales. No se tocan: no cobran a un partner por cuota.

## Open Questions

Ninguna. La decisión de cobrar los tramos es de Luis (spec 065, 5.8 y 5.9).
