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
