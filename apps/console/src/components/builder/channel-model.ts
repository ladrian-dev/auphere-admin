import { agentHref } from "@/components/shell/routes-v2";
import type { MessageKey } from "@/i18n/messages";
import type {
  ChannelAction,
  ChannelChange,
  ChannelCheck,
  ChannelConfigIn,
  ChannelPage,
  ChannelVisibleState,
  OwnerLinkMode,
  Recipient,
} from "@/lib/backend/channel-config-types";

/**
 * Spec 047 (historias 10 y 11; T111, T112, T114 y T115) — los canales de un
 * agente sin pintar nada: el texto de su estado visible (`events.md` §1.2, el
 * mismo en toda la consola), lo que ofrece su ⋯ (solo lo permitido, §V), el
 * borrador de su configuración con los números en formato internacional y sin
 * duplicados (32.4), las palabras de cada error de la API y del historial.
 */

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

// ── el estado visible ───────────────────────────────────────────────────────

const STATES = new Set(["pending_link", "disconnected", "problem", "paused", "unconfigured", "team_only", "everyone"]);
const PROBLEMS = new Set(["quality", "auth_expired", "coexistence_inactive", "meta_error", "account_review", "account_alert"]);

/** «Solo mi equipo», «Con problemas · calidad baja»… El texto lo pone la consola, el estado la API. */
export function channelStateText(t: T, state: ChannelVisibleState): string {
  if (state.code === "problem") {
    const reason = state.reason && PROBLEMS.has(state.reason) ? state.reason : "unknown";
    return t("builder.channel.state.problem", { reason: t(`builder.channel.problem.${reason}` as MessageKey) });
  }
  return STATES.has(state.code) ? t(`builder.channel.state.${state.code}` as MessageKey) : state.code;
}

/** Estados de un número que ya tiene decidido a quién responde (el paso «¡Listo!» del asistente, §7.1). */
const CONFIGURED = new Set(["team_only", "everyone", "paused", "problem"]);
export function isConfiguredState(state: ChannelVisibleState): boolean {
  return CONFIGURED.has(state.code);
}

/**
 * La línea de cada número en la lista de la pestaña Canales (`agente.md` §7.2):
 * «WhatsApp · responde solo a 1 número de prueba · escala a Marta». Sin su
 * página, solo el canal.
 */
export function channelSummary(t: T, type: string, page: Pick<ChannelPage, "config"> | null): string {
  const kinds: Record<string, string> = { whatsapp: t("builder.channels.whatsapp"), instagram: "Instagram", messenger: "Messenger" };
  const parts = [kinds[type] ?? type];
  if (!page) return parts[0]!;
  const { audience, escalation } = page.config;
  if (audience.mode === "team_only") {
    const n = audience.test_numbers.length;
    parts.push(n === 1 ? t("channels.proto.row.team.one") : t("channels.proto.row.team.other", { n }));
  } else if (audience.mode === "everyone") {
    const n = audience.exceptions.length;
    parts.push(n === 0 ? t("channels.proto.row.everyone") : n === 1 ? t("channels.proto.row.everyone.one") : t("channels.proto.row.everyone.other", { n }));
  } else {
    parts.push(t("channels.proto.row.unset"));
  }
  const names = escalation.recipients.map((r) => r.name.trim()).filter(Boolean);
  if (names.length) parts.push(t("channels.proto.row.escalates", { names: names.join(", ") }));
  return parts.join(" · ");
}

// ── las rutas ───────────────────────────────────────────────────────────────

/** La página de un canal cuelga de su agente (las migas ya lo esperan así). */
export function channelHref(refId: string, agentId: string, channelId: string): string {
  return `${agentHref(refId, agentId)}/channels/${encodeURIComponent(channelId)}`;
}

/** La sección Canales en la pantalla del agente. */
export function agentChannelsHref(refId: string, agentId: string): string {
  return `${agentHref(refId, agentId)}#agente-canales`;
}

// ── el ⋯ (34.1) ─────────────────────────────────────────────────────────────

