# Isolation test suite

Verifies the 7 isolation guarantees defined in `architecture/agent-isolation.md`. This suite is **blocking** in CI: a red test prevents merge to `main`.

Block B introduces the first real tests here. Block A leaves the directory wired up so CI configuration can target it from day one.

Planned tests (one per guarantee):

1. `test_rls_blocks_cross_tenant_select.py` — RLS prevents reading another tenant's rows.
2. `test_tool_whitelist_blocks_unlisted_invocation.py` — runtime rejects tools not in `agent_config.tools`.
3. `test_kg_query_is_tenant_scoped.py` — KG queries always carry `tenant_id`.
4. `test_checkpointer_threads_dont_collide.py` — same `user_id` across tenants does not share thread state.
5. `test_prompt_render_is_isolated.py` — rendered prompts contain only the tenant's own data.
6. `test_logs_carry_tenant_id.py` — every log emitted from a request has `tenant_id`.
7. `test_llm_calls_are_per_tenant.py` — no cross-tenant batching at the LiteLLM layer.
