/**
 * Page awareness (CO-03) — §4.2 of the research.
 *
 * The drawer sends `page_context` with every turn so that "make it more
 * formal" typed on `/clients/boreal/agent` needs no follow-up question.
 * It travels as a mid-conversation SYSTEM message, never inside the cached
 * system prefix (correction C4), which is why the API takes it per run
 * instead of per thread.
 *
 * It is also what makes the EMPTY state legal: §14 forbids generic
 * suggestions. On `/clients/boreal/channels` the drawer must not offer
 * "explain my usage" — it offers the question a person standing on that
 * page actually has.
 *
 * Pure module: no React, no `window`. The pathname comes in as an
 * argument so this is trivially testable.
 */
import type { MessageKey } from "@/i18n/messages";

export type PageContext = {
  route: string;
  client_ref: string | null;
  tab: string | null;
  selection: string | null;
};

/** Which bucket of suggestions this route falls into. */
export type ContextId =
  | "home"
  | "clients"
  | "client"
  | "agent"
  | "agentSettings"
  | "tools"
  | "skills"
  | "knowledge"
  | "channels"
  | "playground"
  | "conversations"
  | "usage"
  | "audit"
  | "team"
  | "keys"
  | "billing";

/**
 * Split a console pathname into the context the Companion receives.
 *
 * `/clients/new` is deliberately NOT a client ref: it is the creation
 * form, and treating "new" as a client reference would make the Companion
 * talk about a client that does not exist.
 */
export function readPageContext(pathname: string, selection: string | null = null): PageContext {
  const parts = pathname.split("/").filter(Boolean);
  let clientRef: string | null = null;
  let tab: string | null = null;
  if (parts[0] === "clients" && parts[1] && parts[1] !== "new") {
    clientRef = safeDecode(parts[1]);
    tab = parts.slice(2).join("/") || null;
  } else if (parts.length > 0) {
    tab = parts.slice(1).join("/") || null;
  }
  return { route: pathname, client_ref: clientRef, tab, selection };
}

function safeDecode(v: string): string {
  try {
    return decodeURIComponent(v);
  } catch {
    return v;
  }
}

export function contextId(ctx: PageContext): ContextId {
  const parts = ctx.route.split("/").filter(Boolean);
  const head = parts[0];
  if (!head) return "home";
  if (head === "clients") {
    if (!ctx.client_ref) return "clients";
    switch (ctx.tab) {
      case "agent":
        return "agent";
      case "agent/settings":
        return "agentSettings";
      case "tools":
        return "tools";
      case "skills":
        return "skills";
      case "knowledge":
        return "knowledge";
      case "channels":
      case "channels/diagnostics":
        return "channels";
      case "playground":
        return "playground";
      case "conversations":
        return "conversations";
      default:
        return "client";
    }
  }
  if (head === "usage") return "usage";
  if (head === "audit") return "audit";
  if (head === "team") return "team";
  if (head === "keys") return "keys";
  if (head === "billing") return "billing";
  return "home";
}

/**
 * The three suggestions of the empty state. Message keys, not text: the
 * lane owns the wording in ES and EN, and `{client}` is filled with the
 * ref the user is actually looking at.
 */
export function suggestionKeys(ctx: PageContext): [MessageKey, MessageKey, MessageKey] {
  const id = contextId(ctx);
  return [
    `companion.suggest.${id}.1` as MessageKey,
    `companion.suggest.${id}.2` as MessageKey,
    `companion.suggest.${id}.3` as MessageKey,
  ];
}
