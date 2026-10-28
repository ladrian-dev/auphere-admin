import { api, call, publicApi, upload } from "./client";
import { errorOf } from "./errors";
import type { components } from "./schema.gen";

/**
 * Every call the app makes, typed from the API's own OpenAPI (D14). Screens
 * and hooks use these, never `fetch`. Where the API types a field loosely
 * (`agent`, `channel` are plain dicts in the schema) the view type narrows it
 * to what the console already reads (`apps/console/src/lib/backend/inbox.ts`).
 */
type S = components["schemas"];

/** `/me` with what specs 043 (§1 `reservas`) and 045 (§4 `business`) add, optional until `openapi.json` has them. */
export type Business = { timezone: string; hours: Record<string, { from: string; to: string }[]> | null; hours_label: string | null };
export type Me = S["LiteMeOut"] & {
  reservas?: { mode: "services" | "capacity"; capacity_kind: string | null } | null;
  business?: Business | null;
};
export type AppConfig = S["AppConfigOut"];
export type Tokens = S["TokensOut"];
export type Home = S["LiteHomeOut"];
export type UsageSummary = S["LiteUsageSummaryOut"];
export type Spend = S["LiteSpendOut"];
export type Counts = S["CountsOut"];
export type Author = S["AuthorOut"];
/** Spec 044 (R14.2) with the names of the frozen contract (043 §1): the three of Reservas, only with the module. */
export type NoticeKind =
  | "inbox.waiting"
  | "inbox.message_for_you"
  | "client.balance"
  | "reservas.agent_change"
  | "reservas.cancelled_today"
  | "reservas.waitlist_accepted"
  /** Spec 047 (T170): an agent's cap, its pauses and its numbers' pauses and problems — «Agentes y números». */
  | "agents.state";
/** `GET /phones/current/notices`, with the quiet hours of spec 045 §5 when the API has them (R14.3). */
export type Notices = { kinds: string[]; quiet_outside_hours?: boolean };
export type InboxFilter = "all" | "unread" | "waiting" | "resolved";
export type InboxState = "agent" | "waiting" | "person" | "resolved";

type Named = { id: string; name: string };

/**
 * What specs 045 (§2) and 043 (§1) add, and the app reads when they are there
 * (spec 044, R10–R12): why and since when a conversation waits, and the
 * contact's next reservation. Optional until `openapi.json` carries them.
 */
export type NextBooking = {
  id: string;
  starts_at: string;
  local: { date: string; start: string; end: string };
  status: string;
  service_name: string | null;
  party_size: number | null;
};

export type Conversation = Omit<S["ConversationItemOut"], "agent" | "channel"> & {
  agent: Named | null;
  channel: { kind: string };
  waiting?: { reason: string | null; since: string } | null;
};
/** Spec 047 (50.7): who takes it (`handled_by_agent`) and, while it waits, the code of why (`events.md` §2). */
export type HandledBy = S["AgentRefOut"];
export type ConversationPage = Omit<S["nexus_api__api__console__lite__inbox__ConversationPageOut"], "items"> & {
  items: Conversation[];
};
export type Detail = Omit<S["ConversationDetailOut"], "agent" | "channel" | "contact"> & {
  agent: Named | null;
  channel: { kind: string; connected: boolean };
  waiting_since?: string | null;
  contact: S["ConversationDetailOut"]["contact"] & { next_booking?: NextBooking | null };
};
export type ThreadItem = S["ThreadItemOut"];
export type Thread = S["nexus_api__api__console__lite__inbox__ThreadOut"];
export type Sent = S["SentOut"];
export type SavedReply = S["ReplyOut"];

