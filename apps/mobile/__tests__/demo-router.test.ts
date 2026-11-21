import { readFileSync } from "node:fs";
import { join } from "node:path";

import createClient from "openapi-fetch";

import { ARRIVAL_MS, demoEvents, demoFetch, demoIds, demoRoutes, resetDemo } from "@/api/demo";
import { createDemo } from "@/api/reservas-demo";
import type { components, paths } from "@/api/schema.gen";
import type { InboxEvent } from "@/api/sse";

type S = components["schemas"];

/**
 * Spec 069, Requisito 23: the example API answers every route the app calls
 * with the API's own shapes (checked here against `openapi.json`, on top of
 * the types the routes are written with), and what the app does to it shows
 * on the next read.
 */

// A Tuesday, so Reservas' example (seeded by the date) is the same on every run, with a booking under way.
jest.useFakeTimers({ now: new Date("2026-11-17T14:30:00Z") });

/** Let the example's waits pass; the outcome is caught first so a refusal is never «unhandled». */
async function run<T>(p: Promise<T>): Promise<T> {
  const settled = p.then(
    (value) => ({ ok: true as const, value }),
    (error: unknown) => ({ ok: false as const, error }),
  );
  await jest.advanceTimersByTimeAsync(3000);
  const r = await settled;
  if (r.ok) return r.value;
  throw r.error;
}

const BASE = "http://demo.test";

type Reply = { status: number; body: unknown; text: string };

async function call(method: string, path: string, opts: { json?: unknown; headers?: Record<string, string>; form?: FormData } = {}): Promise<Reply> {
  const headers: Record<string, string> = { ...(opts.json !== undefined ? { "Content-Type": "application/json" } : {}), ...opts.headers };
  const res = await run(
    demoFetch(`${BASE}${path}`, {
      method,
      headers,
      ...(opts.form ? { body: opts.form } : opts.json !== undefined ? { body: JSON.stringify(opts.json) } : {}),
    }),
  );
  const text = await res.text();
  return { status: res.status, text, body: text ? (JSON.parse(text) as unknown) : null };
}

// ── the schema, as the API publishes it ───────────────────────────────

type Schema = {
  $ref?: string;
  type?: string | string[];
  properties?: Record<string, Schema>;
  required?: string[];
  items?: Schema;
  anyOf?: Schema[];
  oneOf?: Schema[];
  allOf?: Schema[];
  enum?: unknown[];
  const?: unknown;
  additionalProperties?: boolean | Schema;
};
type Spec = {
  paths: Record<string, Record<string, { responses: Record<string, { content?: Record<string, { schema: Schema }> }> }>>;
  components: { schemas: Record<string, Schema> };
};
const spec = JSON.parse(readFileSync(join(__dirname, "../src/api/openapi.json"), "utf8")) as Spec;

const isObject = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);

/** What in `value` breaks `schema`: types, required fields, enums, and any field the schema does not name. */
function problems(value: unknown, schema: Schema, at: string): string[] {
  if (schema.$ref) {
    const target = spec.components.schemas[schema.$ref.split("/").pop() ?? ""];
    return target ? problems(value, target, at) : [`${at}: unknown ${schema.$ref}`];
  }
  if (schema.allOf) return schema.allOf.flatMap((s) => problems(value, s, at));
  const alternatives = schema.anyOf ?? schema.oneOf;
  if (alternatives) {
    const tries = alternatives.map((s) => problems(value, s, at));
    return tries.some((p) => p.length === 0) ? [] : (tries.sort((a, b) => a.length - b.length)[0] ?? [`${at}: no alternative`]);
  }
  if (schema.enum && !schema.enum.includes(value)) return [`${at}: ${JSON.stringify(value)} is not one of ${JSON.stringify(schema.enum)}`];
  if ("const" in schema && schema.const !== value) return [`${at}: ${JSON.stringify(value)} is not ${JSON.stringify(schema.const)}`];
  if (schema.type) {
    const types = Array.isArray(schema.type) ? schema.type : [schema.type];
    const fits = (t: string) =>
      t === "null"
        ? value === null
        : t === "array"
          ? Array.isArray(value)
          : t === "object"
            ? isObject(value)
            : t === "integer"
              ? Number.isInteger(value)
              : t === "number"
                ? typeof value === "number"
                : typeof value === t;
    if (!types.some(fits)) return [`${at}: expected ${types.join("|")}, got ${JSON.stringify(value)?.slice(0, 80)}`];
  }
  if (Array.isArray(value) && schema.items) return value.flatMap((v, i) => problems(v, schema.items as Schema, `${at}[${i}]`));
  if (!isObject(value)) return [];
  const out: string[] = [];
  for (const key of schema.required ?? []) if (!(key in value)) out.push(`${at}.${key}: missing`);
  for (const [key, v] of Object.entries(value)) {
    const own = schema.properties?.[key];
    if (own) out.push(...problems(v, own, `${at}.${key}`));
    else if (isObject(schema.additionalProperties)) out.push(...problems(v, schema.additionalProperties, `${at}.${key}`));
    else if (schema.properties && schema.additionalProperties !== true) out.push(`${at}.${key}: not in the schema`);
  }
  return out;
}

