/**
 * La API simulada del alta en tres datos — spec 047 (T050), solo para
 * `clients-v2.config.ts`.
 *
 * Contesta con la forma de `contracts/console-api.md` §2 lo justo para que la
 * consola nueva pinte la lista de clientes y el modal «Nuevo cliente»: la
 * sesión, `GET /console/me` con `console_version: "v2"`, la campana, la lista,
 * la detección de enlaces, las sugerencias de nicho y el alta. La detección es
 * una copia mínima de la regla de la API (`services/business/links.py`): web,
 * `@usuario` suelto y el correo que no es una web. Todo lo demás es un 404.
 *
 * No verifica tokens: no es la puerta, es el otro lado del cable.
 */
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_API_PORT ?? 8712);
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
  role: "builder",
  permissions: [],
  console_enabled: true,
  kind: "partner",
  client_name: null,
  modules: MODULES,
};

/** Lo que la prueba lee después: el cuerpo de cada alta. */
const created = [];

const TLD = { cl: ["CL", "America/Santiago", "CLP", false], es: ["ES", "Europe/Madrid", "EUR", true], mx: ["MX", "America/Mexico_City", "MXN", false] };

function detect(info, browserTz) {
  const emails = [...info.matchAll(/[\w.+-]+@[\w-]+(\.[\w-]+)+/g)].map((m) => [m.index, m.index + m[0].length]);
  const inEmail = (i) => emails.some(([a, b]) => i >= a && i < b);
  const links = [];
  for (const m of info.matchAll(/(?<![@\w.])(?:https?:\/\/)?(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})(?:\/\S*)?/gi)) {
    if (inEmail(m.index)) continue;
    const host = m[1].toLowerCase();
    links.push({ kind: "web", network: "web", value: host, url: `https://${host}`, handle: null, target: "website", guessed: false, alternatives: [] });
  }
  for (const m of info.matchAll(/(?<![\w@./])@([A-Za-z0-9._]{1,30})/g)) {
    if (inEmail(m.index)) continue;
    const handle = `@${m[1]}`;
    links.push({
      kind: "social",
      network: "instagram",
      value: handle,
      url: `https://www.instagram.com/${m[1]}`,
      handle,
      target: "links",
      guessed: true,
      alternatives: ["tiktok", "x", "threads", "youtube", "facebook"],
    });
  }
  const web = links.find((l) => l.network === "web");
  const tld = web ? web.value.split(".").pop() : null;
  const known = tld && TLD[tld];
  const deduced = known
    ? { country: known[0], timezone: known[1], price_currency: known[2], wallet_currency: "USD", eu_only: known[3], source: "web" }
    : { country: null, timezone: browserTz || "UTC", price_currency: null, wallet_currency: "USD", eu_only: false, source: browserTz ? "browser" : "default" };
  return { links, deduced };
}

const NICHES = [
  ["barbershop", "beauty", "barber"],
  ["hair_salon", "beauty", "peluquer"],
  ["nail_studio", "beauty", "uñas"],
  ["clinic", "health", "clínica"],
  ["dental", "health", "dental"],
  ["aesthetic_clinic", "aesthetics", "estétic"],
  ["restaurant", "food", "restaur"],
  ["online_store", "retail", "tienda"],
  ["collections", "services", "cobran"],
];

function niches(q) {
  const needle = (q ?? "").toLowerCase();
  return NICHES.filter(([key, , word]) => !needle || key.includes(needle) || word.includes(needle)).map(([key, group]) => ({
    source: "template",
    key,
    group,
    value: null,
    uses: 0,
  }));
}

const slug = (name) =>
  name
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "") || "cliente";

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store" });
  res.end(body === undefined ? "" : JSON.stringify(body));
}

async function json(req) {
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const text = Buffer.concat(chunks).toString("utf8");
  return text ? JSON.parse(text) : {};
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const route = `${req.method} ${url.pathname}`;
  process.stderr.write(`[clients-mock] ${route}${url.search}\n`);
  switch (route) {
    case "GET /health":
      return send(res, 200, { status: "ok" });
    case "GET /__created":
      return send(res, 200, created);
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
        console_version: "v2",
      });
    case "GET /console/notifications/unread-count":
      return send(res, 200, { unread: 0 });
    case "GET /console/notifications":
      return send(res, 200, { items: [], next_cursor: null, unread: 0 });
    case "GET /console/search":
      return send(res, 200, { clients: [], agents: [], screens: [], actions: [] });
    case "GET /console/clients":
      return send(res, 200, { items: [], total: 0, limit: Number(url.searchParams.get("limit") ?? 50), offset: 0 });
    case "GET /console/clients/niche-suggestions":
      return send(res, 200, { items: niches(url.searchParams.get("q")) });
    case "POST /console/clients/link-detection": {
      const body = await json(req);
      return send(res, 200, detect(String(body.info ?? ""), body.browser_timezone ?? null));
    }
    case "POST /console/clients": {
      const body = await json(req);
      created.push({ body, idempotency_key: req.headers["idempotency-key"] ?? null });
      const hasLinks = detect(String(body.info ?? "")).links.length > 0;
      return send(res, 201, {
        ref: slug(String(body.name ?? "")),
        name: body.name,
        status: "active",
        duplicate_name: false,
        read_job_id: hasLinks ? "33333333-3333-4333-8333-333333333333" : null,
      });
    }
    default:
      return send(res, 404, { detail: "Not Found" });
  }
});

server.listen(PORT, "127.0.0.1", () => process.stderr.write(`[clients-mock] listening on ${PORT}\n`));