// ── spec 047: the agents, the business and the corrections (contracts/lite-app-api.md) ──
/** The same `visible_state` as the partner's console (25.5): a code, a tone and, paused, its reason. */
export type VisibleState = S["VisibleOut"];
export type AgentChannel = S["LiteAgentChannelOut"];
export type AgentCard = S["LiteAgentCardOut"];
export type BusinessSections = S["LiteBusinessSectionsOut"];
export type Hours = S["HoursOut"];
export type Day = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";
export type Shift = { open: string; close: string };
export type SpecialDates = S["SpecialDatesOut"];
export type SpecialDate = S["SpecialDateOut"];
export type SpecialDateBody = { name?: string | null; from: string; to: string; closed: boolean; shifts?: Shift[] };
export type Services = S["ServicesOut"];
export type Service = Services["items"][number];
/** `PriceOut` is typed loosely in the schema; this is the ClientSpec's shape it carries. */
export type Price = { kind: "none" | "free" } | { kind: "amount"; amount_minor: number };
export type ServiceBody = { name: string; description?: string | null; bookable: boolean; duration_min?: number | null; price: S["nexus_api__api__console__schemas_business_sections__PriceIn"] };
export type ServicePatch = Partial<Omit<ServiceBody, "name">>;
export type Locations = S["LocationsOut"];
export type Location = S["LocationOut"];
export type LocationBody = { name: string; address?: string | null; phone_e164?: string | null };
export type BusinessChange = S["LiteChangeOut"];
export type Provenance = S["LiteProvenanceOut"];
export type Correction = S["CorrectionOut"];
export type CorrectionScope = Correction["scope"];
/** The four sections the business edits from here (50.1), by the name the history uses. */
export type Section = "hours" | "special_dates" | "services" | "locations";

const C = "/console/lite/inbox/conversations/{conversation_id}" as const;
const path = (id: string) => ({ path: { conversation_id: id } });

/**
 * A write to the business carries the section's revision (`If-Match`, a 412
 * with what changed when someone wrote first) and its own key, so a retry of
 * the same intent is the same write (contracts/lite-app-api.md).
 */
const ifMatch = (revision: number) => ({ "If-Match": `"${revision}"` });
const keyed = (key: string) => ({ headers: { "Idempotency-Key": key } });

