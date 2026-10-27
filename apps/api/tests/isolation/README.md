# Isolation test suite

Verifies the 7 isolation guarantees defined in `architecture/agent-isolation.md`. **Blocking** in CI: a red test prevents merge to `main`.

Block B introduces the foundation tests; block C will replace the contract-only tests for guarantees 2/4/7 with runtime tests once LangGraph + LiteLLM are wired.

## Tests in this directory

| File | Garantía | Type |
|---|---|---|
| `test_1_rls_blocks_cross_tenant_select.py` | 1 — Postgres RLS | Live, against Postgres |
| `test_2_tool_whitelist_contract.py` | 2 — Tool whitelist | Data contract (runtime in block C) |
| `test_3_kg_query_is_tenant_scoped.py` | 3 — KG scoping | Live, against Postgres |
| `test_4_checkpointer_thread_format.py` | 4 — Checkpointer scoping | Format contract (runtime in block C) |
| `test_5_prompt_render_is_isolated.py` | 5 — Prompt rendering | Live, via service |
| `test_6_logs_carry_tenant_id.py` | 6 — Log tagging | Captures structlog output |
| `test_7_llm_calls_per_tenant.py` | 7 — LLM stateless | Config contract (runtime in block C) |
| `test_8_audit_log_scoped.py` | extra — `audit_log` RLS | Live |
| `test_9_channel_credentials_scoped.py` | extra — `tenant_credentials` RLS + Fernet | Live |
| `test_10_repos_reject_explicit_tenant.py` | extra — repo contract introspection | Static |
| `test_15_tiktok_channel_isolation.py` | extra — TikTok channel resolution + OAuth state | Live |

10 tests minimum; running this directory by itself blocks merge if any fail.

## Running

```bash
cd apps/api
uv run pytest tests/isolation/ -x
```

## When block C lands

The "contract" tests for guarantees 2, 4, 7 get replaced by runtime tests:

- **2**: spin up the agent runtime with whitelist `[booking]`, intercept the LiteLLM call, verify only `booking.*` tool definitions appear in the prompt.
- **4**: drive two messages through the runtime with the same `user_id` but different `tenant_id`s; verify their checkpoints are stored under different keys and don't share state.
- **7**: spawn two concurrent runtime calls with different tenants; verify two distinct HTTP requests are made to the LLM provider.

The data/contract layer in this block remains: the runtime tests build on top.

## Spec 047 — los barridos de la fábrica de agentes

Fase 2 de `specs/047-la-fabrica-de-agentes/tasks.md` (T012–T021, requisito 56).
Cada archivo **barre, no enumera** (constitución §I): recorre el catálogo —de
Postgres, del registro MCP, de las rutas montadas, del código— y se pone en rojo
cuando aparece algo nuevo sin su caso o su razón escrita. Se escribieron en verde
con lo que existe hoy; cada bloque de la 047 añade sus casos. Todos llevan su
control del control: el mismo comprobador, contra una violación plantada, en rojo.

