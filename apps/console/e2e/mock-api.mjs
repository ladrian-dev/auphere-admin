/**
 * La API simulada del contrato — spec 047, solo para `shell.config.ts`.
 *
 * El marco nuevo se puede probar en un navegador de verdad antes de que la API
 * del bloque esté desplegada: esto contesta, con la forma de
 * `contracts/console-api.md` §1 y de `GET /console/me`, lo justo para que la
 * consola pinte el marco a un partner con la consola nueva activada y tres
 * pantallas que piden poco (Notificaciones, Equipo y API). Todo lo demás es un
 * 404, como lo daría una ruta que no existe.
 *
 * No verifica tokens: no es la puerta, es el otro lado del cable. La puerta
 * (token de 60 s y pertenencia) la prueban la API y `tests/isolation/`.
 */
import { readFileSync } from "node:fs";
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_API_PORT ?? 8711);
const SEARCH = JSON.parse(readFileSync(new URL("./fixtures/search-world.json", import.meta.url), "utf8"));

const MODULES = ["panel", "clients", "usage", "audit", "knowledge", "workstation", "team", "billing", "keys"];
const PRINCIPAL = {
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
  role: "owner",
  permissions: [],
  console_enabled: true,
  kind: "partner",
  client_name: null,
  modules: MODULES,
};

const hoursAgo = (h) => new Date(Date.now() - h * 3_600_000).toISOString();
let notifications = [
  {
    id: "00000000-0000-4000-8000-000000000101",
    kind: "member.joined",
    severity: "info",
    data: { email: "lucia@ladrian.studio", role: "Constructor" },
    external_client_ref: null,
    read: false,
    created_at: hoursAgo(2),
  },
  {
    id: "00000000-0000-4000-8000-000000000102",
    kind: "channel.degraded",
    severity: "critical",
    data: { client: "Clínica Dental Sonrisa", channel_status: "desconectado" },
    external_client_ref: "clinica-dental-sonrisa",
    read: false,
    created_at: hoursAgo(5),
  },
  {
    id: "00000000-0000-4000-8000-000000000103",
    kind: "client.activated",
    severity: "info",
    data: { client: "ADSL System" },
    external_client_ref: "adsl-system",
    read: true,
    created_at: hoursAgo(72),
  },
];

const fold = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** La misma regla que `fixtures/search.ts` y que la API: pantallas y acciones van siempre todas. */
function search(q) {
  const needle = fold(q.trim());
  const base = { screens: SEARCH.screens, actions: SEARCH.actions };
  if (!needle) return { clients: [], agents: [], ...base };
  return {
    clients: SEARCH.clients.filter((c) => fold(`${c.name} ${c.ref} ${c.niche ?? ""}`).includes(needle)),
    agents: SEARCH.agents.filter((a) => fold(a.name).includes(needle)),
    ...base,
  };
}

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store" });
  res.end(body === undefined ? "" : JSON.stringify(body));
}

const server = createServer((req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const route = `${req.method} ${url.pathname}`;
  process.stderr.write(`[mock-api] ${route}${url.search}\n`);
  switch (route) {
    case "GET /health":
      return send(res, 200, { status: "ok" });
    case "POST /console/auth/session":
      return send(res, 200, { principal: PRINCIPAL });
    case "GET /console/me":
      return send(res, 200, {
        user_id: PRINCIPAL.user_id,
        partner_id: PRINCIPAL.partner_id,
        partner_slug: PRINCIPAL.partner_slug,
        partner_name: PRINCIPAL.partner_name,
        role: PRINCIPAL.role,
        modules: MODULES,
        companion_enabled: false,
        // `MOCK_CONSOLE_VERSION=v1` pinta la consola de hoy: así se ve la
        // suite en rojo sin el marco nuevo, y que el de hoy no ha cambiado.
        console_version: process.env.MOCK_CONSOLE_VERSION === "v1" ? "v1" : "v2",
      });
    case "GET /console/notifications/unread-count":
      return send(res, 200, { unread: notifications.filter((n) => !n.read).length });
    case "GET /console/notifications": {
      const limit = Number(url.searchParams.get("limit") ?? 20);
      const unreadOnly = url.searchParams.get("unread") === "true";
      const items = notifications.filter((n) => !unreadOnly || !n.read).slice(0, limit);
      return send(res, 200, { items, next_cursor: null, unread: notifications.filter((n) => !n.read).length });
    }
    case "POST /console/notifications/read-all": {
      const marked = notifications.filter((n) => !n.read).length;
      notifications = notifications.map((n) => ({ ...n, read: true }));
      return send(res, 200, { marked });
    }
    case "GET /console/search":
      return send(res, 200, search(url.searchParams.get("q") ?? ""));
    case "GET /console/clients":
      return send(res, 200, { items: [], total: 0, limit: Number(url.searchParams.get("limit") ?? 50), offset: 0 });
    case "GET /console/keys":
      return send(res, 200, []);
    case "GET /console/team":
      return send(res, 200, { members: [], invitations: [] });
    default:
      return send(res, 404, { detail: "Not Found" });
  }
});

server.listen(PORT, "127.0.0.1", () => process.stderr.write(`[mock-api] listening on ${PORT}\n`));