export const CHANNEL_MENU_ORDER = ["configure", "move", "pause", "resume", "disconnect"] as const satisfies readonly ChannelAction[];
export function channelMenuItems(allowed: readonly string[], { here = false }: { here?: boolean } = {}): ChannelAction[] {
  // En su propia página, «Configuración» no lleva a ninguna parte.
  return CHANNEL_MENU_ORDER.filter((a) => allowed.includes(a) && !(here && a === "configure"));
}

// ── los números (32.4) ──────────────────────────────────────────────────────

/** En E.164 o `null`. Admite espacios, guiones, puntos, paréntesis y `00` delante. */
export function normalizeNumber(raw: string): string | null {
  let clean = raw.trim().replace(/[\s().-]/g, "");
  if (clean.startsWith("00")) clean = `+${clean.slice(2)}`;
  return /^\+[1-9]\d{6,14}$/.test(clean) ? clean : null;
}

export type AddResult = { ok: true; list: string[] } | { ok: false; error: "invalid" | "duplicate" };

/** Añadir un número a una lista: normalizado y sin repetir. */
export function addNumber(list: readonly string[], raw: string): AddResult {
  const e164 = normalizeNumber(raw);
  if (!e164) return { ok: false, error: "invalid" };
  if (list.includes(e164)) return { ok: false, error: "duplicate" };
  return { ok: true, list: [...list, e164] };
}

// ── el borrador de la configuración ─────────────────────────────────────────

export const MAX_RECIPIENTS = 10;
export const WAIT_MESSAGE_MAX = 500;

/** Lo que se edita: la configuración de la página sin `notify_from`, que es de solo lectura. */
export function draftFromPage(page: Pick<ChannelPage, "config">): ChannelConfigIn {
  const { audience, escalation, wait_message } = page.config;
  return {
    audience: { mode: audience.mode, test_numbers: [...audience.test_numbers], exceptions: [...audience.exceptions] },
    escalation: { recipients: escalation.recipients.map((r) => ({ ...r })), summary: escalation.summary },
    wait_message: wait_message ?? null,
  };
}

/** Lo que se manda: cada destinatario solo con el dato de su vía, el mensaje sin espacios de sobra. */
export function toPayload(draft: ChannelConfigIn): ChannelConfigIn {
  return {
    audience: { ...draft.audience },
    escalation: {
      summary: draft.escalation.summary,
      recipients: draft.escalation.recipients.map((r) => {
        const name = r.name.trim();
        if (r.via === "whatsapp") return { name, via: "whatsapp", phone_e164: normalizeNumber(r.phone_e164 ?? "") ?? (r.phone_e164 ?? "").trim() };
        if (r.via === "email") return { name, via: "email", email: (r.email ?? "").trim() };
        return { name, via: "inbox", client_user_id: r.client_user_id ?? null };
      }),
    },
    wait_message: draft.wait_message?.trim() ? draft.wait_message.trim() : null,
  };
}

/** ¿Hay algo sin guardar? */
export function isDirty(draft: ChannelConfigIn, saved: ChannelConfigIn): boolean {
  return JSON.stringify(toPayload(draft)) !== JSON.stringify(toPayload(saved));
}

/** Lo que la pantalla puede decir antes de mandar, en el orden en que se lee. */
export function draftProblem(t: T, draft: ChannelConfigIn): { section: "audience" | "escalation" | "wait"; text: string } | null {
  if (draft.audience.mode === "team_only" && draft.audience.test_numbers.length === 0) {
    return { section: "audience", text: t("builder.channel.tests.required") };
  }
  if (draft.escalation.recipients.length > MAX_RECIPIENTS) return { section: "escalation", text: t("builder.channel.recipients.max") };
  for (const r of draft.escalation.recipients) {
    const name = r.name.trim();
    if (!name) return { section: "escalation", text: t("builder.channel.recipient.nameRequired") };
    if (r.via === "whatsapp" && !normalizeNumber(r.phone_e164 ?? "")) {
      return (r.phone_e164 ?? "").trim()
        ? { section: "escalation", text: t("builder.channel.number.invalid", { value: (r.phone_e164 ?? "").trim() }) }
        : { section: "escalation", text: t("builder.channel.recipient.phoneRequired", { name }) };
    }
    if (r.via === "email" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test((r.email ?? "").trim())) {
      return { section: "escalation", text: t("builder.channel.recipient.emailInvalid", { name }) };
    }
  }
  if ((draft.wait_message ?? "").trim().length > WAIT_MESSAGE_MAX) return { section: "wait", text: t("builder.channel.wait.tooLong") };
  return null;
}