/** The reply checked against the schema of its route and status (an empty body where the schema has none). */
function conforms(method: string, template: string, r: Reply): string[] {
  const op = spec.paths[template]?.[method.toLowerCase()];
  if (!op) return [`${method} ${template}: not in openapi.json`];
  const response = op.responses[String(r.status)];
  if (!response) return [`${method} ${template}: ${r.status} is not a status of this route`];
  const schema = response.content?.["application/json"]?.schema;
  if (!schema || r.status === 204) return r.text === "" ? [] : [`${method} ${template}: expected no body`];
  return problems(r.body, schema, `${method} ${template}`);
}

const obj = (v: unknown): Record<string, unknown> => (isObject(v) ? v : {});
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);

beforeEach(() => {
  resetDemo();
  delete process.env.EXPO_PUBLIC_DEMO_CURRENCY;
});

describe("the schema check itself", () => {
  it("catches a missing field, a value off its enum, a wrong type and a field the schema does not name", () => {
    const counts = { $ref: "#/components/schemas/CountsOut" };
    expect(problems({ unread: 1, waiting: 0 }, counts, "c")).toEqual([]);
    expect(problems({ unread: 1 }, counts, "c")).toEqual(["c.waiting: missing"]);
    expect(problems({ unread: 1, waiting: "0" }, counts, "c")).toHaveLength(1);
    expect(problems({ unread: 1, waiting: 0, extra: true }, counts, "c")).toEqual(["c.extra: not in the schema"]);
    expect(problems({ type: "bogus", id: "x", at: "y" }, { $ref: "#/components/schemas/ThreadItemOut" }, "i")).toHaveLength(1);
    expect(conforms("GET", "/console/lite/inbox/counts", { status: 200, text: "{}", body: {} })).toHaveLength(2);
    expect(conforms("POST", "/console/lite/inbox/conversations/{conversation_id}/read", { status: 204, text: "null", body: null })).toHaveLength(1);
  });
});

// ── every route ───────────────────────────────────────────────────────

