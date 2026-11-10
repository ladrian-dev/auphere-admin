import type { MessageKey } from "@/i18n/messages";
import type { InboxAuthor } from "@/lib/backend/inbox";
import { REASONS, inboxReasonText } from "@/lib/waiting-reasons";

type T = (key: MessageKey, vars?: Record<string, string | number>) => string;

/** Who did it, as a sentence subject: a name, «el agente», «el equipo de Auphere». */
export function whoOf(author: InboxAuthor | null, t: T): string {
  if (!author) return t("inbox.who.someone");
  if (author.kind === "member") return author.is_me ? t("inbox.who.you") : (author.name ?? t("inbox.who.someone"));
  if (author.kind === "operator") return t("inbox.who.operator");
  if (author.kind === "contact") return t("inbox.who.contact");
  return t("inbox.who.agent");
}

/**
 * Why a conversation waits, in words (spec 056, requisito 7): the column's code
 * first — the table's text when it knows it — and, for an escalation or a code
 * it does not know, what the agent wrote. Never a code: an unknown one reads
 * «El agente pidió ayuda». The row and the composer say it like this.
 */
export function waitingText(code: string | null | undefined, detail: string | null | undefined, t: T): string {
  const known = (code ?? "").trim();
  if (known && known !== "escalated" && REASONS.has(known)) return inboxReasonText(known, t);
  return inboxReasonText(detail ?? known, t);
}

/**
 * An escalation as one sentence, in the thread and in the activity: a code of
 * the table is its text («Agente sin publicar»), the agent's own words go after
 * «El agente pidió ayuda:», and an unknown code or nothing is just «El agente
 * pidió ayuda».
 */
export function escalatedText(detail: string | null | undefined, t: T): string {
  const raw = (detail ?? "").trim();
  const said = inboxReasonText(raw, t);
  return raw && said === raw ? t("inbox.event.escalated.reason", { reason: raw }) : said;
}

/**
 * What happened to a conversation, as one sentence — the same words in the
 * thread and in the contact panel's activity. «Tú» gets its own verbs
 * («Tomaste el control»): a third-person template with «Tú» as subject
 * would read «Tú tomó el control».
 */
export function eventText(kind: string | null, author: InboxAuthor | null, detail: string | null, t: T): string {
  const me = Boolean(author && author.kind === "member" && author.is_me);
  const who = whoOf(author, t);
  switch (kind) {
    case "escalated":
      return escalatedText(detail, t);
    case "takeover":
      return me ? t("inbox.event.takeover.you") : t("inbox.event.takeover", { who });
    case "released":
      return me ? t("inbox.event.released.you") : t("inbox.event.released", { who });
    case "resolved":
      return me ? t("inbox.event.resolved.you") : t("inbox.event.resolved", { who });
    case "reopened":
      if (author?.kind === "contact") return t("inbox.event.reopened.contact");
      return me ? t("inbox.event.reopened.you") : t("inbox.event.reopened", { who });
    default:
      return t("inbox.event.agent_changed");
  }
}