export function emptyRecipient(): Recipient {
  return { name: "", via: "whatsapp", phone_e164: "", email: null, client_user_id: null };
}

// ── los errores de la API al guardar (contracts/console-api.md §9) ──────────

type Failure = { status: number; code?: string | null; info?: Record<string, unknown> };

/** Dónde lleva un arreglo, si la persona puede hacerlo; `null` si solo se dice. */
export type FixTargets = { agent: string | null; tests: string | null; balance: string | null; recipients: string };

export type SaveError = { section: "audience" | "escalation" | "wait" | "general"; text: string; fix: string | null };

export function saveErrorOf(t: T, res: Failure): SaveError {
  const info = res.info ?? {};
  const fix = typeof info.fix === "string" ? info.fix : null;
  switch (res.code) {
    case "channel_test_numbers_required":
      return { section: "audience", text: t("builder.channel.tests.required"), fix: null };
    case "invalid_phone":
      return { section: "general", text: t("builder.channel.number.invalid", { value: String(info.value ?? "") }), fix: null };
    case "too_many_recipients":
      return { section: "escalation", text: t("builder.channel.recipients.max"), fix: null };
    case "too_many_numbers":
      return { section: "audience", text: t("builder.channel.error.too_many_numbers", { limit: Number(info.limit ?? 200) }), fix: null };
    case "recipient_name_required":
      return { section: "escalation", text: t("builder.channel.recipient.nameRequired"), fix: null };
    case "recipient_phone_required":
      return { section: "escalation", text: t("builder.channel.recipient.phoneRequired", { name: String(info.name ?? "") }), fix: null };
    case "recipient_email_invalid":
      return { section: "escalation", text: t("builder.channel.recipient.emailInvalid", { name: String(info.name ?? "") }), fix: null };
    case "wait_message_too_long":
      return { section: "wait", text: t("builder.channel.wait.tooLong"), fix: null };
    case "agent_not_published":
      return { section: "audience", text: t("builder.channel.error.agent_not_published"), fix: fix ?? "publish_agent" };
    case "bag_empty":
      return { section: "audience", text: t("builder.channel.error.bag_empty"), fix: fix ?? "assign_balance" };
    case "audience_admin_only_template":
      return { section: "audience", text: t("builder.channel.error.audience_admin_only_template"), fix: null };
    default:
      return {
        section: "general",
        text: res.status === 401 || res.status === 403 ? t("common.forbidden") : t("builder.channel.error.generic"),
        fix: null,
      };
  }
}

/** El arreglo de una comprobación o de un error, como enlace; `null` si no se puede ofrecer aquí. */
export function fixLink(fix: string | null, targets: FixTargets): { href: string; label: MessageKey } | null {
  switch (fix) {
    case "publish_agent":
      return targets.agent ? { href: targets.agent, label: "builder.channel.fix.publish_agent" } : null;
    case "run_tests":
      return targets.tests ? { href: targets.tests, label: "builder.channel.fix.run_tests" } : null;
    case "assign_balance":
      return targets.balance ? { href: targets.balance, label: "builder.channel.fix.assign_balance" } : null;
    case "add_recipient":
      return { href: targets.recipients, label: "builder.channel.fix.add_recipient" };
    default:
      return null;
  }
}

/** «a quién responde y el escalado»: lo que cambió otra persona (412 `changes`). */
export function conflictSections(t: T, changes: unknown): string {
  const list = Array.isArray(changes) ? changes.filter((c): c is string => typeof c === "string") : [];
  const known = list.map((c) =>
    ["audience", "escalation", "wait_message"].includes(c) ? t(`builder.channel.section.${c}` as MessageKey) : t("builder.channel.section.unknown"),
  );
  const unique = [...new Set(known)];
  if (!unique.length) return t("builder.channel.section.unknown");
  if (unique.length === 1) return unique[0]!;
  return `${unique.slice(0, -1).join(", ")}${t("builder.channel.section.and")}${unique[unique.length - 1]}`;
}