describe("every route the router lists", () => {
  it("answers 2xx with the schema's body (Reservas refuses what Servicios or its example does not do, as the API would)", async () => {
    const C = (id: string) => `/console/lite/inbox/conversations/${id}`;
    const ids = demoIds;
    const done = new Set<string>();
    const failures: string[] = [];

    /** One sample request: `template` is the router's path, `path` the request's. */
    const hit = async (method: string, template: string, path: string, opts: Parameters<typeof call>[2] = {}, expect: number | null = null) => {
      const r = await call(method, path, opts);
      done.add(`${method} ${template}`);
      if (expect !== null) {
        if (r.status !== expect) failures.push(`${method} ${path}: ${r.status} (expected ${expect}) ${r.text.slice(0, 200)}`);
        return r;
      }
      if (r.status < 200 || r.status >= 300) failures.push(`${method} ${path}: ${r.status} ${r.text.slice(0, 200)}`);
      else failures.push(...conforms(method, template, r));
      return r;
    };

    // public
    await hit("GET", "/app/config", "/app/config");
    const device = { platform: "ios", display_name: "iPhone de prueba", install_id: "install-1", app_version: "1.3.0", locale: "es" };
    await hit("POST", "/app/sign-in/password", "/app/sign-in/password", { json: { email: "camila@clinicabrisa.test", password: "una-clave", ...device } });
    await hit("POST", "/app/sign-in/google", "/app/sign-in/google", { json: { code: "abc", code_verifier: "v".repeat(43), ...device } });
    await hit("POST", "/app/password-reset", "/app/password-reset", { json: { email: "camila@clinicabrisa.test" } });
    await hit("POST", "/app/phones/refresh", "/app/phones/refresh", { json: { refresh_token: "demo-refresh-0001-not-a-real-secret", app_version: "1.3.0" } });

    // who and what, Inicio, Consumo
    await hit("GET", "/console/lite/me", "/console/lite/me");
    await hit("GET", "/console/lite/home", "/console/lite/home");
    await hit("GET", "/console/lite/usage/summary", "/console/lite/usage/summary");
    await hit("GET", "/console/lite/usage/spend", "/console/lite/usage/spend?days=90");

    // the Bandeja
    for (const filter of ["all", "unread", "waiting", "resolved"]) {
      await hit("GET", "/console/lite/inbox/conversations", `/console/lite/inbox/conversations?filter=${filter}`);
    }
    await hit("GET", "/console/lite/inbox/counts", "/console/lite/inbox/counts");
    const T = "/console/lite/inbox/conversations/{conversation_id}";
    for (const id of Object.values(ids).filter((x) => x !== ids.nuria)) {
      await hit("GET", T, C(id));
      await hit("GET", `${T}/messages`, `${C(id)}/messages`);
    }
    const marta = await call("GET", `${C(ids.marta)}/messages`);
    const comment = list(obj(marta.body).items).map(obj).find((i) => i.comment === true && i.direction === "inbound");
    await hit("GET", `${T}/messages/{message_id}/post`, `${C(ids.marta)}/messages/${String(comment?.id)}/post`);
    await hit("GET", "/console/lite/inbox/tags", "/console/lite/inbox/tags");
    await hit("GET", "/console/lite/inbox/replies", "/console/lite/inbox/replies");

    await hit("POST", `${T}/read`, `${C(ids.lucia)}/read`);
    await hit("POST", `${T}/unread`, `${C(ids.lucia)}/unread`);
    await hit("POST", `${T}/takeover`, `${C(ids.lucia)}/takeover`, { headers: { "If-Match": "1" } });
    await hit("POST", `${T}/release`, `${C(ids.lucia)}/release`, { headers: { "If-Match": "2" } });
    await hit("POST", `${T}/messages`, `${C(ids.sofia)}/messages`, { json: { text: "Claro, tráelo." }, headers: { "Idempotency-Key": "k1" } });
    const form = new FormData();
    form.append("file", new Blob(["x"], { type: "image/jpeg" }), "foto.jpg");
    await hit("POST", `${T}/attachments`, `${C(ids.sofia)}/attachments`, { form, headers: { "Idempotency-Key": "k2" } });
    await hit("PUT", `${T}/tags`, `${C(ids.diego)}/tags`, { json: { tags: ["Ortodoncia", "VIP"] } });
    await hit("PUT", `${T}/note`, `${C(ids.diego)}/note`, { json: { body: "Llamar antes del jueves." } });
    await hit("POST", `${T}/resolve`, `${C(ids.diego)}/resolve`);
    await hit("POST", `${T}/reopen`, `${C(ids.diego)}/reopen`);
    await hit("POST", `${T}/clear`, `${C(ids.valentina)}/clear`);
    await hit("POST", `${T}/archive`, `${C(ids.laura)}/archive`);

    // «Corregir»
    const diego = await call("GET", `${C(ids.diego)}/messages`);
    const answer = list(obj(diego.body).items).map(obj).find((i) => obj(i.author).kind === "agent");
    const draft = await hit("POST", "/console/lite/inbox/{conversation_id}/messages/{message_id}/corrections", `/console/lite/inbox/${ids.diego}/messages/${String(answer?.id)}/corrections`, {
      json: { text: "La valoración es gratis y dura 30 minutos.", scope: "business" },
      headers: { "Idempotency-Key": "c1" },
    });
    const cid = String(obj(draft.body).id);
    await hit("PATCH", "/console/lite/corrections/{correction_id}", `/console/lite/corrections/${cid}`, { json: { lesson: "La valoración es gratis y dura 30 minutos." }, headers: { "If-Match": '"1"' } });
    await hit("POST", "/console/lite/corrections/{correction_id}/send", `/console/lite/corrections/${cid}/send`, { headers: { "If-Match": '"2"', "Idempotency-Key": "c2" } });
    await hit("POST", "/console/lite/corrections/{correction_id}/undo", `/console/lite/corrections/${cid}/undo`, { headers: { "Idempotency-Key": "c3" } });

    // this phone
    await hit("GET", "/console/lite/phones/current/notices", "/console/lite/phones/current/notices");
    await hit("PUT", "/console/lite/phones/current/notices", "/console/lite/phones/current/notices", { json: { kinds: ["inbox.waiting"], quiet_outside_hours: false } });
    await hit("PUT", "/console/lite/phones/current/push", "/console/lite/phones/current/push", { json: { provider: "apns", token: "demo-token", apns_environment: "sandbox" } });
    await hit("POST", "/console/lite/account/deletion-request", "/console/lite/account/deletion-request");
    // spec 069 (R17.2): the inbox's inactivity close, from Ajustes
    await hit("GET", "/console/lite/inbox/settings", "/console/lite/inbox/settings");
    await hit("PATCH", "/console/lite/inbox/settings", "/console/lite/inbox/settings", { json: { autoclose_hours: 168 } });
    await hit("DELETE", "/console/lite/phones/current", "/console/lite/phones/current");

    // Reservas, through the example of spec 044
    const R = "/console/lite/reservas";
    const settings = await hit("GET", `${R}/settings`, `${R}/settings`);
    await hit("PATCH", `${R}/settings`, `${R}/settings`, { json: { waitlist: { enabled: true, lead_minutes: 180 } }, headers: { "If-Match": String(obj(settings.body).version) } });
    await hit("GET", `${R}/staff`, `${R}/staff?archived=false`);
    const services = await hit("GET", `${R}/services`, `${R}/services?archived=false`);
    await hit("GET", `${R}/blocks`, `${R}/blocks?from=2026-11-17&to=2027-01-16`);
    await hit("GET", `${R}/occupancy`, `${R}/occupancy?from=2026-11-17&to=2026-11-23`);
    const week = await hit("GET", `${R}/bookings`, `${R}/bookings?from=2026-11-17&to=2026-11-23`);
    const bookings = list(obj(week.body).items).map(obj);
    const used = new Set<unknown>();
    /** A booking that allows `a` and was not acted on yet (each action bumps its version). */
    const allowing = (a: string) => {
      const b = bookings.find((x) => list(x.allowed).includes(a) && !used.has(x.id));
      used.add(b?.id);
      return b;
    };
    const first = bookings[0];
    await hit("GET", `${R}/bookings/{booking_id}`, `${R}/bookings/${String(first?.id)}`);
    const acted: Record<string, Record<string, unknown> | undefined> = {};
    for (const action of ["confirm", "noshow", "cancel"]) {
      const b = allowing(action);
      expect(b).toBeDefined();
      const r = await hit("POST", `${R}/bookings/{booking_id}/${action}`, `${R}/bookings/${String(b?.id)}/${action}`, {
        headers: { "If-Match": String(b?.version) },
        ...(action === "cancel" ? { json: { notify: true } } : {}),
      });
      acted[action] = obj(r.body);
    }
    // The one marked «No vino» can be undone, with its new version.
    const noShow = acted.noshow;
    expect(list(noShow?.allowed)).toContain("undo");
    await hit("POST", `${R}/bookings/{booking_id}/undo`, `${R}/bookings/${String(noShow?.id)}/undo`, { headers: { "If-Match": String(noShow?.version) } });
    // Servicios has no «Llegó» and no walk-ins: the API refuses them, and so does the example.
    await hit("POST", `${R}/bookings/{booking_id}/arrive`, `${R}/bookings/${String(first?.id)}/arrive`, { headers: { "If-Match": String(first?.version) } }, 409);
    await hit("POST", `${R}/walkins`, `${R}/walkins`, { json: { party_size: 2, name: null }, headers: { "Idempotency-Key": "w1" } }, 422);

    // Spec 069's additions answer 2xx once spec 044's example has them, and the API's refusal until then.
    const example = createDemo("services", null);
    const can = (k: "move" | "requestConfirmation" | "stopOffer") => typeof example[k] === "function";
    const cancellable = allowing("cancel");
    await hit("GET", `${R}/bookings/{booking_id}/cancel-preview`, `${R}/bookings/${String(cancellable?.id)}/cancel-preview`);
    const movable = allowing("move");
    if (can("move") && movable) {
      const free = await call("GET", `${R}/slots?date=${String(obj(movable.local).date)}&service_id=${String(obj(movable.service).id)}&staff_id=${String(obj(movable.staff).id)}&exclude=${String(movable.id)}`);
      const to = list(obj(free.body).slots).map(obj)[0];
      await hit("POST", `${R}/bookings/{booking_id}/move`, `${R}/bookings/${String(movable.id)}/move`, { json: { date: obj(movable.local).date, time: to?.time, notify: true }, headers: { "If-Match": String(movable.version) } });
    } else {
      await hit("POST", `${R}/bookings/{booking_id}/move`, `${R}/bookings/${String(cancellable?.id)}/move`, { json: { date: "2026-11-19", time: "10:00", notify: true }, headers: { "If-Match": String(cancellable?.version) } }, 409);
    }
    const askable = allowing("request_confirmation");
    if (can("requestConfirmation") && askable) {
      await hit("POST", `${R}/bookings/{booking_id}/request-confirmation`, `${R}/bookings/${String(askable.id)}/request-confirmation`, { headers: { "If-Match": String(askable.version) } });
    } else {
      await hit("POST", `${R}/bookings/{booking_id}/request-confirmation`, `${R}/bookings/${String(cancellable?.id)}/request-confirmation`, { headers: { "If-Match": String(cancellable?.version) } }, 409);
    }
    const offers = await hit("GET", `${R}/offers`, `${R}/offers?status=running`);
    const running = list(obj(offers.body).items).map(obj)[0];
    if (can("stopOffer") && running) await hit("POST", `${R}/offers/{offer_id}/stop`, `${R}/offers/${String(running.id)}/stop`);
    else await hit("POST", `${R}/offers/{offer_id}/stop`, `${R}/offers/o-none/stop`, {}, 404);
    const service = list(obj(services.body).items).map(obj)[0];
    const slots = await hit("GET", `${R}/slots`, `${R}/slots?date=2026-11-18&service_id=${String(service?.id)}`);
    const slot = list(obj(slots.body).slots).map(obj)[0];
    await hit("POST", `${R}/bookings`, `${R}/bookings`, {
      json: { date: "2026-11-18", time: slot?.time, service_id: service?.id, staff_id: list(slot?.staff_ids)[0] ?? null, contact: { name: "Irene Prueba", phone: "+34 600 000 099" }, note: null, join_waitlist: false, notify: true },
      headers: { "Idempotency-Key": "b1" },
    });
    const waitlist = await hit("GET", `${R}/waitlist`, `${R}/waitlist?from=2026-11-17&to=2026-12-17`);
    await hit("POST", `${R}/waitlist`, `${R}/waitlist`, { json: { name: "Irene Prueba", phone: null, party_size: 1, date: "2026-11-19", time: null, in_person: true }, headers: { "Idempotency-Key": "w2" } });
    const entry = list(obj(waitlist.body).items).map(obj)[0];
    await hit("POST", `${R}/waitlist/{entry_id}/offer`, `${R}/waitlist/${String(entry?.id)}/offer`);
    await hit("POST", `${R}/waitlist/{entry_id}/remove`, `${R}/waitlist/${String(entry?.id)}/remove`);
    const block = await hit("POST", `${R}/blocks`, `${R}/blocks`, { json: { date: "2026-11-19", from: "13:00", until: "14:00", label: "Formación del equipo" }, headers: { "Idempotency-Key": "bl1" } });
    await hit("POST", `${R}/blocks/{block_id}/remove`, `${R}/blocks/${String(obj(obj(block.body).block).id)}/remove`);

    expect(failures).toEqual([]);
    expect([...done].sort()).toEqual(demoRoutes.map((r) => `${r.method} ${r.path}`).sort());
  });
});

