/**
 * La API simulada de la lista de clientes, la cabecera y el Panel de la consola
 * nueva — spec 047 (T065, T067), solo para `client-records.config.ts`.
 *
 * Contesta con la forma de `contracts/console-api.md` §2 lo justo para pintar
 * `/clients` y `/clients/{ref}`: la sesión, `GET /console/me` con
 * `console_version: "v2"`, la campana, la lista con contadores, la cabecera del
 * cliente y su Panel, más archivar y restaurar. Todo lo demás es un 404. No
 * verifica tokens: no es la puerta, es el otro lado del cable.
 */
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_API_PORT ?? 8713);
const MODULES = ["panel", "clients", "usage", "audit", "knowledge", "team", "billing", "keys"];
const PRINCIPAL = {
  user_id: "00000000-0000-4000-8000-0000000000e2",
  email: "lucia@ladrian.studio",
  display_name: "Lucía Pérez",
  locale: "es",
  access: "ok",
  membership_id: "00000000-0000-4000-8000-0000000000e3",
  partner_id: "00000000-0000-4000-8000-0000000000e4",
  partner_slug: "ladrian-studio",
  partner_name: "Ladrian Studio",
  partner_status: "active",
  role: "owner",
  permissions: [],
  console_enabled: true,
  kind: "partner",
  client_name: null,
  modules: MODULES,
};
const USD = (amount) => ({ amount_micros: Math.round(amount * 100_000), currency: "USD" });
const serving = { code: "serving", tone: "positive", pause_reason: null };
const noChannel = { code: "ready_no_channel", tone: "info", pause_reason: null };
const ACTIONS = ["edit", "assign_balance", "new_agent", "archive", "delete"];
const bag = (over = {}) => ({
  state: "ok",
  balance: USD(150),
  assigned: USD(200),
  spent: USD(50),
  pct_spent: 25,
  pct_left: 75,
  days_left: 30,
  days_estimable: true,
  alerts: [],
  ...over,
});
const row = (ref, name, niche, over = {}) => ({
  external_client_ref: ref,
  name,
  status: "active",
  timezone: "Europe/Madrid",
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-26T10:00:00Z",
  out_of_quota: false,
  unlimited_consumption: false,
  setup: null,
  quota: null,
  conversations_7d: 0,
  audience: null,
  niche,
  lifecycle: "active",
  attention: { needs: false, reasons: [] },
  agents: [{ agent_id: `${ref}-a1`, name: "Recepción", visible_state: serving }],
  agents_summary: { total: 1, serving: 1, testing: 0, ready_no_channel: 0, draft: 0, paused: 0 },
  bag: bag(),
  allowed: ACTIONS,
  ...over,
});

const ROWS = [
  row("floristeria-lirio", "Floristería Lirio", "Floristería con entregas", {
    attention: { needs: true, reasons: [{ code: "no_balance", count: 1 }] },
    bag: bag({ state: "empty", balance: USD(0), pct_left: 0, pct_spent: 100, alerts: ["empty"], days_left: null }),
  }),
  row("clinica-sonrisa", "Clínica Dental Sonrisa", "Clínica dental familiar", {
    attention: { needs: true, reasons: [{ code: "low_balance", count: 1 }] },
    bag: bag({ balance: USD(8), assigned: USD(50), pct_left: 16, days_left: 4, state: "low" }),
  }),
  row("friseursalon", "Friseursalon Haarschneidekunst und Bartpflege Großstadt", "Herrenfriseur mit Rasurservice und Bartpflegeberatung", {
    agents: [
      { agent_id: "f1", name: "Terminvereinbarung", visible_state: serving },
      { agent_id: "f2", name: "Erinnerungen", visible_state: noChannel },
    ],
    agents_summary: { total: 2, serving: 1, testing: 0, ready_no_channel: 1, draft: 0, paused: 0 },
    attention: { needs: true, reasons: [{ code: "agent_without_channel", count: 1 }] },
  }),
  row("barberia-cultor", "Barbería Cultor", "Barbería de barrio con 2 sedes"),
];
const archived = new Set();

function lifecycleOf(ref) {
  return archived.has(ref) ? "archived" : "active";
}

function detail(ref) {
  const r = ROWS.find((x) => x.external_client_ref === ref);
  if (!r) return null;
  const lifecycle = lifecycleOf(ref);
  return {
    ...r,
    status: lifecycle,
    health: { whatsapp_connected: true, display_phone_number: null, agent_configured: true, agent_version: 1 },
    sector: null,
    serving_since: null,
    info: "Desde 1998",
    website: null,
    country: "ES",
    price_currency: "EUR",
    wallet_currency: "USD",
    eu_only: true,
    lifecycle,
    revision: 3,
    allowed: lifecycle === "archived" ? ["edit", "assign_balance", "restore", "delete"] : ACTIONS,
  };
}

