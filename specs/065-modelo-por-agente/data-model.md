# Modelo de datos: El modelo de cada agente

**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

Cuatro migraciones sobre `0236_context_cut_and_autoclose`. Al desplegar, todos los agentes responden con el mismo modelo que el día anterior (CE-005): los que tenían el modelo de su cliente pasan a tenerlo elegido (§7), y el modelo por defecto de Auphere arranca en Sol (§8).

## 1. La elección de un agente (`agents`, columnas nuevas)

Migración `0237_agent_respond_model`.

| Columna | Tipo | Nulo | Qué es |
|---|---|---|---|
| `respond_model_profile_id` | `uuid` → `model_profiles(id)` `ON DELETE RESTRICT` | sí | El modelo elegido para responder. Nulo = sigue el modelo por defecto de Auphere. |
| `respond_model_set_by` | `text` con `CHECK IN ('partner','operator')` | sí | Quién lo eligió. Nulo si no hay elección. |
| `respond_model_set_at` | `timestamptz` | sí | Cuándo. |

- `CHECK ((respond_model_profile_id IS NULL) = (respond_model_set_by IS NULL))`: una elección siempre dice quién la hizo.
- La RLS de `agents` (FORCE, `agents_tenant_isolation`, migración 0152) cubre las columnas nuevas: no hace falta política nueva. La FK apunta a `model_profiles`, una tabla de plataforma sin cliente; no cruza dos tablas de tenant, así que no necesita FK compuesta.
- `ON DELETE RESTRICT`: un perfil de modelo elegido por un agente no se puede borrar. Retirarlo pasa por las guardas de la spec 059.
- Quién y por qué queda en `audit_log` (§4), no en la fila.

**Por qué en `agents` y no en una tabla aparte**: la elección es una por agente, vive y muere con él y ya tiene RLS forzada. Una tabla nueva sería otra superficie de aislamiento con su política, su FK compuesta `(tenant_id, agent_id)` y su test, para guardar tres columnas.

**Por qué no en la versión (`agent_configs.policies`)**: la spec la quiere viva (requisito 2.3). En la versión obligaría a publicar.

## 2. La oferta: perfiles y lista por partner

Migración `0238_respond_offer_claude_55`.

### `model_profiles` (plataforma, sin RLS)

- Columnas nuevas, la puerta por entorno (research.md §D11):

  | Columna | Tipo | Nulo | Qué es |
  |---|---|---|---|
  | `respond_enabled_at` | `timestamptz` | sí | Desde cuándo se puede elegir para responder en este entorno. Nulo = no habilitado. |
  | `respond_enabled_by` | `text` | sí | La persona de Auphere que lo habilitó (`operator_actor`). |
  | `respond_enabled_note` | `text` | sí | La pasada de la batería real en la que se apoya (fecha, commit, resultado). |

  `CHECK ((respond_enabled_at IS NULL) = (respond_enabled_by IS NULL))`. La migración marca habilitados Sol, Terra y Luna (nota: «ofrecidos antes de la spec 065»); los tres de Anthropic quedan sin habilitar.
- Filas nuevas `anthropic/claude-opus-5-5` («Claude Opus 5.5») y `anthropic/claude-sonnet-5-5` («Claude Sonnet 5.5»), copiadas de la fila de `anthropic/claude-haiku-5-5` (proveedor, `route`, `family`, `residency`, contrato, `capabilities`, `quota`), con tarifas y pesos de research.md §D1, `max_context` 1.000.000 y `status = 'active'`.
- Precios en `model_prices` con `valid_from = CURRENT_DATE` y `source_url` de la página de precios de Anthropic.
- `offer_label` para las tres de Anthropic: «Opus 5.5», «Sonnet 5.5», «Haiku 5.5». Dos vistas: **ofrecible** (`offer_label` ∩ `status = 'active'` ∩ con perfil), contra la que se valida la lista de un partner, y **ofrecido** (ofrecible ∩ `respond_enabled_at IS NOT NULL`), lo que se puede elegir. Los de Anthropic no se ofrecen hasta que Auphere los habilite.