// ── through the app's own client ──────────────────────────────────────

describe("through openapi-fetch, as the app calls it", () => {
  const api = createClient<paths>({ baseUrl: BASE, fetch: demoFetch });

  it("signs in with any email and password, and refuses the two cases the screens have words for", async () => {
    const device = { platform: "ios" as const, display_name: "iPhone", install_id: "i1", app_version: "1.3.0", locale: "es" };
    const ok = await run(api.POST("/app/sign-in/password", { body: { email: "alguien@ejemplo.test", password: "x", ...device } }));
    expect(ok.response.status).toBe(201);
    expect(ok.data?.access_token).toBeTruthy();
    expect(ok.data?.expires_in).toBe(3600);

    const wrong = await run(api.POST("/app/sign-in/password", { body: { email: "camila@clinicabrisa.test", password: "error", ...device } }));
    expect(wrong.response.status).toBe(401);
    expect(wrong.error).toEqual({ code: "invalid_credentials" });

    const partner = await run(api.POST("/app/sign-in/password", { body: { email: "partner@agencia.test", password: "x", ...device } }));
    expect(partner.response.status).toBe(403);
    expect(partner.error).toEqual({ code: "not_a_client" });

    const renewed = await run(api.POST("/app/phones/refresh", { body: { refresh_token: ok.data?.refresh_token ?? "" } }));
    expect(renewed.data?.access_token).not.toBe(ok.data?.access_token);

    const config = await run(api.GET("/app/config"));
    expect(config.data?.sign_in.google).toBe(true);
  });

  it("reads typed bodies, empty answers and refusals the way the app unwraps them", async () => {
    const me = await run(api.GET("/console/lite/me"));
    expect(me.data?.client.name).toBe("Clínica Brisa");
    expect(me.data?.user).toEqual({ name: "Camila Rojas", email: "camila@clinicabrisa.test" });
    expect(me.data?.nav).toEqual(["panel", "inbox", "reservas", "usage"]);
    expect(me.data?.channels.map((c) => c.kind)).toEqual(["whatsapp", "instagram", "messenger"]);

    const read = await run(api.POST("/console/lite/inbox/conversations/{conversation_id}/read", { params: { path: { conversation_id: demoIds.lucia } } }));
    expect(read.response.status).toBe(204);
    expect(read.error).toBeUndefined();

    const deletion = await run(api.POST("/console/lite/account/deletion-request"));
    expect(deletion.response.status).toBe(202);
    expect(deletion.error).toBeUndefined();

    const send = await run(
      api.POST("/console/lite/inbox/conversations/{conversation_id}/messages", {
        params: { path: { conversation_id: demoIds.diego }, header: { "Idempotency-Key": "k" } },
        body: { text: "Hola" },
      }),
    );
    expect(send.response.status).toBe(409);
    expect(send.error).toEqual({ detail: { code: "not_assigned_to_you" } });
  });
});