export const endpoints = {
  // ── public (no credential) ──────────────────────────────────────────
  config: () => call(publicApi.GET("/app/config")),
  signInWithPassword: (body: S["PasswordSignInIn"]) => call(publicApi.POST("/app/sign-in/password", { body })),
  signInWithGoogle: (body: S["GoogleRedeemIn"]) => call(publicApi.POST("/app/sign-in/google", { body })),
  passwordReset: (email: string) => call(publicApi.POST("/app/password-reset", { body: { email } })),

  // ── who and what ────────────────────────────────────────────────────
  me: () => call(api.GET("/console/lite/me")) as Promise<Me>,
  home: () => call(api.GET("/console/lite/home")),
  usageSummary: () => call(api.GET("/console/lite/usage/summary")),
  usageSpend: (days: number, agent?: string | null) =>
    call(api.GET("/console/lite/usage/spend", { params: { query: { days, ...(agent ? { agent } : {}) } } })),

  // ── the Bandeja ─────────────────────────────────────────────────────
  conversations: (q: { filter: InboxFilter; q?: string; agent?: string | null; cursor?: string | null }) =>
    call(
      api.GET("/console/lite/inbox/conversations", {
        params: {
          query: {
            filter: q.filter,
            ...(q.q ? { q: q.q } : {}),
            ...(q.agent ? { agent: q.agent } : {}),
            ...(q.cursor ? { cursor: q.cursor } : {}),
          },
        },
      }),
    ) as Promise<ConversationPage>,
  counts: () => call(api.GET("/console/lite/inbox/counts")),
  conversation: (id: string) => call(api.GET(C, { params: path(id) })) as Promise<Detail>,
  thread: (id: string, before?: string | null) =>
    call(
      api.GET(`${C}/messages`, { params: { ...path(id), query: before ? { before } : {} } }),
    ) as Promise<Thread>,
  markRead: (id: string) => call(api.POST(`${C}/read`, { params: path(id) })),
  markUnread: (id: string) => call(api.POST(`${C}/unread`, { params: path(id) })),
  takeOver: (id: string, version: number) =>
    call(api.POST(`${C}/takeover`, { params: { ...path(id), header: { "If-Match": String(version) } } })) as Promise<Detail>,
  giveBack: (id: string, version: number) =>
    call(api.POST(`${C}/release`, { params: { ...path(id), header: { "If-Match": String(version) } } })) as Promise<Detail>,
  resolve: (id: string) => call(api.POST(`${C}/resolve`, { params: path(id) })) as Promise<Detail>,
  reopen: (id: string) => call(api.POST(`${C}/reopen`, { params: path(id) })) as Promise<Detail>,
  send: (id: string, text: string, idempotencyKey: string) =>
    call(
      api.POST(`${C}/messages`, {
        params: { ...path(id), header: { "Idempotency-Key": idempotencyKey } },
        body: { text },
      }),
    ),
  setTags: (id: string, tags: string[]) => call(api.PUT(`${C}/tags`, { params: path(id), body: { tags } })),
  setNote: (id: string, body: string) => call(api.PUT(`${C}/note`, { params: path(id), body: { body } })),
  suggestedTags: () => call(api.GET("/console/lite/inbox/tags")),
  replies: () => call(api.GET("/console/lite/inbox/replies")),

  /** R6.3: an image or a PDF, same rules as the web. `file` is an expo-file-system `File`. */
  attach: async (id: string, file: Blob, idempotencyKey: string) => {
    const res = await upload(
      `/console/lite/inbox/conversations/${encodeURIComponent(id)}/attachments`,
      () => {
        const form = new FormData();
        form.append("file", file);
        return form;
      },
      { "Idempotency-Key": idempotencyKey },
    );
    if (!res.ok) throw errorOf(res.status, await res.json().catch(() => null));
    return (await res.json()) as Sent;
  },

  // ── this phone (R7, R10, R11) ───────────────────────────────────────
  signOut: () => call(api.DELETE("/console/lite/phones/current")),
  registerPush: (body: S["PushIn"]) => call(api.PUT("/console/lite/phones/current/push", { body })),
  notices: () => call(api.GET("/console/lite/phones/current/notices")) as Promise<Notices>,
  /** `quiet_outside_hours` goes only when the API has it (spec 045); today's schema knows `kinds`. */
  setNotices: (kinds: NoticeKind[], quiet?: boolean) =>
    call(
      api.PUT("/console/lite/phones/current/notices", {
        body: (quiet === undefined ? { kinds } : { kinds, quiet_outside_hours: quiet }) as { kinds: NoticeKind[] },
      }),
    ) as Promise<Notices>,
  requestDeletion: () => call(api.POST("/console/lite/account/deletion-request")),

  // ── agents (spec 047, 50.1, 50.2, 27.6) ─────────────────────────────
  agents: () => call(api.GET("/console/lite/agents")),
  /** Without `confirm`, an agent with conversations in progress answers 409 `confirm_required` with how many (27.8). */
  pauseAgent: (id: string, confirm = false) =>
    call(api.POST("/console/lite/agents/{agent_id}/pause", { params: { path: { agent_id: id } }, body: { confirm } })),
  resumeAgent: (id: string) => call(api.POST("/console/lite/agents/{agent_id}/resume", { params: { path: { agent_id: id } } })),
  pauseChannel: (id: string) => call(api.POST("/console/lite/channels/{channel_id}/pause", { params: { path: { channel_id: id } } })),
  resumeChannel: (id: string) => call(api.POST("/console/lite/channels/{channel_id}/resume", { params: { path: { channel_id: id } } })),

  // ── the business (spec 047, 50.1, 50.4; requirements 9–11 and 13) ───
  business: () => call(api.GET("/console/lite/business")),
  /** Returns the hours as they are now, with «Así lo dirá el agente» (`label`). */
  putHours: (days: Partial<Record<Day, Shift[]>>, layout: "blocks" | "daily", revision: number, key: string) =>
    call(api.PUT("/console/lite/business/hours", { params: { header: ifMatch(revision) }, body: { days, layout, clear: false, inherit: false, confirm_loss: false }, ...keyed(key) })),
  /** A location's own week, or the business's it inherits (`inherits`). Its revision is the Sedes one. */
  locationHours: (locationId: string) => call(api.GET("/console/lite/business/hours", { params: { query: { location_id: locationId } } })),
  /** A location's week of its own, or `inherit` to use the business's again; with the Sedes revision. */
  putLocationHours: (locationId: string, week: { days: Partial<Record<Day, Shift[]>>; layout: "blocks" | "daily" } | { inherit: true }, revision: number, key: string) =>
    call(
      api.PUT("/console/lite/business/hours", {
        params: { query: { location_id: locationId }, header: ifMatch(revision) },
        body: "inherit" in week ? { inherit: true, layout: "daily", clear: false, confirm_loss: false } : { ...week, clear: false, inherit: false, confirm_loss: false },
        ...keyed(key),
      }),
    ),
  addSpecialDate: (body: SpecialDateBody, revision: number, key: string) =>
    call(api.POST("/console/lite/business/special-dates", { params: { header: ifMatch(revision) }, body, ...keyed(key) })),
  editSpecialDate: (id: string, body: Partial<SpecialDateBody>, revision: number, key: string) =>
    call(
      api.PATCH("/console/lite/business/special-dates/{special_id}", {
        params: { path: { special_id: id }, header: ifMatch(revision) },
        body,
        ...keyed(key),
      }),
    ),
  archiveSpecialDate: (id: string, revision: number, key: string) =>
    call(
      api.POST("/console/lite/business/special-dates/{special_id}/archive", {
        params: { path: { special_id: id }, header: ifMatch(revision) },
        ...keyed(key),
      }),
    ),
  addService: (body: ServiceBody, revision: number, key: string) =>
    call(api.POST("/console/lite/business/services", { params: { header: ifMatch(revision) }, body, ...keyed(key) })),
  editService: (id: string, body: ServicePatch, revision: number, key: string) =>
    call(
      api.PATCH("/console/lite/business/services/{service_id}", {
        params: { path: { service_id: id }, header: ifMatch(revision) },
        body,
        ...keyed(key),
      }),
    ),
  archiveService: (id: string, revision: number, key: string) =>
    call(
      api.POST("/console/lite/business/services/{service_id}/archive", {
        params: { path: { service_id: id }, header: ifMatch(revision) },
        ...keyed(key),
      }),
    ),
  addLocation: (body: LocationBody, revision: number, key: string) =>
    call(api.POST("/console/lite/business/locations", { params: { header: ifMatch(revision) }, body, ...keyed(key) })),
  editLocation: (id: string, body: Partial<LocationBody>, revision: number, key: string) =>
    call(
      api.PATCH("/console/lite/business/locations/{location_id}", {
        params: { path: { location_id: id }, header: ifMatch(revision) },
        body,
        ...keyed(key),
      }),
    ),
  archiveLocation: (id: string, revision: number, key: string) =>
    call(
      api.POST("/console/lite/business/locations/{location_id}/archive", {
        params: { path: { location_id: id }, header: ifMatch(revision) },
        ...keyed(key),
      }),
    ),
  restoreLocation: (id: string, revision: number, key: string) =>
    call(
      api.POST("/console/lite/business/locations/{location_id}/restore", {
        params: { path: { location_id: id }, header: ifMatch(revision) },
        ...keyed(key),
      }),
    ),
  /** Undo a change of the history (13.3): a 412 when someone wrote after it, nobody overwrites anybody (13.4). */
  undoChange: (changeId: string, key: string) =>
    call(api.POST("/console/lite/business/history/{change_id}/undo", { params: { path: { change_id: changeId } }, ...keyed(key) })),

  // ── «Corregir esta respuesta» (spec 047, requirement 52) ────────────
  /** The draft: its kind (data or behaviour), the proposed paraphrase and where personal data is (`pii`). Nothing applied yet. */
  draftCorrection: (conversationId: string, messageId: string, body: { text: string; scope: CorrectionScope }, key: string) =>
    call(
      api.POST("/console/lite/inbox/{conversation_id}/messages/{message_id}/corrections", {
        params: { path: { conversation_id: conversationId, message_id: messageId }, header: { "Idempotency-Key": key } },
        body,
      }),
    ),
  editCorrection: (id: string, body: { lesson?: string; paraphrase?: string }, revision: number) =>
    call(api.PATCH("/console/lite/corrections/{correction_id}", { params: { path: { correction_id: id }, header: ifMatch(revision) }, body })),
  /** Data applies at once; behaviour reaches the partner as a proposal. `pii_present` (422) saves nothing (52.5). */
  sendCorrection: (id: string, revision: number, key: string) =>
    call(api.POST("/console/lite/corrections/{correction_id}/send", { params: { path: { correction_id: id }, header: ifMatch(revision) }, ...keyed(key) })),
  undoCorrection: (id: string, key: string) =>
    call(api.POST("/console/lite/corrections/{correction_id}/undo", { params: { path: { correction_id: id } }, ...keyed(key) })),
};

export type Endpoints = typeof endpoints;
