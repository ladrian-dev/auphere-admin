# agendapro-public-mcp

MCP server that books AgendaPro appointments via the tenant's **public
booking link** (`<branch>.site.agendapro.com/cl/sucursal/<id>`). No
admin login, no 2FA, no persisted browser context — per ADR-017.

Spoken via stdio JSON-RPC 2.0 by the Python booking facade and the
async booking cron (`apps/worker/src/nexus_worker/streams/async_booking_cron.py`).

## Tools exposed

| Method | Purpose |
|---|---|
| `agendapro_public.check_availability` | Read free slots from the public wizard for a given date + service. |
| `agendapro_public.create_appointment` | Walk the 3-step wizard end-to-end and return the confirmation code. |
| `agendapro_public._ping` | Liveness probe used by the Python transport. |

See `apps/mcp/servers/agendapro_public_mcp/src/flows/*.ts` for input/
output shapes. The Python side mirrors them via Pydantic models in
`nexus_mcp/servers/agendapro_public/schemas.py`.

## Run locally

```bash
# Build
pnpm install
pnpm build

# Smoke test (needs Browserbase keys)
BROWSERBASE_API_KEY=...  \
BROWSERBASE_PROJECT_ID=...  \
echo '{"jsonrpc":"2.0","id":1,"method":"agendapro_public._ping"}' | node dist/server.js
```

## Anti-bot posture

- Fresh Browserbase Stealth session per call. No Context reuse.
- Gemini 2.0 Flash for `act()`; Sonnet 4.6 only if a flow falls back
  to deep observation.
- Screenshot on every wizard step, dumped to the result envelope; the
  Python side persists them to S3 for operator post-mortems.
- If reCAPTCHA score drops below 0.5 → the call returns `status="failed"`
  with `failure_reason="recaptcha_low_score"` and the cron escalates
  to the owner.

## What this MCP does **not** do

- Modify or cancel appointments — those escalate to the owner via
  ADR-018.
- List a customer's appointments — escalates too. The public link is
  one-way (create-only) by design.
- Persist any state across calls (no session pool, no Context).

## Testing without Browserbase

`apps/api/tests/integration/agendapro_public/` runs against a local
HTTP server that mimics the agendapro.com wizard's DOM. The Python
fake transport (`FakeAgendaProPublicTransport`) skips this Node binary
entirely and is what unit tests use.