// ── what the app does shows on the next read ─────────────────────────

describe("the example remembers what was done", () => {
  const C = (id: string) => `/console/lite/inbox/conversations/${id}`;
  const detail = async (id: string) => obj((await call("GET", C(id))).body) as unknown as S["ConversationDetailOut"];
  const thread = async (id: string) => list(obj((await call("GET", `${C(id)}/messages`)).body).items) as S["ThreadItemOut"][];
  const page = async (filter: string, q = "") =>
    obj((await call("GET", `/console/lite/inbox/conversations?filter=${filter}${q ? `&q=${encodeURIComponent(q)}` : ""}`)).body) as unknown as S["nexus_api__api__console__lite__inbox__ConversationPageOut"];
  const home = async () => obj((await call("GET", "/console/lite/home")).body) as unknown as S["LiteHomeOut"];

  it("starts as the design: Lucía waits 12 min with her reason, Sofía is yours, two unread, two resolved", async () => {
    const all = await page("all");
    expect(all.items).toHaveLength(11);
    expect((await page("resolved")).items.map((c) => c.contact.name).sort()).toEqual(["Elena Castro", "Pedro Alarcón"]);
    expect(all.counts).toEqual({ unread: 2, waiting: 1 });
    const lucia = all.items.find((c) => c.id === demoIds.lucia);
    expect(lucia?.state).toBe("waiting");
    expect(lucia?.waiting?.reason).toBe("Pide que le devuelvan la seña de 20 €. Ava no puede hacer devoluciones.");
    expect(lucia?.waiting_reason).toBe("escalated");
    expect(Date.now() - Date.parse(lucia?.waiting?.since ?? "")).toBeLessThan(13 * 60_000);
    const sofia = all.items.find((c) => c.id === demoIds.sofia);
    expect(sofia?.state).toBe("person");
    expect(sofia?.assignee).toEqual({ kind: "member", is_me: true, name: "Camila Rojas" });

    const d = await detail(demoIds.lucia);
    expect(d.waiting_reason).toBe("Pide que le devuelvan la seña de 20 €. Ava no puede hacer devoluciones.");
    expect(d.waiting_code).toBe("escalated");
    // Reservas' example has her next booking, and points back to her conversation.
    expect(d.contact.next_booking?.service_name).toBeTruthy();

    const h = await home();
    expect(h.attention).toEqual([{ kind: "waiting", count: 1 }]);
    expect(h.waiting).toEqual({ count: 1, first_conversation_id: demoIds.lucia });
  });

  it("has the cases a screen needs: an expired window, a failed send, an image, a comment on a post, tags and a note", async () => {
    const jorge = await detail(demoIds.jorge);
    expect(jorge.window.agent_open).toBe(false);
    expect(jorge.window.open).toBe(false);
    expect(Date.parse(jorge.window.closes_at ?? "")).toBeLessThan(Date.now());
    expect((await detail(demoIds.sofia)).window.open).toBe(true);

    const failed = (await thread(demoIds.andres)).find((i) => i.delivery === "failed");
    expect(failed?.failure_reason).toBeTruthy();
    expect((await thread(demoIds.lucia)).some((i) => i.media?.kind === "image")).toBe(true);

    const comment = (await thread(demoIds.marta)).find((i) => i.comment);
    const post = await call("GET", `${C(demoIds.marta)}/messages/${comment?.id}/post`);
    expect(obj(post.body).text).toContain("Blanqueamiento");
    const plain = (await thread(demoIds.marta)).find((i) => !i.comment);
    expect((await call("GET", `${C(demoIds.marta)}/messages/${plain?.id}/post`)).body).toBeNull();

    const diego = await detail(demoIds.diego);
    expect(diego.tags).toEqual(["Primera visita", "Ortodoncia"]);
    expect(diego.note.body).toBeTruthy();
  });

  it("taking over flips who answers, adds the moment, and Inicio and the counts follow", async () => {
    const taken = obj((await call("POST", `${C(demoIds.lucia)}/takeover`, { headers: { "If-Match": "1" } })).body) as unknown as S["ConversationDetailOut"];
    expect(taken.state).toBe("person");
    expect(taken.assignee?.is_me).toBe(true);
    expect(taken.control_version).toBe(2);
    expect(taken.activity.at(-1)?.kind).toBe("takeover");
    expect((await thread(demoIds.lucia)).at(-1)).toMatchObject({ type: "event", kind: "takeover" });
    expect((await call("GET", "/console/lite/inbox/counts")).body).toEqual({ unread: 2, waiting: 0 });
    expect((await home()).attention).toEqual([]);
    expect((await page("waiting")).items).toEqual([]);

    // A stale version is refused with the conversation as it is now.
    const stale = await call("POST", `${C(demoIds.lucia)}/release`, { headers: { "If-Match": "1" } });
    expect(stale.status).toBe(412);
    expect(obj(obj(obj(stale.body).detail).conversation).control_version).toBe(2);

    const back = obj((await call("POST", `${C(demoIds.lucia)}/release`, { headers: { "If-Match": "2" } })).body) as unknown as S["ConversationDetailOut"];
    expect(back.state).toBe("agent");
    expect(back.assignee).toBeNull();
    expect(back.activity.at(-1)?.kind).toBe("released");
  });

  it("sends only who answers and while the window is open; a message goes to the end of the thread", async () => {
    const sent = await call("POST", `${C(demoIds.sofia)}/messages`, { json: { text: "Sí, tráelo también." }, headers: { "Idempotency-Key": "s1" } });
    expect(sent.status).toBe(201);
    const last = (await thread(demoIds.sofia)).at(-1);
    expect(last).toMatchObject({ text: "Sí, tráelo también.", direction: "outbound", author: { kind: "member", is_me: true } });
    // The same key is the same message.
    const again = await call("POST", `${C(demoIds.sofia)}/messages`, { json: { text: "Sí, tráelo también." }, headers: { "Idempotency-Key": "s1" } });
    expect(obj(again.body).id).toBe(obj(sent.body).id);
    expect((await thread(demoIds.sofia)).filter((i) => i.text === "Sí, tráelo también.")).toHaveLength(1);
    const row = (await page("all")).items.find((c) => c.id === demoIds.sofia);
    expect(row?.last_message?.author.is_me).toBe(true);
    expect(row?.unread).toBe(false);

    expect((await call("POST", `${C(demoIds.diego)}/messages`, { json: { text: "Hola" } })).body).toEqual({ detail: { code: "not_assigned_to_you" } });
    await call("POST", `${C(demoIds.jorge)}/takeover`);
    expect((await call("POST", `${C(demoIds.jorge)}/messages`, { json: { text: "Hola" } })).body).toEqual({ detail: { code: "window_closed" } });

    const form = new FormData();
    form.append("file", new Blob(["x"], { type: "application/pdf" }), "presupuesto.pdf");
    expect((await call("POST", `${C(demoIds.sofia)}/attachments`, { form })).status).toBe(201);
    expect((await thread(demoIds.sofia)).at(-1)?.media).toEqual({ kind: "document", filename: "presupuesto.pdf", transcript: null });
  });

  it("resolves, reopens, reads, clears and archives", async () => {
    await call("POST", `${C(demoIds.diego)}/resolve`);
    expect((await page("all")).items.some((c) => c.id === demoIds.diego)).toBe(false);
    expect((await page("resolved")).items.some((c) => c.id === demoIds.diego)).toBe(true);
    const reopened = obj((await call("POST", `${C(demoIds.diego)}/reopen`)).body);
    expect(reopened.state).toBe("agent");

    await call("POST", `${C(demoIds.lucia)}/read`);
    expect((await call("GET", "/console/lite/inbox/counts")).body).toEqual({ unread: 1, waiting: 1 });
    await call("POST", `${C(demoIds.diego)}/unread`);
    expect((await page("unread")).items.map((c) => c.id).sort()).toEqual([demoIds.diego, demoIds.sofia].sort());

    await call("POST", `${C(demoIds.valentina)}/clear`);
    expect(await thread(demoIds.valentina)).toEqual([]);
    expect((await page("all")).items.find((c) => c.id === demoIds.valentina)?.last_message).toBeNull();

    expect((await call("POST", `${C(demoIds.laura)}/archive`)).status).toBe(204);
    expect((await call("GET", C(demoIds.laura))).status).toBe(404);
    expect((await page("all")).items.some((c) => c.id === demoIds.laura)).toBe(false);
    expect((await page("resolved")).items.some((c) => c.id === demoIds.laura)).toBe(false);

    await call("PUT", `${C(demoIds.diego)}/tags`, { json: { tags: [" VIP ", "vip", "Ortodoncia"] } });
    await call("PUT", `${C(demoIds.diego)}/note`, { json: { body: "Nota nueva" } });
    const d = await detail(demoIds.diego);
    expect(d.tags).toEqual(["VIP", "Ortodoncia"]);
    expect(d.note.body).toBe("Nota nueva");
    expect(d.note.updated_at).toBeTruthy();
  });

  it("searches by name, handle and text, like the API", async () => {
    expect((await page("all", "seña")).items.map((c) => c.id)).toEqual([demoIds.lucia]);
    expect((await page("all", "sena")).items.map((c) => c.id)).toEqual([demoIds.lucia]);
    expect((await page("all", "@sofi")).items.map((c) => c.id)).toEqual([demoIds.sofia]);
    expect((await page("all", "urgencia de sábado")).items).toEqual([]);
  });

  it("keeps a correction from draft to applied to undone, and refuses one with personal data", async () => {
    const answer = (await thread(demoIds.diego)).find((i) => i.author?.kind === "agent");
    const path = `/console/lite/inbox/${demoIds.diego}/messages/${answer?.id}/corrections`;
    const draft = obj((await call("POST", path, { json: { text: "La valoración dura 30 minutos.", scope: "business" } })).body);
    expect(draft).toMatchObject({ status: "draft", kind: "data", revision: 1, pii: [] });
    const sent = obj((await call("POST", `/console/lite/corrections/${String(draft.id)}/send`, { headers: { "If-Match": '"1"' } })).body);
    expect(sent.status).toBe("applied");
    const undone = obj((await call("POST", `/console/lite/corrections/${String(draft.id)}/undo`)).body);
    expect(undone.status).toBe("undone");

    const behaviour = obj((await call("POST", path, { json: { text: "Que sea más cercana y menos formal.", scope: "agent" } })).body);
    expect(behaviour.kind).toBe("behavior");
    expect(obj((await call("POST", `/console/lite/corrections/${String(behaviour.id)}/send`)).body).status).toBe("proposed");

    const personal = obj((await call("POST", path, { json: { text: "Que escriban a diego@correo.test", scope: "business" } })).body);
    expect(list(personal.pii).length).toBeGreaterThan(0);
    const refused = await call("POST", `/console/lite/corrections/${String(personal.id)}/send`);
    expect(refused.status).toBe(422);
    expect(obj(obj(refused.body).detail).code).toBe("pii_present");

    // An edit with a stale revision is refused with the current one.
    const conflict = await call("PATCH", `/console/lite/corrections/${String(personal.id)}`, { json: { lesson: "Que escriban por aquí" }, headers: { "If-Match": '"9"' } });
    expect(conflict.status).toBe(412);
    expect(obj(obj(conflict.body).detail).code).toBe("revision_conflict");
  });

  it("saves this phone's notices", async () => {
    await call("PUT", "/console/lite/phones/current/notices", { json: { kinds: ["inbox.waiting", "client.balance"], quiet_outside_hours: false } });
    expect((await call("GET", "/console/lite/phones/current/notices")).body).toEqual({ kinds: ["inbox.waiting", "client.balance"], quiet_outside_hours: false });
  });
});

