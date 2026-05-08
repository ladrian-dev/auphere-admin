# .claude/

Per-project Claude Code configuration. Populated incrementally as Phase 1 advances.

- `agents/` — specialized subagent definitions (e.g. db-migrator, mcp-author, isolation-reviewer).
- `skills/` — domain skills the model can invoke (e.g. seed-tenant, run-isolation-suite).
- `rules/` — repo-specific rules enforced via the `Rule` matcher.

Until block B introduces real workflows, these directories hold stubs. Adapt definitions from existing Auphere/Ladrian projects (Astroluv, Restaurant AI) as reusable patterns emerge.
