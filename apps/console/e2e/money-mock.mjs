/**
 * La API simulada del dinero — spec 047 (T153, T159, T160), solo para
 * `money.config.ts`.
 *
 * Contesta con la forma de `contracts/console-api.md` §7 lo justo para:
 * Consumo por partidas (las tres cifras, la tabla por cliente, la gráfica, las
 * partidas, la construcción y el detalle), las bolsas y el cambio del BCE,
 * asignar (con su recibo, «Faltan» y la clave de idempotencia), bajar, mover,
 * el relleno, «Pedir saldo» (una vez al día), el tope del agente, «Pedir
 * ampliación» y «Repartir tu saldo en bolsas». Y, para abrir el modal desde
 * otros sitios, la lista de clientes y el Panel de un cliente.
 *
 * La cuenta va en euros; Flor y Encanto tiene la bolsa en dólares y Barbería
 * Cultor, en euros y vacía. Guarda el estado en memoria.
 *
 * `POST /__test/reset` vuelve al principio, `POST /__test/role` cambia el rol de
 * quien entra, `POST /__test/migration` deja un reparto por confirmar y
 * `GET /__test/state` enseña lo que llegó. No verifica tokens: no es la puerta,
 * es el otro lado del cable.
 */
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_API_PORT ?? 8718);
const MODULES = ["panel", "clients", "usage", "audit", "knowledge", "team", "billing", "keys"];
const NOW = "2026-10-27T10:00:00Z";
const RATE = 1.0852; // 1 € = 1,0852 USD
const FX_DATE = "2026-10-26";
const FLOR = "flor-y-encanto";
const BARBERIA = "barberia-cultor";
const AGENT = "00000000-0000-4000-8000-0000000000a1";

const M = (units, currency) => ({ amount_micros: Math.round(units * 100_000), currency });

function principal(role) {
  return {
    user_id: "00000000-0000-4000-8000-0000000000e2",
    email: "luis@ladrian.studio",
    display_name: "Luis Matos",
    locale: "es",
    access: "ok",
    membership_id: "00000000-0000-4000-8000-0000000000e3",
    partner_id: "00000000-0000-4000-8000-0000000000e4",
    partner_slug: "ladrian-studio",
    partner_name: "Ladrian Studio",
    partner_status: "active",
    role,
    permissions: [],
    console_enabled: true,
    kind: "partner",
    client_name: null,
    modules: MODULES,
  };
}

function fresh() {
  return {
    role: "owner",
    account: { currency: "EUR", available: 60 * 100_000 },
    bags: {
      [FLOR]: { name: "Flor y Encanto", currency: "USD", balance: 1_550_000, spent: 400_000, refill: null, alert_low: true, days: 9 },
      [BARBERIA]: { name: "Barbería Cultor", currency: "EUR", balance: 0, spent: 0, refill: null, alert_low: true, days: null },
    },
    migration: { confirmed_at: null, clients: [] },
    assigns: [],
    lowers: [],
    moves: [],
    refills: [],
    caps: [],
    requests: [],
    requested: {},
    extensions: 0,
    confirmed: 0,
  };
}
let state = fresh();

const usageWrite = () => state.role === "owner" || state.role === "admin";

/** De la cuenta (EUR) a la bolsa: cuántas unidades de `to` vale una de `from`. */
function rate(from, to) {
  if (from === to) return 1;
  return from === "EUR" ? RATE : 1 / RATE;
}

function bagOut(ref) {
  const b = state.bags[ref];
  return {
    ref,
    balance: { amount_micros: b.balance, currency: b.currency },
    month_spent: { amount_micros: b.spent, currency: b.currency },
    month_base: { amount_micros: b.balance + b.spent, currency: b.currency },
    days_left: b.balance > 0 ? b.days : null,
    state: b.balance <= 0 ? "empty" : "ok",
    refill_up_to: b.refill ? { amount_micros: b.refill, currency: b.currency } : null,
    alert_low: b.alert_low,
    requested_at: state.requested[ref] ?? null,
  };
}