// ── live events ───────────────────────────────────────────────────────

describe("the live line", () => {
  it("brings Nuria 3.2 s after it opens, once, and she is in the Bandeja when the event says so", async () => {
    const events: InboxEvent[] = [];
    const stop = demoEvents((e) => events.push(e));
    await jest.advanceTimersByTimeAsync(ARRIVAL_MS - 100);
    expect(events).toEqual([]);
    await jest.advanceTimersByTimeAsync(200);
    expect(events).toEqual([{ event: "message.new", conversation_id: demoIds.nuria }]);
    stop();

    const all = obj((await call("GET", "/console/lite/inbox/conversations?filter=all")).body) as unknown as S["nexus_api__api__console__lite__inbox__ConversationPageOut"];
    const nuria = all.items[0];
    expect(nuria?.contact.name).toBe("Nuria Campos");
    expect(nuria?.channel.kind).toBe("instagram");
    expect(nuria?.unread).toBe(true);
    expect(all.counts.unread).toBe(3);

    const again: InboxEvent[] = [];
    const stop2 = demoEvents((e) => again.push(e));
    await jest.advanceTimersByTimeAsync(ARRIVAL_MS * 2);
    stop2();
    expect(again).toEqual([]);
  });

  it("tells nothing once stopped", async () => {
    const events: InboxEvent[] = [];
    demoEvents((e) => events.push(e))();
    await jest.advanceTimersByTimeAsync(ARRIVAL_MS * 2);
    expect(events).toEqual([]);
  });
});

