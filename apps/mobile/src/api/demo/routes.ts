import type { Me } from "../endpoints";
import type { components } from "../schema.gen";

import {
  AGENT,
  BALANCE_USD_CENTS,
  BUSINESS,
  CAP_USD_CENTS,
  CHANNELS,
  DAYS_LEFT,
  HOURS,
  HOURS_LABEL,
  MONTH_CONVERSATIONS,
  NAV,
  PHONE_ID,
  PREV_7D,
  REPLIES,
  TIMEZONE,
  USER,
  daysBefore,
  localDate,
  money,
  spendSeries,
  uuid,
  type Currency,
} from "./data";
import { DemoHttpError, ifMatch, refuse, refusePublic, route, type Route } from "./http";
import type { DetailOut, Filter } from "./inbox";
import { nextBookingOf } from "./reservas";
import { state } from "./state";

type S = components["schemas"];

/**
 * The example API's routes outside Reservas: the public `/app/*` ones (sign
 * in, renew, config), and `/console/lite/*` for who and what, Inicio, the
 * Bandeja, «Corregir», Consumo and this phone. Each body is the schema's
 * (`route` types it); the rules are the API's where a screen depends on them.
 */

// ── credentials ───────────────────────────────────────────────────────

function tokens(): S["TokensOut"] {
  const s = state();
  s.issued += 1;
  const n = String(s.issued).padStart(4, "0");
  return { phone_id: PHONE_ID, access_token: `demo-access-${n}`, refresh_token: `demo-refresh-${n}-not-a-real-secret`, expires_in: 3600 };
}

function missing(field: string): DemoHttpError {
  return new DemoHttpError(422, { detail: [{ loc: ["body", field], msg: "Field required", type: "missing" }] });
}

// ── money ─────────────────────────────────────────────────────────────

function spend(now: number, c: Currency): { days: string[]; cents: number[]; month: number; projection: number } {
  const series = spendSeries(now);
  const cents = series.usdCents.map((x) => money(x, c));
  const today = new Date(now);
  const prefix = localDate(now).slice(0, 7);
  const month = series.days.reduce((sum, d, i) => (d.startsWith(prefix) ? sum + (cents[i] ?? 0) : sum), 0);
  const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
  return { days: series.days, cents, month, projection: Math.round((month / today.getDate()) * daysInMonth) };
}

function balance(now: number, c: Currency): S["LiteBalanceOut"] {
  const today = new Date(now);
  const daysInMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0).getDate();
  return {
    assigned: true,
    currency: c,
    remaining_cents: money(BALANCE_USD_CENTS, c),
    cap_cents: money(CAP_USD_CENTS, c),
    days_left: DAYS_LEFT,
    month_days_left: daysInMonth - today.getDate(),
    runs_out_on: localDate(daysBefore(now, -DAYS_LEFT)),
  };
}

// ── the Bandeja ───────────────────────────────────────────────────────

const C = "/console/lite/inbox/conversations/{conversation_id}" as const;
const FILTERS: readonly Filter[] = ["all", "unread", "waiting", "resolved"];

/** The contact's next reservation rides on the detail, from Reservas' example (spec 044, R12). */
async function withBooking(d: DetailOut): Promise<DetailOut> {
  const next = await nextBookingOf(d.contact.name);
  return next ? { ...d, contact: { ...d.contact, next_booking: next } } : d;
}

type FormLike = {
  get?: (key: string) => unknown;
  getAll?: (key: string) => unknown[];
  /** React Native's `FormData`: no `get`, its parts instead. */
  getParts?: () => { fieldName?: string; name?: unknown; type?: unknown; uri?: unknown }[];
};