| Archivo | Garantía | Qué barre |
|---|---|---|
| `test_43_force_and_composite_fk_sweep.py` | 1 | `pg_class`/`pg_policy`/`pg_constraint` en todos los esquemas: toda tabla con `tenant_id` tiene RLS ENABLE + FORCE, la política de cliente canónica con `USING` y `WITH CHECK` explícitos, ninguna otra política permisiva, y toda FK entre tablas de cliente es compuesta `(tenant_id, x)`. Lo de antes que no cumple está en un inventario cerrado (77 entradas, con techo y sin entradas podridas) que ninguna tabla creada por una migración ≥ 0175 puede usar |
| `test_44_agent_within_client.py` | 9 | Toda tabla con `agent_id` o FK a `agents`, y toda herramienta del registro MCP: cada una con su caso adversarial o su razón. Casos de hoy: el cargador y el prompt compilado de un agente no llevan nada de su hermano; cada número resuelve su agente y su configuración; las herramientas que leen un agente (`payments.request_review`, `notification.schedule_reminder`, `reservas.create`/`answer_offer`) leen el del número de la conversación. Ninguna herramienta deja al modelo elegir agente |
| `test_45_tools_only_from_activations.py` | 2 y 9 | Cada herramienta del registro, fuera de la lista, ni llega al modelo ni se ejecuta; el registro repartido entre dos hermanos, en cada intención; las herramientas dinámicas de Composio solo de conexiones vivas del cliente, filtradas por la lista del agente y con su credencial; y cada campo del `AgentBundle` clasificado como fuente de herramientas (con caso) o no. Las activaciones por agente del bloque F entran por ese último barrido |
| `test_46_business_profile_not_in_kg.py` | 3 | Todo el código de producto con `ast`: quién escribe en `kg_nodes`/`kg_edges` (hoy nadie, y nunca un módulo de la ficha) y quién lee el grafo, cada lector con su caso por cliente (la instantánea del turno, `commission.*`) |
| `test_47_router_state_in_checkpoint.py` | 4 | Todas las claves de `AgentState`, escritas con el `TenantScopedPostgresSaver` real: vuelven enteras a su hilo y ni el hilo del vecino (mismo canal y número), ni su GUC, ni una sesión sin GUC las ven. Más un turno real con el saver real. `pinned_model` y el estado por agente entran solos cuando estén en `AgentState` |
| `test_48_compilation_is_deterministic.py` | 5 | Todas las plantillas de sector del disco: mismas entradas, mismos bytes, aunque entre medias se compile otro cliente, y nada de un cliente en el otro; el bloque de conocimiento, igual y solo del cliente; y el modo «instrucciones»: el prompt guardado llega al modelo byte a byte |
| `test_49_new_events_carry_tenant_and_agent.py` | 6 | Lee el catálogo de `contracts/events.md` §5 y barre el código con `ast`: cada emisión lleva `tenant_id` explícito, los siete eventos de la 047 también `agent_id`, ningún campo de texto, teléfono o fuera del contrato, y ningún uso del nombre que el barrido no pueda leer. Hoy no hay emisiones; cada evento entra el día que se escriba |
| `test_50_provider_retention_and_tenant_batches.py` | 7 | Cada ruta de proveedor del catálogo de plataforma con su regla de retención, comprobada sobre lo que sale del transporte; todo sitio que llama a un proveedor, declarado y sin `store=True`; ninguna API de lotes de proveedor; y cada sitio que arma un lote de evaluación, con su caso de un solo cliente |
| `test_51_new_tools_take_no_end_customer.py` | 8 | El registro MCP entero, argumento a argumento: ninguno nombra a un cliente final salvo el inventario cerrado (28 entradas, con techo), con sus casos: el runtime sobrescribe `conversation_id`, `reservas.*` descarta una conversación ajena y las herramientas de operador solo están en semillas `admin_only` |
| `test_52_partner_never_sees_bodies.py` | C8, C1, C9 | Todas las respuestas del partner: ningún campo de coste ni de teléfono salvo los inventariados; ninguna lectura devuelve el coste de modelo sembrado; y cada superficie (Panel hoy; Rendimiento, sugerencias y correcciones cuando se monten) responde con datos de verdad |

Además, en archivos que ya existían:

- `test_console_scope.py` §7: todas las lecturas del partner de `/console/*` —las
  nuevas de la 047 incluidas, el día que se montan— sobre `_partner_world`, una
  base con cuerpos de mensaje, transcripciones, llamadas a herramientas, notas y
  nombres y teléfonos de clientes finales; ninguna respuesta los lleva. `_fill`
  rellena los parámetros con objetos reales de ese cliente y, los que no conoce,
  con un UUID.
- `test_lite_route_scope.py` y `test_phone_route_scope.py`: una ruta de
  `/console/lite/*` montada en el test entra sola en los dos barridos, y una
  escritura con id nueva los pone en rojo hasta tener su caso; `/app/*` lo cubre
  la lista cerrada de `test_app_public_routes.py`.

Ayudantes que no son tests: `_tenant_catalog.py` (la lectura del catálogo de
Postgres que comparten `test_43` y `test_44`) y `_partner_world.py` (el mundo con
lo que el partner nunca debe ver).

**La garantía 9** («el agente dentro del cliente») la escribe la enmienda 1.3.0
de la constitución, que espera a la spec 046. Hasta que entre, `test_44` y
`test_45` la prueban como requisito de la spec 047 (56.2, 56.3 y 37.x), no como
garantía vigente de `architecture/agent-isolation.md`.