// ── money, unknown routes, made-up people ─────────────────────────────

describe("the rest", () => {
  it("says the design's figures in US$, and switches currency with EXPO_PUBLIC_DEMO_CURRENCY", async () => {
    const usd = obj((await call("GET", "/console/lite/usage/summary")).body) as unknown as S["LiteUsageSummaryOut"];
    expect(usd.balance).toMatchObject({ currency: "USD", remaining_cents: 2391, days_left: 120 });
    expect(usd.month).toMatchObject({ currency: "USD", spent_cents: 421, conversations: 8 });
    expect(usd.by_agent).toHaveLength(1);
    const spend = obj((await call("GET", "/console/lite/usage/spend?days=90")).body) as unknown as S["LiteSpendOut"];
    expect(spend.days).toHaveLength(90);
    expect(spend.series_cents.filter((c) => c > 0).length).toBeGreaterThan(2);
    expect(spend.month_cents).toBe(421);
    const home = obj((await call("GET", "/console/lite/home")).body) as unknown as S["LiteHomeOut"];
    expect(home.balance?.remaining_cents).toBe(2391);
    expect(home.spend_month?.total_cents).toBe(421);

    resetDemo();
    process.env.EXPO_PUBLIC_DEMO_CURRENCY = "EUR";
    const eur = obj((await call("GET", "/console/lite/usage/summary")).body) as unknown as S["LiteUsageSummaryOut"];
    expect(eur.balance?.currency).toBe("EUR");
    expect(eur.balance?.remaining_cents).toBe(2200);

    resetDemo();
    process.env.EXPO_PUBLIC_DEMO_CURRENCY = "CLP";
    const clp = obj((await call("GET", "/console/lite/usage/spend?days=90")).body) as unknown as S["LiteSpendOut"];
    expect(clp.currency).toBe("CLP");
    // No cents in pesos: every amount is whole.
    expect(clp.series_cents.every((c) => c % 100 === 0)).toBe(true);
    expect(clp.month_cents).toBeGreaterThan(100_000);
  });

  it("answers a route it does not know with a 404 and says so", async () => {
    const warn = jest.spyOn(console, "warn").mockImplementation(() => undefined);
    const r = await call("GET", "/console/lite/agents");
    expect(r.status).toBe(404);
    expect(r.body).toEqual({ detail: { code: "not_found" } });
    expect(warn).toHaveBeenCalledWith(expect.stringContaining("/console/lite/agents"));
    warn.mockRestore();
  });

  it("only has made-up people: +34 600 000 0xx numbers and .test emails", async () => {
    const all = [
      ...(obj((await call("GET", "/console/lite/inbox/conversations?filter=all")).body).items as S["ConversationItemOut"][]),
      ...(obj((await call("GET", "/console/lite/inbox/conversations?filter=resolved")).body).items as S["ConversationItemOut"][]),
    ];
    for (const c of all) {
      if (c.channel.kind === "whatsapp") expect(c.contact.handle).toMatch(/^\+34 600 000 0\d\d$/);
    }
    expect(obj(obj((await call("GET", "/console/lite/me")).body).user).email).toMatch(/\.test$/);
  });
});