function panel(ref) {
  const r = ROWS.find((x) => x.external_client_ref === ref);
  if (!r) return null;
  return {
    ref,
    name: r.name,
    niche: r.niche,
    lifecycle: lifecycleOf(ref),
    bag: bag({ balance: USD(6), assigned: USD(16), spent: USD(10), pct_spent: 85, pct_left: 15, days_left: 4.2, state: "low", alerts: ["warn_80"] }),
    attention: { needs: true, reasons: [{ code: "low_balance", count: 1 }] },
    spend_by_agent: [
      { agent_id: "a1", name: "Terminvereinbarungsassistent", spent: USD(8), share_pct: 80 },
      { agent_id: "a2", name: "Ventas", spent: USD(2), share_pct: 20 },
    ],
    month: {
      period_start: "2026-10-01",
      period_end: "2026-10-31",
      conversations: 128,
      handed_to_person: 21,
      resolved_without_person: 107,
      resolved_pct: 83.6,
      spent: USD(10),
    },
    top_agents: [
      { agent_id: "a1", name: "Terminvereinbarungsassistent für Neukunden", visible_state: serving, spent: USD(8), conversations: 97, spend_per_conversation: USD(0.08), cap: null },
      { agent_id: "a2", name: "Ventas", visible_state: noChannel, spent: USD(2), conversations: 31, spend_per_conversation: USD(0.06), cap: null },
    ],
    agents_total: 2,
    missing: { section: "hours", action: "add_hours" },
    read: { job: null, website: null, networks: [] },
    allowed: ACTIONS,
  };
}

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store" });
  res.end(body === undefined ? "" : JSON.stringify(body));
}

const COUNTS = { all: ROWS.length, attention: 3, active: ROWS.length, archived: 0 };

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const route = `${req.method} ${url.pathname}`;
  process.stderr.write(`[records-mock] ${route}${url.search}\n`);
  const m = url.pathname.match(/^\/console\/clients\/([^/]+)(\/[a-z/]+)?$/);
  if (route === "GET /health") return send(res, 200, { status: "ok" });
  if (route === "POST /console/auth/session") return send(res, 200, { principal: PRINCIPAL });
  if (route === "GET /console/me")
    return send(res, 200, {
      user_id: PRINCIPAL.user_id,
      partner_id: PRINCIPAL.partner_id,
      partner_slug: PRINCIPAL.partner_slug,
      partner_name: PRINCIPAL.partner_name,
      role: PRINCIPAL.role,
      modules: MODULES,
      companion_enabled: false,
      console_version: "v2",
    });
  if (route === "GET /console/notifications/unread-count") return send(res, 200, { unread: 0 });
  if (route === "GET /console/notifications") return send(res, 200, { items: [], next_cursor: null, unread: 0 });
  if (route === "GET /console/search") return send(res, 200, { clients: [], agents: [], screens: [], actions: [] });
  if (route === "GET /console/clients") {
    const filter = url.searchParams.get("filter") ?? "all";
    const items = ROWS.filter((r) => (filter === "attention" ? r.attention.needs : filter === "archived" ? archived.has(r.external_client_ref) : true));
    return send(res, 200, { items, total: items.length, limit: 50, offset: 0, counts: COUNTS });
  }
  if (m && req.method === "GET" && !m[2]) {
    const d = detail(decodeURIComponent(m[1]));
    return d ? send(res, 200, d) : send(res, 404, { detail: "Unknown client reference" });
  }
  if (m && req.method === "GET" && m[2] === "/panel") {
    const p = panel(decodeURIComponent(m[1]));
    return p ? send(res, 200, p) : send(res, 404, { detail: "Unknown client reference" });
  }
  if (m && req.method === "GET" && m[2] === "/business/read") return send(res, 200, { job: null, website: null, networks: [] });
  if (m && req.method === "POST" && m[2] === "/archive") {
    const ref = decodeURIComponent(m[1]);
    archived.add(ref);
    return send(res, 200, { ref, lifecycle: "archived", previous: "active", agents: [], undo: "restore" });
  }
  if (m && req.method === "POST" && m[2] === "/restore") {
    const ref = decodeURIComponent(m[1]);
    archived.delete(ref);
    return send(res, 200, { ref, lifecycle: "active", previous: "archived", agents: [], undo: null });
  }
  return send(res, 404, { detail: "Not Found" });
});

server.listen(PORT, "127.0.0.1", () => process.stderr.write(`[records-mock] listening on ${PORT}\n`));
