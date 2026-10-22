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
  | "reservas.waitlist_accepted";
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

const C = "/console/lite/inbox/conversations/{conversation_id}" as const;
const path = (id: string) => ({ path: { conversation_id: id } });

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
};

export type Endpoints = typeof endpoints;
