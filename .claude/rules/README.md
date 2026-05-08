# Rules

Repo-specific rules enforced at PR/save time.

Likely first rules:
- Tenant-id must come from request context, never from request body.
- All SQL repos must accept `tenant_id` from context only.
- New tools must register in `tool_catalog` migration in the same PR.
- Touching `agent-isolation.md` requires updating `tests/isolation/` in the same PR.
