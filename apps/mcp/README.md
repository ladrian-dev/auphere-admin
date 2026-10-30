# nexus-mcp

MCP server implementations for the Nexus tool catalogue. One Python subpackage per server under `src/nexus_mcp/servers/`.

## Servers (Block D)

| Server | Tools | Backed by |
|---|---|---|
| `escalate` | `escalate.escalate_to_human` | `audit_log` row + flips conversation to `escalated` |
| `client` | `client.get_preferences`, `update_preferences`, `get_history` | `customers.preferences` JSONB + `reservations` + the `appointments` not passed to Reservas |
| `reservas` | `reservas.{services,find_slots,create,list_mine,reschedule,cancel,confirm_attendance,join_waitlist,answer_offer}` | `reservations` — **the** agenda of the agents (spec 043), the one the business sees |
| `booking` | `booking.{check_availability,create_appointment,modify_appointment,cancel_appointment,get_appointments}` | `appointments` table. **Retired** (spec 048): no new agent gets it; it runs only for the versions that still name it, until the final removal |
| `queue` | `queue.{join_queue,get_position,get_estimated_wait,check_in,remove_from_queue}` | Redis hot list `nexus:queue:{tenant}` + `queue_entries` history |
| `commission` | `commission.{calculate_commission,get_barber_earnings,get_daily_report}` | `reservations` + the `appointments` not passed + barber `kg_nodes` (matched to the Reservas staff by name) |
| `notification` | `notification.{send_template,send_text,schedule_reminder,cancel_scheduled}` | `messages.status='pending'` + `scheduled_jobs` |

## Layout decision

Block D ships these as **in-process Python modules**, not subprocess MCP servers. The `dispatch` interface in `nexus_mcp.registry` mirrors the MCP shape (`call_tool(name, args) -> result`) so a future server can move out-of-process without breaking the worker's contract. See [`architecture/mcp-registry.md`](../../../Work/Auphere/nexus/architecture/mcp-registry.md) for the full justification.

Every server is in-process. The only out-of-process one (a Node browser MCP for a third-party booking page, with its stdio transport) was removed in spec 048 together with its internal tools; `dispatch_internal` stays as the mechanism, with nothing registered behind it.

## Tenant isolation

- `tenant_id` is **always** read from `nexus_api.core.tenant_context.require_current_tenant()`. Tools never accept it as an argument from the LLM.
- Every DB transaction is opened inside `tenant_scoped_session()` so RLS policies apply.
- Redis keys prefix with `nexus:<purpose>:tenant:{tenant_id}:` to prevent cross-tenant cache poisoning.
- The `MCPRegistry.dispatch` rechecks the whitelist before invoking the tool — defense in depth on top of pre-LLM filtering.