### `partner_model_allowlist` (RLS por `app.partner_id`)

- Inserta los tres de Anthropic para cada partner existente (`ON CONFLICT DO NOTHING`).
- Redefine `partner_model_allowlist_on_partner()` para que un partner nuevo nazca con los seis.

Ningún partner pierde nada; Auphere restringe después desde la ficha del partner, como hoy.

## 3. El perfil de llamada de cada modelo (código, no base)

Un registro en `apps/api/src/nexus_api/core/respond_profiles.py` (lo leen la API y el worker; el worker depende de `nexus-api`), una entrada por modelo que puede responder:

| Campo | Qué fija |
|---|---|
| `model_id` | El id del catálogo. |
| `family` | `openai` o `anthropic`: decide qué se conserva y qué se quita al saltar. |
| `request` | Los kwargs que necesita con herramientas (research.md §D3–D4). |
| `forbidden` | Lo que nunca se le manda (temperatura, `tool_choice` forzado, `budget_tokens`…). |
| `keeps_reasoning` | Si sus bloques de razonamiento vuelven en la siguiente llamada del turno. |
| `timeout_s` | El plazo de cada llamada. |
| `max_tokens` | El techo de salida, con el razonamiento dentro. |
| `reserve` | La reserva de la otra familia (research.md §D5): GPT-5.6 → `anthropic/claude-sonnet-5-5`; Claude 5.5 → `openai/gpt-5.6-terra`. |
| `cross_in_request` | Lo que se manda cuando el modelo entra como reserva tras herramientas de otra familia (Sonnet 5.5: `thinking: {"type": "between_tools"}`). |
| `block_binding` | Para los que razonan: `prefix_mismatch_behavior = "drop_block"` y su beta. Nunca junto a `between_tools`. |
| `estimate_factor` | Lo que gasta frente a Sol con los mismos tokens (razonamiento, tokenizador), medido por la batería real; 1,0 hasta medirlo. |
| `supports` | Lo que sabe ejecutar además de herramientas: Skills de Anthropic, conector MCP de Anthropic. |

**Reglas** (research.md §D12):
- El registro es la única fuente de cómo se llama a un modelo.
- Un modelo sin perfil no se ofrece, no se habilita y no es reserva.
- Un modelo sin perfil que ya responde hoy por una asignación de cliente sigue como hoy.

## 4. Auditoría

`audit_log` (por cliente, como hoy), dos acciones nuevas:

| Acción | Quién | `target` | `before_json` / `after_json` |
|---|---|---|---|
| `console.agent.model.update` | persona del partner | `agent:<agent_id>` | `{model_id}` antes y después; `null` = modelo por defecto |
| `admin.agent.model.update` | persona de Auphere | `agent:<agent_id>` | ídem, con `set_by` |

Y una notificación de consola nueva, `agent.model_reset`, cuando una lista más corta pasa un agente al modelo por defecto (requisito 8.2): `{external_client_ref, agent_name, from_model, to_model}`. Sin ids internos de cliente, como `client.model_reset`.

## 5. Resolución (función única)

`apps/api/src/nexus_api/core/respond_model.py`:

```text
resolve(agent_choice, version_override, platform_default, *, agent_needs) → (model_id, source)
source ∈ {agent, agent_operator, version, platform}
```

`platform_default` es `platform_settings.agent_respond_default` (§8), no `llm_respond_model`.

La usan el turno (worker), las guardas de la 059 (`model_lifecycle.fixed_deployment`, `model_usage`), la consola (modelo efectivo y origen) y el panel. Un barrido en `tests/unit` falla si alguno de esos sitios resuelve el modelo de respuesta por su cuenta (Principio I: «barre, y deja que el código diga dónde más vive»).

## 6. Lo que viaja en el turno

