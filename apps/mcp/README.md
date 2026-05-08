# nexus-mcp

MCP server implementations for the Nexus tool catalogue. One Python subpackage per server under `src/nexus_mcp/servers/`.

## Servers (Block D)

| Server | Tools | Backed by |
|---|---|---|
| `escalate` | `escalate.escalate_to_human` | `audit_log` row + flips conversation to `escalated` |
| `client` | `client.get_preferences`, `update_preferences`, `get_history` | `customers.preferences` JSONB + `appointments` |
| `booking` | `booking.{check_availability,create_appointment,modify_appointment,cancel_appointment,get_appointments}` | `appointments` table (relational; will become a shadow of AgendaPro when Block E lands) |
| `queue` | `queue.{join_queue,get_position,get_estimated_wait,check_in,remove_from_queue}` | Redis hot list `nexus:queue:{tenant}` + `queue_entries` history |
| `commission` | `commission.{calculate_commission,get_barber_earnings,get_daily_report}` | `appointments` + barber/service `kg_nodes` |
| `notification` | `notification.{send_template,send_text,schedule_reminder,cancel_scheduled}` | `messages.status='pending'` + `scheduled_jobs` |

## Layout decision

Block D ships these as **in-process Python modules**, not subprocess MCP servers. The `dispatch` interface in `nexus_mcp.registry` mirrors the MCP shape (`call_tool(name, args) -> result`) so a future server can move out-of-process without breaking the worker's contract. See [`architecture/mcp-registry.md`](../../../Work/Auphere/nexus/architecture/mcp-registry.md) for the full justification.

Block E ships AgendaPro browser MCP as a real subprocess (Stagehand + Browserbase, Node.js). The `booking-server` here is the **facade** that the LLM sees; when Block E lands, `booking.create_appointment` will internally delegate to `agendapro.create_appointment` for tenants on AgendaPro and continue using the local `appointments` table as a shadow cache.

## Tenant isolation

- `tenant_id` is **always** read from `nexus_api.core.tenant_context.require_current_tenant()`. Tools never accept it as an argument from the LLM.
- Every DB transaction is opened inside `tenant_scoped_session()` so RLS policies apply.
- Redis keys prefix with `nexus:<purpose>:tenant:{tenant_id}:` to prevent cross-tenant cache poisoning.
- The `MCPRegistry.dispatch` rechecks the whitelist before invoking the tool — defense in depth on top of pre-LLM filtering.