/** A file inside an upload's `FormData`: its name and type, when the runtime says them (Node's and React Native's differ). */
function fileOf(body: unknown): { name: string | null; type: string | null } {
  let f: unknown = null;
  try {
    const form = (body && typeof body === "object" ? body : {}) as FormLike;
    if (typeof form.get === "function") f = form.get("file");
    else if (typeof form.getAll === "function") f = form.getAll("file")[0];
    else if (typeof form.getParts === "function") f = form.getParts().find((p) => p.fieldName === "file");
  } catch {
    f = null;
  }
  const o = f && typeof f === "object" ? (f as { name?: unknown; type?: unknown; uri?: unknown }) : {};
  // An expo-file-system `File` may only say its `uri`: the name and the kind come from it.
  const fromUri = typeof o.uri === "string" ? (o.uri.split(/[/?#]/).filter(Boolean).pop() ?? null) : null;
  const name = typeof o.name === "string" && o.name ? o.name : fromUri;
  const type = typeof o.type === "string" && o.type ? o.type : name?.toLowerCase().endsWith(".pdf") ? "application/pdf" : null;
  return { name, type };
}

// ── «Corregir esta respuesta» (spec 047, requirement 52) ──────────────

const PII: { kind: S["PiiOut"]["kind"]; re: RegExp }[] = [
  { kind: "email", re: /[^\s@]+@[^\s@]+\.[^\s@]+/g },
  { kind: "phone", re: /\+?\d[\d ]{7,}\d/g },
];

function piiIn(field: S["PiiOut"]["field"], text: string, names: readonly string[]): S["PiiOut"][] {
  const out: S["PiiOut"][] = [];
  for (const { kind, re } of PII) {
    for (const m of text.matchAll(re)) out.push({ field, kind, start: m.index ?? 0, end: (m.index ?? 0) + m[0].length });
  }
  for (const name of names) {
    const at = text.indexOf(name);
    if (name && at >= 0) out.push({ field, kind: "name", start: at, end: at + name.length });
  }
  return out;
}

/** A fact (a price, an hour, a place) applies at once; anything else is a behaviour for the partner. */
function kindOf(text: string): S["CorrectionOut"]["kind"] {
  return /\d|€|\$|precio|cuesta|horario|abr[ei]|cierra|direcci|calle|dura/i.test(text) ? "data" : "behavior";
}

function correction(id: string): S["CorrectionOut"] {
  const c = state().corrections.get(id);
  if (!c) throw refuse(404, "unknown_correction");
  return c;
}

function checkRevision(c: S["CorrectionOut"], headers: Headers): void {
  const rev = ifMatch(headers);
  if (rev !== null && rev !== c.revision) throw refuse(412, "revision_conflict", { current: { ...c } });
}

// ── the routes ────────────────────────────────────────────────────────

export const appRoutes: Route[] = [
  // public
  route("get", "/app/config", 200, () => ({
    console_url: "https://console.auphere.com",
    min_version: { ios: null, android: null },
    reason: null,
    sign_in: { google: true },
  })),
  route("post", "/app/sign-in/password", 201, ({ json }) => {
    const email = (json?.email ?? "").trim().toLowerCase();
    const password = json?.password ?? "";
    if (!email) throw missing("email");
    if (!password) throw missing("password");
    // The two refusals the screens have words for (`sign-in.ts`, `outcomeOfError`).
    if (password === "error") throw refusePublic(401, "invalid_credentials");
    if (email.startsWith("partner@")) throw refusePublic(403, "not_a_client");
    return tokens();
  }),
  route("post", "/app/sign-in/google", 201, ({ json }) => {
    if (!json?.code) throw refusePublic(422, "invalid_grant");
    return tokens();
  }),
  route("post", "/app/password-reset", 202, (): S["PasswordResetOut"] => ({ status: "sent_if_known" })),
  route("post", "/app/phones/refresh", 200, ({ json }) => {
    if (!json?.refresh_token) throw refusePublic(401, "invalid_grant");
    return tokens();
  }),

  // who and what
  route(
    "get",
    "/console/lite/me",
    200,
    (): S["LiteMeOut"] & Me => ({
      user: { name: USER.name, email: USER.email },
      client: { name: BUSINESS, modules: [...NAV] },
      nav: [...NAV],
      agents: [{ id: AGENT.id, name: AGENT.name }],
      channels: CHANNELS.map((kind) => ({ kind, connected: true })),
      balance_contact: { kind: "auphere", name: "Auphere" },
      business: { timezone: TIMEZONE, hours: HOURS, hours_label: HOURS_LABEL },
      reservas: { mode: "services", capacity_kind: null },
    }),
  ),
  route("get", "/console/lite/home", 200, (): S["LiteHomeOut"] => {
    const s = state();
    const now = Date.now();
    const m = spend(now, s.currency);
    const { waiting } = s.inbox.counts();
    const daily = s.inbox.daily(now);
    return {
      attention: waiting > 0 ? [{ kind: "waiting", count: waiting }] : [],
      waiting: { count: waiting, first_conversation_id: s.inbox.firstWaiting() },
      balance: balance(now, s.currency),
      spend_month: { currency: s.currency, total_cents: m.month, by_agent: [{ agent_id: AGENT.id, name: AGENT.name, cents: m.month }] },
      conversations: { daily, last_7d: daily.reduce((a, d) => a + d.count, 0), prev_7d: PREV_7D },
      errors: [],
    };
  }),

  // Consumo
  route("get", "/console/lite/usage/summary", 200, () => {
    const s = state();
    const now = Date.now();
    const m = spend(now, s.currency);
    return {
      partner_name: "Auphere",
      bag_state: null,
      balance: balance(now, s.currency),
      days_left: DAYS_LEFT,
      month: {
        currency: s.currency,
        spent_cents: m.month,
        conversations: MONTH_CONVERSATIONS,
        avg_per_conversation_cents: Math.round(m.month / MONTH_CONVERSATIONS),
        projection_cents: m.projection,
      },
      by_agent: [{ agent_id: AGENT.id, name: AGENT.name, conversations: MONTH_CONVERSATIONS, share_pct: 100, spent_cents: m.month }],
      errors: [],
    };
  }),
  route("get", "/console/lite/usage/spend", 200, ({ query }) => {
    if (query.agent && query.agent !== AGENT.id) throw refuse(404, "unknown_agent");
    const s = state();
    const m = spend(Date.now(), s.currency);
    const days = Math.min(90, Math.max(1, Math.floor(Number(query.days)) || 30));
    return { currency: s.currency, days: m.days.slice(-days), series_cents: m.cents.slice(-days), month_cents: m.month, projected_cents: m.projection };
  }),

  // the Bandeja: reads
  route("get", "/console/lite/inbox/conversations", 200, ({ query }) => {
    const filter = FILTERS.find((f) => f === query.filter) ?? "all";
    const limit = Number(query.limit);
    return state().inbox.list({
      filter,
      ...(query.q ? { q: query.q } : {}),
      ...(query.channel ? { channel: query.channel } : {}),
      ...(query.agent ? { agent: query.agent } : {}),
      ...(query.cursor ? { cursor: query.cursor } : {}),
      ...(Number.isFinite(limit) && limit > 0 ? { limit } : {}),
    });
  }),
  route("get", "/console/lite/inbox/counts", 200, () => state().inbox.counts()),
  route("get", C, 200, ({ params }) => withBooking(state().inbox.detail(params.conversation_id, Date.now()))),
  route("get", `${C}/messages`, 200, ({ params, query }) => {
    const limit = Number(query.limit);
    return state().inbox.thread(params.conversation_id, Date.now(), query.before, Number.isFinite(limit) && limit > 0 ? limit : 100);
  }),
  route("get", `${C}/messages/{message_id}/post`, 200, ({ params }) => state().inbox.post(params.conversation_id, params.message_id)),
  route("get", "/console/lite/inbox/tags", 200, () => state().inbox.suggestedTags()),
  route("get", "/console/lite/inbox/replies", 200, () => REPLIES.map((r) => ({ ...r }))),

  // the Bandeja: writes
  route("post", `${C}/read`, 204, ({ params }) => {
    state().inbox.markRead(params.conversation_id, false);
    return null;
  }),
  route("post", `${C}/unread`, 204, ({ params }) => {
    state().inbox.markRead(params.conversation_id, true);
    return null;
  }),
  route("post", `${C}/takeover`, 200, ({ params, headers }) => withBooking(state().inbox.takeOver(params.conversation_id, ifMatch(headers), Date.now()))),
  route("post", `${C}/release`, 200, ({ params, headers }) => withBooking(state().inbox.giveBack(params.conversation_id, ifMatch(headers), Date.now()))),
  route("post", `${C}/resolve`, 200, ({ params }) => withBooking(state().inbox.resolve(params.conversation_id, Date.now()))),
  route("post", `${C}/reopen`, 200, ({ params }) => withBooking(state().inbox.reopen(params.conversation_id, Date.now()))),
  route("post", `${C}/clear`, 200, ({ params }) => withBooking(state().inbox.clear(params.conversation_id, Date.now()))),
  route("post", `${C}/archive`, 204, ({ params }) => {
    state().inbox.archive(params.conversation_id, Date.now());
    return null;
  }),
  route("post", `${C}/messages`, 201, ({ params, json, headers }) => {
    if (typeof json?.text !== "string") throw missing("text");
    return state().inbox.send(params.conversation_id, json.text, headers.get("Idempotency-Key"), Date.now()).sent;
  }),
  route("post", `${C}/attachments`, 201, ({ params, body, headers }) => state().inbox.attach(params.conversation_id, fileOf(body), headers.get("Idempotency-Key"), Date.now()).sent),
  route("put", `${C}/tags`, 200, ({ params, json }) => state().inbox.setTags(params.conversation_id, Array.isArray(json?.tags) ? json.tags.filter((t): t is string => typeof t === "string") : [])),
  route("put", `${C}/note`, 200, ({ params, json }) => state().inbox.setNote(params.conversation_id, typeof json?.body === "string" ? json.body : "", Date.now())),

  // «Corregir esta respuesta»
  route("post", "/console/lite/inbox/{conversation_id}/messages/{message_id}/corrections", 201, ({ params, json, headers }) => {
    const s = state();
    const key = headers.get("Idempotency-Key");
    const seen = key ? s.correctionKeys.get(key) : undefined;
    if (seen) return { ...correction(seen) };
    const text = (json?.text ?? "").trim();
    if (!text) throw missing("text");
    const scope = json?.scope === "agent" ? "agent" : "business";
    const reply = s.inbox.agentReply(params.conversation_id, params.message_id);
    const names = [reply.contact, reply.contact.split(" ")[0] ?? ""];
    const paraphrase = reply.asked ? `Pregunta: «${reply.asked}»`.slice(0, 300) : null;
    const id = uuid("d", s.corrections.size + 1);
    const out: S["CorrectionOut"] = {
      id,
      agent: { id: AGENT.id, name: AGENT.name },
      kind: kindOf(text),
      scope,
      lesson: text,
      paraphrase,
      pii: [...piiIn("lesson", text, names), ...(paraphrase ? piiIn("paraphrase", paraphrase, names) : [])],
      revision: 1,
      status: "draft",
      created_at: new Date().toISOString(),
      sent_at: null,
      undone_at: null,
      applied_change_id: null,
      proposal_id: null,
    };
    s.corrections.set(id, out);
    s.correctionNames.set(id, names);
    if (key) s.correctionKeys.set(key, id);
    return { ...out };
  }),
  route("patch", "/console/lite/corrections/{correction_id}", 200, ({ params, json, headers }) => {
    const c = correction(params.correction_id);
    checkRevision(c, headers);
    if (c.status !== "draft") throw refuse(409, "not_a_draft");
    const lesson = typeof json?.lesson === "string" ? json.lesson : c.lesson;
    const paraphrase = typeof json?.paraphrase === "string" ? json.paraphrase : c.paraphrase;
    const names = state().correctionNames.get(c.id) ?? [];
    const next: S["CorrectionOut"] = {
      ...c,
      lesson,
      paraphrase,
      kind: kindOf(lesson),
      revision: c.revision + 1,
      pii: [...piiIn("lesson", lesson, names), ...(paraphrase ? piiIn("paraphrase", paraphrase, names) : [])],
    };
    state().corrections.set(c.id, next);
    return { ...next };
  }),
  route("post", "/console/lite/corrections/{correction_id}/send", 200, ({ params, headers }) => {
    const c = correction(params.correction_id);
    if (c.status !== "draft") return { ...c };
    checkRevision(c, headers);
    // Personal data saves nothing (52.5): the sheet lists what to take out.
    if (c.pii.length > 0) throw refuse(422, "pii_present", { pii: c.pii });
    const data = c.kind === "data";
    const next: S["CorrectionOut"] = {
      ...c,
      status: data ? "applied" : "proposed",
      sent_at: new Date().toISOString(),
      applied_change_id: data ? uuid("9", state().corrections.size) : null,
      proposal_id: data ? null : uuid("8", state().corrections.size),
    };
    state().corrections.set(c.id, next);
    return { ...next };
  }),
  route("post", "/console/lite/corrections/{correction_id}/undo", 200, ({ params }) => {
    const c = correction(params.correction_id);
    if (c.status === "undone") return { ...c };
    if (c.status !== "applied") throw refuse(409, "not_undoable");
    const next: S["CorrectionOut"] = { ...c, status: "undone", undone_at: new Date().toISOString() };
    state().corrections.set(c.id, next);
    return { ...next };
  }),

  // this phone
  route("delete", "/console/lite/phones/current", 204, () => null),
  route("put", "/console/lite/phones/current/push", 204, () => null),
  route("get", "/console/lite/phones/current/notices", 200, () => {
    const n = state().notices;
    return { kinds: [...n.kinds], quiet_outside_hours: n.quiet_outside_hours };
  }),
  route("put", "/console/lite/phones/current/notices", 200, ({ json }) => {
    const s = state();
    const kinds = Array.isArray(json?.kinds) ? json.kinds.filter((k): k is string => typeof k === "string") : s.notices.kinds;
    const quiet = typeof json?.quiet_outside_hours === "boolean" ? json.quiet_outside_hours : s.notices.quiet_outside_hours;
    s.notices = { kinds: [...new Set(kinds)], quiet_outside_hours: quiet };
    return { kinds: [...s.notices.kinds], quiet_outside_hours: s.notices.quiet_outside_hours };
  }),
  route("post", "/console/lite/account/deletion-request", 202, () => null),
  // Spec 069 (R17.2): the inbox's inactivity close, set from Ajustes. Lives in this module's memory.
  route("get", "/console/lite/inbox/settings", 200, (): S["InboxSettingsOut"] => ({ autoclose_hours: inboxSettings.autoclose_hours })),
  route("patch", "/console/lite/inbox/settings", 200, ({ json }): S["InboxSettingsOut"] => {
    const hours = json?.autoclose_hours;
    inboxSettings.autoclose_hours = typeof hours === "number" ? hours : null;
    return { autoclose_hours: inboxSettings.autoclose_hours };
  }),
];

/** The example business closes a quiet conversation after 72 h (spec 064 R5's default in the web). */
const inboxSettings: { autoclose_hours: number | null } = { autoclose_hours: 72 };