- `AgentBundle` gana `respond_model: str | None` (la elección del agente), leído en `bundle_of` con la sesión ya acotada al cliente. `model_bindings` deja de traer el rol `respond`.
- `LLMResponse` gana `model` (el que respondió), `fell_back` (si no fue el primero de la cadena), `finish_reason` y `reasoning_blocks` (los bloques que vuelven al mismo modelo).
- `TurnModelPin`, por turno: el modelo que sirve el resto del turno una vez que entra la reserva, y si el turno sigue con el razonamiento apagado por un cruce (research.md §D5.4).
- El estado del turno: `response_model` pasa a ser el modelo que respondió de verdad; nuevo `response_fell_back: bool`.

## 7. Eventos nuevos (sin texto)

| Evento | Cuándo | Campos |
|---|---|---|
| `llm.respond_fell_back` | Una llamada de conversación la respondió la reserva | `tenant_id`, `agent_id`, `chosen`, `served`, `reason` (`error`, `timeout`, `refusal`, `rate_limit`) |
| `metering.price_tier_exceeded` | Una llamada de Haiku 5.5 pasó de 100.000 tokens de prompt | `tenant_id`, `agent_id`, `model`, `prompt_tokens` |

## 8. Pesos de la escritura en caché y modelo por defecto de Auphere

Migración `0239_cache_write_lane_default`.

- `model_profiles.quota_weight_cache_write numeric NULL`: peso = `price_cache_write_per_mtok` × multiplicador ÷ 10, relleno para las filas con tarifa de escritura (todas las de Anthropic) y `0` para las que no la tienen. GPT-5.6 cobra la escritura a 1,25× la entrada según OpenAI y se repercute (Luis, 2026-11-19; research.md §D14): la migración pone su tarifa en `model_profiles.price_cache_write_per_mtok` (Sol 5,00, Terra 2,50, Luna 0,25), una fila nueva de `model_prices` por modelo con esa `cache_write` **y copiando las demás tarifas en vigor** (el precio vigente es la fila de `valid_from` más reciente: una fila solo con `cache_write` dejaría la entrada y la salida en blanco), vigente desde el día del despliegue y con `source_url` la guía de prompt caching de OpenAI, y su peso (Sol 1,10, Terra 0,55, Luna 0,055). Entra en `pricing_policy.LANES` como cuarto carril (research.md §D14).
- `platform_settings` es una tabla de clave y valor (`key`, `value jsonb`, `updated_by`; migración 0231). Fila nueva `('agent_respond_default', '"openai/gpt-5.6-sol"', 'migration:0239')`: el modelo con el que respondían los agentes sin elección. La API valida que sea un modelo habilitado al cambiarlo (research.md §D16). Quién y por qué queda en la auditoría (`admin.platform.agent_respond_default`).

## 9. La asignación de cada cliente pasa a sus agentes

Migración `0240_respond_bindings_to_agents` (datos, no falla por lo que encuentre; research.md §D15):

- dentro de un bloque con `SET LOCAL row_security = off` (patrón de la 0229: con la RLS forzada de `agents` falla en vez de escribir 0 filas en silencio), por cada fila de `tenant_model_bindings` con `role = 'respond'`, a cada agente del cliente con `status = 'active'` y sin elección propia: `respond_model_profile_id` = el de la fila; `respond_model_set_by` = `'partner'` si la última entrada de auditoría del cliente sobre el modelo es `console.model.update` y su modelo coincide con el de la fila, si no `'operator'`; `respond_model_set_at = now()`;
- `RAISE NOTICE` con cuántas asignaciones encontró y cuántos agentes escribió, para compararlo con la comprobación previa;
- una línea de `audit_log` por cliente, `model.respond_binding.migrated`, con la fila de antes (modelo, `fallback_chain`, `max_cost_per_turn_usd`) y los agentes que la recibieron;
- **no borra** las filas; las borra la migración de la versión siguiente;
- `downgrade`: vuelve a dejar las elecciones migradas en `NULL`, leyendo la auditoría.