function summary() {
  const inBags = Object.values(state.bags).reduce((sum, b) => sum + Math.round(b.balance * rate(b.currency, "EUR")), 0);
  return {
    currency: "EUR",
    since: "2026-10-01T00:00:00Z",
    until: "2026-11-01T00:00:00Z",
    available: { amount_micros: state.account.available, currency: "EUR" },
    in_bags: { amount_micros: inBags, currency: "EUR" },
    in_bags_approx: true,
    month_spend: M(1234.5, "EUR"),
    projected: M(1890, "EUR"),
    lines: [
      { line: "conversations", amount: M(1200, "EUR"), payer: "client_bag", approx: false },
      { line: "meta", amount: M(18.2, "EUR"), payer: "business_meta", approx: true },
      { line: "build", amount: M(41, "EUR"), payer: "auphere", approx: false, cap: M(50, "EUR"), state: "warning" },
      { line: "companion", amount: M(34.5, "EUR"), payer: "account", approx: false },
    ],
    clients: Object.entries(state.bags).map(([ref, b]) => ({
      ref,
      name: b.name,
      bag: { amount_micros: b.balance, currency: b.currency },
      month_spent: ref === FLOR ? M(12.4, "EUR") : M(0, "EUR"),
      days_left: b.balance > 0 ? b.days : null,
      refill_up_to: b.refill ? { amount_micros: b.refill, currency: b.currency } : null,
      empty: b.balance <= 0,
    })),
  };
}

function daily(days, line) {
  const today = new Date(Date.UTC(2026, 9, 28));
  const list = Array.from({ length: days }, (_, i) => new Date(today.getTime() - (days - 1 - i) * 86_400_000).toISOString().slice(0, 10));
  const lines = line ? [line] : ["conversations", "meta", "build", "companion"];
  const base = { conversations: 3_000_000, meta: 50_000, build: 120_000, companion: 100_000 };
  const series = Object.fromEntries(lines.map((l) => [l, list.map((_, i) => (i % 3 === 0 ? 0 : base[l] + i * 1_000))]));
  return {
    currency: "EUR",
    days: list,
    lines,
    series,
    total: list.map((_, i) => lines.reduce((s, l) => s + series[l][i], 0)),
    approx_lines: lines.filter((l) => l === "meta"),
  };
}

const bag = (ref, extra = {}) => {
  const b = state.bags[ref];
  const assigned = b.balance + b.spent;
  return {
    state: b.balance <= 0 ? "empty" : "ok",
    balance: { amount_micros: b.balance, currency: b.currency },
    assigned: { amount_micros: assigned, currency: b.currency },
    spent: { amount_micros: b.spent, currency: b.currency },
    pct_spent: assigned ? (b.spent / assigned) * 100 : null,
    pct_left: assigned ? (b.balance / assigned) * 100 : null,
    days_left: b.balance > 0 ? b.days : null,
    days_estimable: b.balance > 0,
    alerts: b.balance <= 0 ? ["empty"] : [],
    ...extra,
  };
};

const allowed = () => (usageWrite() ? ["edit", "assign_balance", "new_agent", "archive"] : ["edit", "request_balance", "new_agent"]);

function clientDetail(ref) {
  const b = state.bags[ref];
  return {
    external_client_ref: ref,
    name: b.name,
    status: "active",
    timezone: "Europe/Madrid",
    created_at: NOW,
    updated_at: NOW,
    health: { whatsapp_connected: true, display_phone_number: null, agent_configured: true, agent_version: 2 },
    sector: null,
    serving_since: NOW,
    setup: null,
    quota: null,
    niche: ref === FLOR ? "Floristería de barrio" : "Barbería de barrio",
    info: null,
    website: null,
    country: "ES",
    price_currency: "EUR",
    wallet_currency: b.currency,
    eu_only: true,
    lifecycle: "active",
    revision: 3,
    allowed: allowed(),
  };
}

