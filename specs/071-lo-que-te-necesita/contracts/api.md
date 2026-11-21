# Contrato: la lista «Lo que te necesita» (spec 071)

## Fila de la lista (`AttentionItem`)

Amplía la `PanelAttention` de la spec 047. Lo nuevo va marcado con ★.

```ts
type AttentionCode =
  // de un cliente (los de hoy, services/attention.py)
  | "no_balance" | "channel_problem" | "integration_reauth" | "agent_cap"
  | "agent_without_channel" | "low_balance" | "no_agents"
  // ★ del partner
  | "build_cap_exhausted" | "build_cap_warning"
  | "account_empty" | "account_low"
  | "billing_payment_failed";

type AttentionAction =
  | "assign_balance" | "request_balance" | "fix_channel" | "reconnect"
  | "raise_cap" | "connect_channel" | "new_agent"
  // ★
  | "request_build_extension"   // POST /console/usage/build-budget/extension-request (ya existe)
  | "buy_balance"               // enlace a Comprar saldo (/billing o el modal de Consumo)
  | "fix_billing";              // enlace a Facturación

type AttentionItem = {
  scope: "partner" | "client";               // ★
  severity: "critical" | "warning";          // ★ critical: *_exhausted, *_empty, no_balance, channel_problem, billing_payment_failed
  code: AttentionCode;
  external_client_ref: string | null;        // ★ null cuando scope = "partner"
  client_name: string | null;
  count: number;                             // como hoy (agentes, canales… afectados)
  action: AttentionAction;
  href: string;
  data: {                                    // ★ lo justo para el texto; todo opcional
    pct?: number;                            // build_cap_*: % gastado (entero)
    spent?: PanelMoney; cap?: PanelMoney;    // build_cap_*
    available?: PanelMoney;                  // account_*, low_balance, no_balance
    days_left?: number | null;               // account_low, low_balance
  };
};
```

Orden: de peor a mejor por gravedad. Dentro de cada gravedad, primero lo del partner, luego por `ATTENTION_REASONS` y por `external_client_ref`.

## `GET /console/attention` ★

- Permiso: `partner:read`. Las filas de cliente, además, solo con `clients:read`, como el Panel de hoy.
- Respuesta: `{ items: AttentionItem[], errors: string[] }`. `errors` dice qué parte no se pudo leer (`"partner"`, `"clients"`), como `panel.errors`.
- `/console/home` → `panel.attention` devuelve **la misma lista**, de la misma función. `panel.all_serving` = lista vacía y sin errores.

## Avisos guardados (`/console/notifications`)

- `NotificationOut` ya trae `handled`. La consola lo usa para «Resuelto».
- ★ `GET /console/notifications/unread-count` deja de contar los avisos de condición (tabla de spec.md §2.1): esos los cuenta «Ahora».
- ★ `POST /console/notifications/read-all` solo marca los informativos.
- ★ `NotificationOut.condition: boolean`: el aviso es de una condición (se resuelve solo; no se marca como leído a mano).
