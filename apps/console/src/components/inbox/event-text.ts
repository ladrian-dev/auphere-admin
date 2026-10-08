import type { MessageKey } from "@/i18n/messages";
import type { InboxAuthor } from "@/lib/backend/inbox";

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
      return detail ? t("inbox.event.escalated.reason", { reason: detail }) : t("inbox.event.escalated");
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
