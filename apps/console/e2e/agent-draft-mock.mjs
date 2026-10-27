/**
 * La API simulada de la pestaña Agente — spec 047, historia 2 (T041), solo
 * para `agent-draft.config.ts`.
 *
 * Contesta con la forma de `contracts/console-api.md` §4 (el borrador con su
 * revisión, `If-Match` y el 412 con `current` y `changes`) y con lo justo de
 * hoy para que la consola pinte la ficha de un cliente con un agente. Guarda el
 * estado en memoria: el borrador, su revisión y quién escribió cada una.
 *
 * `POST /__test/other-writes` es la otra pestaña: Lucía cambia el tono y las
 * instrucciones del mismo borrador, y la revisión sube. `POST /__test/reset`
 * vuelve al principio. No verifica tokens: no es la puerta, es el otro lado
 * del cable; la puerta la prueban la API y `tests/isolation/`.
 */
import { createServer } from "node:http";

const PORT = Number(process.env.MOCK_API_PORT ?? 8712);
const REF = "panaderia-la-espiga";
const AGENT = "00000000-0000-4000-8000-0000000000a1";
const ME = "luis@ladrian.studio";
const OTHER = "lucia@ladrian.studio";
const MODULES = ["panel", "clients", "usage", "audit", "knowledge", "workstation", "team", "billing", "keys"];
const PRINCIPAL = {
  user_id: "00000000-0000-4000-8000-0000000000e2",
  email: ME,
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

const ACTIVE_PROMPT = "Atiende a los clientes de la panadería con calma y sin prisa.";
const POLICY = {
  schema_version: 1,
  identity: { name: "Recepción", persona: "" },
  tone: { style: "cercano", guidance: "" },
  objective: "",
  schedule: { timezone: "Europe/Madrid", weekly: [], closed_message: "" },
  languages: { primary: "es", allowed: ["es"] },
  escalation: { enabled: true, triggers: ["user_asks_human", "angry", "out_of_scope"], after_n_turns: null, handoff_message: "" },
  ai_disclosure: { enabled: true, disclosure_message: "", decided_by: `console:${ME}`, decided_at: "2026-10-01T09:00:00Z" },
};
const CREATED = "2026-10-20T09:00:00Z";

function fresh() {
  return {
    revision: 0,
    draft: null,
    changes: [],
    versions: [
      { number: 1, version: 1, status: "active", author: ME, created_at: CREATED, published_at: CREATED, published_by: ME, change_note: "Primera versión", base_number: null, system_prompt: ACTIVE_PROMPT, settings: POLICY },
    ],
  };
}
let state = fresh();

const clone = (x) => JSON.parse(JSON.stringify(x));
const active = () => state.versions.find((v) => v.status === "active");

function view() {
  const target = state.draft ?? active();
  return {
    agent_id: AGENT,
    agent_name: "Recepción",
    revision: state.revision,
    exists: state.draft !== null,
    number: target.number,
    version: target.version,
    status: target.status,
    base_number: target.base_number,
    active_number: active().number,
    active_version: active().version,
    author: target.author,
    created_at: target.created_at,
    updated_at: target.created_at,
    change_note: target.change_note,
    system_prompt: target.system_prompt,
    tools: [],
    skills: [],
    settings: target.settings,
    audience: { mode: "everyone", numbers: [], locked: false },
    payment_review: { reviewers: [] },
    screens: state.draft ? screens(state.draft) : [],
    allowed: state.draft ? ["edit", "discard"] : ["edit"],
  };
}

function screens(draft) {
  const out = [];
  if (JSON.stringify(draft.settings) !== JSON.stringify(active().settings)) out.push("settings");
  if (draft.system_prompt !== active().system_prompt) out.push("prompt");
  return out;
}

/** Write into the draft (created from the active version the first time). */
function write(by, patch) {
  if (!state.draft) {
    const base = active();
    const next = Math.max(...state.versions.map((v) => v.number)) + 1;
    state.draft = { ...clone(base), number: next, version: next, status: "staged", author: by, created_at: new Date().toISOString(), published_at: null, published_by: null, change_note: null, base_number: base.number };
    state.versions.unshift(state.draft);
  }
  const fields = [];
  if (patch.system_prompt !== undefined && patch.system_prompt !== state.draft.system_prompt) {
    state.draft.system_prompt = patch.system_prompt;
    fields.push("system_prompt");
  }
  if (patch.settings) {
    for (const key of Object.keys(patch.settings)) {
      if (key !== "schema_version" && JSON.stringify(patch.settings[key]) !== JSON.stringify(state.draft.settings[key])) fields.push(`settings.${key}`);
    }
    state.draft.settings = patch.settings;
  }
  if (patch.note !== undefined) state.draft.change_note = patch.note || null;
  state.revision += 1;
  state.changes.push({ revision: state.revision, kind: "edit", by, at: new Date().toISOString(), fields: fields.sort() });
}

function revisionOf(req) {
  const raw = req.headers["if-match"];
  if (raw === undefined) return null;
  return Number(String(raw).replace(/^W\//, "").replaceAll('"', ""));
}

function conflict(res, expected) {
  return send(res, 412, { detail: { code: "revision_conflict", current: view(), changes: state.changes.filter((c) => c.revision > expected) } });
}

function send(res, status, body, headers = {}) {
  res.writeHead(status, { "content-type": "application/json", "cache-control": "no-store", ...headers });
  res.end(body === undefined ? "" : JSON.stringify(body));
}

async function json(req) {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : {};
}

const client = () => ({
  external_client_ref: REF,
  name: "Panadería La Espiga",
  status: "active",
  timezone: "Europe/Madrid",
  created_at: CREATED,
  updated_at: CREATED,
  health: { whatsapp_connected: true, display_phone_number: "+34 600 000 000", agent_version: active().version, agent_configured: true, ready: true, missing: [] },
  serving_since: CREATED,
  sector: null,
  setup: { agent: true, channel: true, quota: true, active: true, next: null },
  quota: null,
  audience: { mode: "everyone", count: 0 },
});

const bundle = () => ({
  active_version: active().version,
  versions: state.versions.map((v) => ({
    version: v.version,
    status: v.status,
    system_prompt: v.system_prompt,
    tools: [],
    seed_template_ref: null,
    created_by: `console:${v.author}`,
    created_at: v.created_at,
    promoted_at: v.published_at,
    promoted_by: v.published_by ? `console:${v.published_by}` : null,
  })),
  draft_screens: state.draft ? screens(state.draft) : [],
});

const base = `/console/clients/${REF}`;
const draftPath = `${base}/agents/${AGENT}/draft`;

const server = createServer(async (req, res) => {
  const url = new URL(req.url ?? "/", `http://127.0.0.1:${PORT}`);
  const route = `${req.method} ${url.pathname}`;
  process.stderr.write(`[agent-draft-mock] ${route}${url.search}\n`);
  switch (route) {
    case "GET /health":
      return send(res, 200, { status: "ok" });
    case "POST /__test/reset":
      state = fresh();
      return send(res, 200, { ok: true });
    case "POST /__test/other-writes":
      write(OTHER, { system_prompt: "Atiende rápido: la cola es larga.", settings: { ...(state.draft ?? active()).settings, tone: { style: "formal", guidance: "" } } });
      return send(res, 200, view());
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
        // Ola 1 llega a todos: la consola de hoy por defecto.
        console_version: process.env.MOCK_CONSOLE_VERSION === "v2" ? "v2" : "v1",
      });
    case "GET /console/notifications/unread-count":
      return send(res, 200, { unread: 0 });
    case "GET /console/notifications":
      return send(res, 200, { items: [], next_cursor: null, unread: 0 });
    case `GET ${base}`:
      return send(res, 200, client());
    case `GET ${base}/agent`:
      return send(res, 200, bundle());
    case `GET ${base}/agents`:
      return send(res, 200, [{ id: AGENT, name: "Recepción", status: "active", is_principal: true, channels: [], active_version: active().version, draft_version: state.draft?.version ?? null }]);
    case `GET ${base}/agent/settings`: {
      const target = state.draft ?? active();
      return send(res, 200, {
        version: target.version,
        version_status: target.status,
        active_version: active().version,
        has_draft: state.draft !== null,
        settings: target.settings,
        audience: { mode: "everyone", numbers: [], locked: false },
        payment_review: { reviewers: [] },
      });
    }
    case `GET ${draftPath}`:
      return send(res, 200, view(), { etag: `"${state.revision}"` });
    case `PATCH ${draftPath}`: {
      const expected = revisionOf(req);
      if (expected === null) return send(res, 428, { detail: { code: "revision_required" } });
      if (expected !== state.revision) return conflict(res, expected);
      write(ME, await json(req));
      return send(res, 200, view(), { etag: `"${state.revision}"` });
    }
    case `DELETE ${draftPath}`: {
      const expected = revisionOf(req);
      if (expected !== state.revision) return conflict(res, expected ?? -1);
      if (!state.draft) return send(res, 404, { detail: { code: "no_draft" } });
      state.draft.status = "archived";
      state.draft = null;
      state.revision += 1;
      state.changes.push({ revision: state.revision, kind: "discard", by: ME, at: new Date().toISOString(), fields: [] });
      return send(res, 200, view());
    }
    case `GET ${base}/agents/${AGENT}/versions`:
      return send(
        res,
        200,
        state.versions.map((v) => ({
          number: v.number,
          version: v.version,
          status: v.status,
          author: v.author,
          created_at: v.created_at,
          published_at: v.published_at,
          published_by: v.published_by,
          change_note: v.change_note,
          base_number: v.base_number,
        })),
      );
    default:
      return send(res, 404, { detail: "Not Found" });
  }
});

server.listen(PORT, "127.0.0.1", () => process.stderr.write(`[agent-draft-mock] listening on ${PORT}\n`));