function row(ref) {
  const b = state.bags[ref];
  const empty = b.balance <= 0;
  return {
    external_client_ref: ref,
    name: b.name,
    status: "active",
    timezone: "Europe/Madrid",
    niche: clientDetail(ref).niche,
    lifecycle: "active",
    attention: empty ? { needs: true, reasons: [{ code: "no_balance", count: 1 }] } : { needs: false, reasons: [] },
    agents: [{ agent_id: AGENT, name: "Citas", visible_state: { code: "serving", tone: "positive", pause_reason: null } }],
    agents_summary: { total: 1, serving: 1, testing: 0, ready_no_channel: 0, draft: 0, paused: 0 },
    bag: bag(ref),
    allowed: allowed(),
  };
}

function panel(ref) {
  const b = state.bags[ref];
  return {
    ref,
    name: b.name,
    niche: clientDetail(ref).niche,
    lifecycle: "active",
    bag: bag(ref),
    attention: b.balance <= 0 ? { needs: true, reasons: [{ code: "no_balance", count: 1 }] } : { needs: false, reasons: [] },
    spend_by_agent: [{ agent_id: AGENT, name: "Citas", spent: { amount_micros: b.spent, currency: b.currency }, share_pct: 100 }],
    month: {
      period_start: "2026-10-01",
      period_end: "2026-10-31",
      conversations: 42,
      handed_to_person: 4,
      resolved_without_person: 38,
      resolved_pct: 90,
      spent: { amount_micros: b.spent, currency: b.currency },
    },
    top_agents: [
      {
        agent_id: AGENT,
        name: "Citas",
        visible_state: { code: "serving", tone: "positive", pause_reason: null },
        spent: { amount_micros: b.spent, currency: b.currency },
        conversations: 42,
        spend_per_conversation: { amount_micros: Math.round(b.spent / 42), currency: b.currency },
        cap: null,
      },
    ],
    agents_total: 1,
    missing: null,
    read: { job: null, website: null, networks: [] },
    allowed: allowed(),
  };
}

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store" });
  res.end(body === undefined || status === 204 ? "" : JSON.stringify(body));
}

