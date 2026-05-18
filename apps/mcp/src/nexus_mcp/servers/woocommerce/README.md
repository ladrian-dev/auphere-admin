# WooCommerce MCP server

First Nexus connector using the **`api_key`** auth kind. Talks the WooCommerce
REST API v3 directly via Basic Auth over HTTPS (Consumer Key + Consumer
Secret) — no Composio, no headless browser.

- Catalog seed: `apps/api/.../services/connectors/seeds/woocommerce.yaml`
- DB tool rows: alembic migration `0024_seed_woocommerce_tools.py`
- Tools registered in `nexus_mcp.registry.build_default_registry()`

---

## Tool surface (12 total)

| Tool | Kind | What it does |
|---|---|---|
| `woocommerce.list_products` | read | List products. Filters: `search`, `category`, `type`, `status`, `stock_status`, `attribute` + `attribute_term`. |
| `woocommerce.get_product` | read | One product by `id` or `sku`. Returns attributes + variation ids. |
| `woocommerce.list_product_variations` | read | Variations of a variable product (size/colour combos). |
| `woocommerce.list_categories` | read | Product categories — useful to discover category slugs. |
| `woocommerce.list_orders` | read | Orders. Filters: `status`, `customer`, `after`/`before`, `search`. |
| `woocommerce.get_order` | read | One order with full line items + billing/shipping. |
| `woocommerce.list_customers` | read | Search customers by email / name. |
| `woocommerce.get_customer` | read | One customer by `id` or `email`. |
| `woocommerce.create_order` | **destructive** | Create an order. Line items accept `product_id` or `variation_id`. Default status `pending`. |
| `woocommerce.update_order_status` | **destructive** | Move an order to a new status. Reports previous status for audit. |
| `woocommerce.update_order` | **destructive** | Update restricted fields (addresses, customer note, payment method). |
| `woocommerce.add_order_note` | **destructive** | Add a note (internal or visible to customer). |

Destructive tools land in `tool_catalog` with `default_mode='blocked'`. The
operator promotes them per tenant via `tenant_connector_tool_overrides` once
the read-only surface has been validated against the real store.

---

## Connecting a tenant's WooCommerce store

### 1. Generate the API keys in WP-Admin

In the client's WordPress admin:

```
WooCommerce → Settings → Advanced → REST API → Add key
```

- **Description**: `Auphere agent` (or anything memorable for the operator)
- **User**: a user that owns the store (typically the shop admin)
- **Permissions**: `Read/Write` (required for `create_order` / `update_*` tools)
- Click **Generate API key**.

WordPress shows the Consumer Key (`ck_...`) and Consumer Secret (`cs_...`)
**once**. Copy both before leaving the page.

### 2. Wire it into Auphere

`POST /admin/tenants/{tenant_id}/connectors/woocommerce/connect-api-key`
with admin Bearer token:

```json
{
  "secrets": {
    "consumer_key": "ck_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "consumer_secret": "cs_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  },
  "endpoint_meta": {
    "store_url": "https://shop.example.com"
  }
}
```

The endpoint:
- Fernet-encrypts the `secrets` payload into `tenant_credentials`.
- Stores routing info in `tenant_connectors.credentials_ref.endpoint_meta`.
- Sets `tenant_connectors.status = 'connected'`.
- Writes an `audit_log` row `connector.connect_completed`.

`store_url` **must** be HTTPS — the client refuses `http://` because Basic
Auth over plaintext would leak the Consumer Secret on the wire.

### 3. Enable destructive tools (only when the operator is ready)

Read-only tools are usable immediately. Destructive tools start blocked.
To enable e.g. `create_order` for a single tenant:

```
PUT /admin/tenants/{id}/connector-tool-overrides/woocommerce.create_order
{ "mode": "always", "reason": "post-soak: agent verified on read-only for 1 week" }
```

---

## Troubleshooting

### `401 Unauthorized` on every call
1. Re-check that the Consumer Key permission is `Read/Write` (Read-only blocks
   destructive tools but should NOT block reads — if reads also fail, the key
   is wrong).
2. WooCommerce signs Basic Auth requests against the server timezone. If
   the WP server clock is far off (>5 minutes), Basic Auth still works
   (no nonce), but **some security plugins** reject. Check `php date` on
   the server matches reality.
3. Hosting providers that wrap WP with a WAF (Sucuri, Cloudflare Bot
   Management) sometimes strip the `Authorization` header. Confirm the
   header reaches WP by tailing access logs.

### `403 Forbidden`
- A security plugin (Wordfence, iThemes) is blocking the API path. Whitelist
  `/wp-json/wc/v3/*` for our outbound IP, or temporarily disable to confirm.

### `429 Too Many Requests`
- Default WooCommerce installs don't rate-limit, but hosting providers
  often do. The client retries `429` once respecting `Retry-After`; past
  that it raises `WooCommerceRateLimited` and the operator panel shows
  the cause.

### Long product descriptions get truncated
Descriptions are stripped of HTML and truncated to 500 chars in `get_product`
output. That's intentional — the agent doesn't need the full marketing copy
and we keep the LLM context small. Use the WP-Admin link in the UI for
operator review.

---

## Code layout

```
apps/mcp/src/nexus_mcp/
  http/
    __init__.py
    base_client.py     # reusable HTTP scaffolding (M1 — used by future api_key connectors)
  servers/woocommerce/
    __init__.py
    README.md          # this file
    client.py          # WooCommerceClient — subclass of BaseHTTPConnectorClient
    errors.py          # WooCommerce*Error subclasses
    schemas.py         # Pydantic Input/Output models for every tool
    tools.py           # 12 ToolBase classes + WOOCOMMERCE_TOOLS tuple
```

Tests:
- Tools: `apps/mcp/tests/test_woocommerce_tools_unit.py` (FakeWooClient).
- Seed: `apps/api/tests/unit/connectors/test_woocommerce_seed.py`.