// ── las comprobaciones (32.8) ───────────────────────────────────────────────

export function checkText(t: T, check: ChannelCheck): string {
  switch (check.code) {
    case "tests_up_to_date":
    case "escalation_recipient":
      return t(`builder.channel.check.${check.code}.${check.ok ? "ok" : "ko"}` as MessageKey);
    case "agent_not_published":
    case "bag_empty":
    case "audience_admin_only_template":
      return t(`builder.channel.check.${check.code}` as MessageKey);
    default:
      return t("builder.channel.check.unknown", { code: check.code });
  }
}

// ── el historial (32.7) ─────────────────────────────────────────────────────

function modeName(t: T, mode: unknown): string {
  return mode === "team_only" || mode === "everyone" || mode === "unset" ? t(`builder.channel.mode.${mode}` as MessageKey) : "—";
}

function countNumbers(t: T, list: unknown): string {
  const n = Array.isArray(list) ? list.length : 0;
  return n === 0 ? t("builder.channel.count.numbers.none") : n === 1 ? t("builder.channel.count.numbers.one") : t("builder.channel.count.numbers.other", { n });
}

function countPeople(t: T, list: unknown): string {
  const n = Array.isArray(list) ? list.length : 0;
  return n === 0 ? t("builder.channel.count.people.none") : n === 1 ? t("builder.channel.count.people.one") : t("builder.channel.count.people.other", { n });
}

const same = (a: unknown, b: unknown) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

/** Cada cambio de una fila del historial, con su antes y su después. */
export function historyLines(t: T, change: Pick<ChannelChange, "before" | "after">): string[] {
  const before = change.before ?? {};
  const after = change.after ?? {};
  const out: string[] = [];
  const ba = before.audience;
  const aa = after.audience;
  if (!same(ba?.mode, aa?.mode)) out.push(t("builder.channel.change.mode", { before: modeName(t, ba?.mode), after: modeName(t, aa?.mode) }));
  if (!same(ba?.test_numbers ?? [], aa?.test_numbers ?? []))
    out.push(t("builder.channel.change.tests", { before: countNumbers(t, ba?.test_numbers), after: countNumbers(t, aa?.test_numbers) }));
  if (!same(ba?.exceptions ?? [], aa?.exceptions ?? []))
    out.push(t("builder.channel.change.exceptions", { before: countNumbers(t, ba?.exceptions), after: countNumbers(t, aa?.exceptions) }));
  const be = before.escalation;
  const ae = after.escalation;
  if (!same(be?.recipients ?? [], ae?.recipients ?? []))
    out.push(t("builder.channel.change.recipients", { before: countPeople(t, be?.recipients), after: countPeople(t, ae?.recipients) }));
  if (be && ae && !same(be.summary, ae.summary)) {
    const yn = (v: unknown) => (v ? t("builder.channel.yes") : t("builder.channel.no"));
    out.push(t("builder.channel.change.summary", { before: yn(be.summary), after: yn(ae.summary) }));
  }
  if (!same(before.wait_message ?? null, after.wait_message ?? null)) {
    const w = (v: unknown) => (typeof v === "string" && v.trim() ? t("builder.channel.wait.some") : t("builder.channel.wait.none"));
    out.push(t("builder.channel.change.wait", { before: w(before.wait_message), after: w(after.wait_message) }));
  }
  return out;
}

// ── el enlace del dueño (31) ────────────────────────────────────────────────

export const OWNER_LINK_MODES = ["coexistence", "cloud_api", "whatsapp_login"] as const satisfies readonly OwnerLinkMode[];

export function ownerLinkModeName(t: T, mode: string): string {
  return (OWNER_LINK_MODES as readonly string[]).includes(mode) ? t(`builder.ownerLink.modeName.${mode}` as MessageKey) : mode;
}

/** La frase «desde su teléfono» solo con la bandera (31.3). */
export function ownerLinkCopy(fromPhone: boolean): { body: MessageKey; message: MessageKey } {
  return fromPhone
    ? { body: "builder.ownerLink.body.phone", message: "builder.ownerLink.message.phone" }
    : { body: "builder.ownerLink.body", message: "builder.ownerLink.message" };
}