async function json(req) {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : {};
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const path = url.pathname;
  const route = `${req.method} ${path}`;
  process.stderr.write(`[money-mock] ${route}\n`);

  if (route === "GET /health") return send(res, 200, { status: "ok" });
  if (route === "POST /__test/reset") {
    state = fresh();
    return send(res, 200, { ok: true });
  }
  if (route === "POST /__test/role") {
    state.role = (await json(req)).role;
    return send(res, 200, { ok: true });
  }
  if (route === "POST /__test/migration") {
    state.migration = { confirmed_at: null, clients: [{ ref: FLOR, amount: M(12.5, "USD") }, { ref: BARBERIA, amount: M(7, "USD") }] };
    return send(res, 200, { ok: true });
  }
  if (route === "GET /__test/state") return send(res, 200, state);

  if (route === "POST /console/auth/session") return send(res, 200, { principal: principal(state.role) });
  if (route === "GET /console/me")
    return send(res, 200, {
      user_id: "00000000-0000-4000-8000-0000000000e2",
      partner_id: "00000000-0000-4000-8000-0000000000e4",
      partner_slug: "ladrian-studio",
      partner_name: "Ladrian Studio",
      role: state.role,
      modules: MODULES,
      companion_enabled: false,
      console_version: "v2",
    });
  if (route === "GET /console/notifications/unread-count") return send(res, 200, { unread: 0 });
  if (route === "GET /console/notifications") return send(res, 200, { items: [], next_cursor: null, unread: 0 });
  if (route === "GET /console/search") return send(res, 200, { clients: [], agents: [], screens: [], actions: [] });

  // ── Consumo ──
  if (route === "GET /console/usage/summary") return send(res, 200, summary());
  if (route === "GET /console/usage/daily") {
    const days = Number(url.searchParams.get("days") ?? 30);
    return send(res, 200, daily(days, url.searchParams.get("line")));
  }
  if (route === "GET /console/usage/detail")
    return send(res, 200, {
      since: "2026-09-28T00:00:00Z",
      until: NOW,
      rows: [
        { ref: FLOR, agent_id: AGENT, meter: "channel.message", line: "conversations", source: "channel", quantity: 420, billable_qty: 420, records: 420, unpriced: 0 },
        { ref: FLOR, agent_id: AGENT, meter: "voice.minutes", line: "conversations", source: "channel", quantity: 12, billable_qty: 12, records: 3, unpriced: 3 },
      ],
    });
  if (route === "GET /console/usage/build-budget")
    return send(res, 200, { cap: M(50, "EUR"), spent: M(41, "EUR"), remaining: M(9, "EUR"), state: "warning", paid_by: "auphere" });
  if (route === "POST /console/usage/build-budget/extension-request") {
    state.extensions += 1;
    return state.extensions > 1 ? send(res, 429, { detail: { code: "request_already_sent_today", retry_after: "tomorrow" } }) : send(res, 201, { status: "requested" });
  }

  // ── la cuenta y las bolsas ──
  if (route === "GET /console/wallet/bags") return send(res, 200, Object.keys(state.bags).map(bagOut));
  if (route === "GET /console/wallet") {
    const active = !(state.migration.confirmed_at == null && state.migration.clients.length > 0);
    const s = summary();
    return send(res, 200, {
      included_remaining_cents: 0,
      purchased_remaining_cents: Math.floor(state.account.available / 1000),
      available_cents: Math.floor(state.account.available / 1000),
      reserve_cents: 0,
      included_expires_at: null,
      exhausted: false,
      bags_active: active,
      account_currency: active ? "EUR" : null,
      assignable_micros: active ? state.account.available : null,
      in_bags_micros: active ? s.in_bags.amount_micros : null,
      in_bags_approx: active ? true : null,
    });
  }
  if (route === "GET /console/wallet/fx") {
    const from = url.searchParams.get("from");
    const to = url.searchParams.get("to");
    return send(res, 200, { rate: rate(from, to).toFixed(8), date: from === to ? null : FX_DATE, source: "ECB" });
  }
  if (route === "GET /console/wallet/migration") return send(res, 200, state.migration);
  if (route === "POST /console/wallet/migration/confirm") {
    if (state.migration.confirmed_at) return send(res, 409, { detail: { code: "already_confirmed" } });
    const body = await json(req);
    state.adjust = body.adjust ?? null;
    for (const c of state.migration.clients) {
      const amount = body.adjust && c.ref in body.adjust ? body.adjust[c.ref] : c.amount.amount_micros;
      state.bags[c.ref].balance += Math.round(amount * rate("USD", state.bags[c.ref].currency));
    }
    state.migration = { ...state.migration, confirmed_at: NOW };
    state.confirmed += 1;
    return send(res, 200, { status: "confirmed", clients: state.migration.clients.length });
  }
  if (route === "POST /console/wallet/bags/move") {
    const body = await json(req);
    state.moves.push({ ...body, key: req.headers["idempotency-key"] ?? null });
    const from = state.bags[body.from_ref];
    const to = state.bags[body.to_ref];
    from.balance -= body.amount.amount_micros;
    to.balance += Math.round(body.amount.amount_micros * rate(from.currency, to.currency));
    return send(res, 200, [bagOut(body.from_ref), bagOut(body.to_ref)]);
  }

  const bm = path.match(/^\/console\/clients\/([a-z0-9-]+)\/bag\/(assign|lower|refill|currency|request)$/);
  if (bm) {
    const ref = bm[1];
    const b = state.bags[ref];
    if (!b) return send(res, 404, { detail: "Unknown client reference" });
    const body = await json(req);
    if (bm[2] === "request") {
      if (usageWrite()) return send(res, 409, { detail: { code: "can_assign" } });
      state.requests.push({ ref, ...body });
      if (state.requested[ref]) return send(res, 429, { detail: { code: "request_already_sent_today", retry_after: "tomorrow" } });
      state.requested[ref] = new Date().toISOString();
      return send(res, 201, { status: "requested" });
    }
    if (!usageWrite()) return send(res, 403, { detail: "forbidden" });
    if (bm[2] === "assign") {
      state.assigns.push({ ref, body, key: req.headers["idempotency-key"] ?? null });
      if (body.amount.currency !== b.currency) return send(res, 422, { detail: { code: "currency_mismatch" } });
      const r = rate(state.account.currency, b.currency);
      const debit = Math.round(body.amount.amount_micros / r);
      if (debit > state.account.available)
        return send(res, 409, {
          detail: { code: "insufficient_account", available_micros: state.account.available, currency: state.account.currency, missing_micros: debit - state.account.available },
        });
      const before = b.balance;
      state.account.available -= debit;
      b.balance += body.amount.amount_micros;
      if (body.refill_up_to !== undefined) b.refill = body.refill_up_to ? body.refill_up_to.amount_micros : null;
      if (body.alert_low !== undefined) b.alert_low = body.alert_low;
      return send(res, 200, {
        client_balance_before: { amount_micros: before, currency: b.currency },
        assigned: body.amount,
        debited_from_account: { amount_micros: debit, currency: state.account.currency },
        fx: { rate: r.toFixed(8), date: r === 1 ? null : FX_DATE, source: "ECB" },
        client_balance_after: { amount_micros: b.balance, currency: b.currency },
        account_left: { amount_micros: state.account.available, currency: state.account.currency },
        warn_low_account: state.account.available < debit,
      });
    }
    if (bm[2] === "lower") {
      state.lowers.push({ ref, body, key: req.headers["idempotency-key"] ?? null });
      if (body.amount.amount_micros > b.balance) return send(res, 409, { detail: { code: "bag_below_spent", available_micros: b.balance } });
      b.balance -= body.amount.amount_micros;
      state.account.available += Math.round(body.amount.amount_micros * rate(b.currency, state.account.currency));
      return send(res, 200, bagOut(ref));
    }
    if (bm[2] === "refill") {
      state.refills.push({ ref, body });
      b.refill = body.up_to ? body.up_to.amount_micros : null;
      return send(res, 200, bagOut(ref));
    }
    if (bm[2] === "currency") {
      if (body.currency === b.currency) return send(res, 200, bagOut(ref));
      const r = rate(b.currency, body.currency);
      if (!body.confirm && b.balance > 0)
        return send(res, 409, {
          detail: { code: "confirm_required", would_be: { amount_micros: Math.round(b.balance * r), currency: body.currency }, fx: { rate: r.toFixed(8), date: FX_DATE, source: "ECB" } },
        });
      b.balance = Math.round(b.balance * r);
      b.currency = body.currency;
      return send(res, 200, bagOut(ref));
    }
  }
  const cm = path.match(/^\/console\/clients\/([a-z0-9-]+)\/agents\/([0-9a-f-]{36})\/cap$/);
  if (cm && req.method === "PUT") {
    const body = await json(req);
    state.caps.push({ ref: cm[1], agent: cm[2], ...body });
    return send(res, 200, { agent_id: cm[2], monthly_cap_micros: body.monthly_cap ? body.monthly_cap.amount_micros : null, lifecycle: "published" });
  }

  // ── los clientes, para abrir el modal desde la lista y el Panel ──
  if (route === "GET /console/clients") {
    const items = Object.keys(state.bags).map(row);
    const attention = items.filter((i) => i.attention.needs).length;
    return send(res, 200, { items, total: items.length, limit: 50, offset: 0, counts: { all: items.length, attention, active: items.length, archived: 0 } });
  }
  const pm = path.match(/^\/console\/clients\/([a-z0-9-]+)(\/panel)?$/);
  if (pm && req.method === "GET") {
    if (!state.bags[pm[1]]) return send(res, 404, { detail: "Unknown client reference" });
    return send(res, 200, pm[2] ? panel(pm[1]) : clientDetail(pm[1]));
  }
  if (route === `GET /console/clients/${FLOR}/business/read` || route === `GET /console/clients/${BARBERIA}/business/read`)
    return send(res, 200, { job: null, website: null, networks: [] });

  return send(res, 404, { detail: "Not Found" });
});

server.listen(PORT, "127.0.0.1", () => process.stderr.write(`[money-mock] listening on ${PORT}\n`));
