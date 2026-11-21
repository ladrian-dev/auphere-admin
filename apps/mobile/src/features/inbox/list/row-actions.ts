import { useQueryClient, type InfiniteData, type QueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { endpoints, type Conversation, type ConversationPage, type InboxFilter } from "@/api/endpoints";
import { invalidateInbox, keys } from "@/api/query";
import type { T } from "@/i18n/t";
import { haptics } from "@/motion/haptics";
import { useToast } from "@/ui/toast";

/**
 * What a row's swipe — or its accessibility action — does (spec 069, R9.4,
 * R3.4, micro 6): resolve or reopen, mark read or unread, at once in every
 * list on screen and then from the API, with «Deshacer» in the brief notice.
 *
 * Undoing a resolve reopens it, and a reopened conversation goes back to the
 * agent (`inbox_lifecycle.reopen`): one that waited for a person or that a
 * person answered does not get that back. The notice says so in its words.
 */
export type RowAction = "resolve" | "reopen" | "read" | "unread";

/** Read when called, not at import: the endpoints object is the shared one. */
function call(action: RowAction, id: string): Promise<unknown> {
  if (action === "resolve") return endpoints.resolve(id);
  if (action === "reopen") return endpoints.reopen(id);
  if (action === "read") return endpoints.markRead(id);
  return endpoints.markUnread(id);
}

const UNDO: Record<RowAction, RowAction> = { resolve: "reopen", reopen: "resolve", read: "unread", unread: "read" };

/** The actions a row offers now: one of each pair. */
export function rowActionsOf(c: Pick<Conversation, "state" | "unread">): { left: RowAction; right: RowAction } {
  return { left: c.state === "resolved" ? "reopen" : "resolve", right: c.unread ? "read" : "unread" };
}

/** Whether a conversation, as it is now, still belongs in a list with this filter (the API's own rules). */
function fits(c: Conversation, filter: InboxFilter): boolean {
  if (filter === "resolved") return c.state === "resolved";
  if (c.state === "resolved") return false;
  if (filter === "waiting") return c.state === "waiting" && !c.assignee;
  if (filter === "unread") return c.unread;
  return true;
}

function changed(c: Conversation, action: RowAction): Conversation {
  if (action === "read") return { ...c, unread: false };
  if (action === "unread") return { ...c, unread: true };
  if (action === "resolve") return { ...c, state: "resolved", assignee: null, waiting: null };
  return { ...c, state: "agent", assignee: null, waiting: null };
}

/** Every loaded list at once: the row changes or leaves the lists it no longer belongs to. */
export function patchLists(qc: QueryClient, id: string, action: RowAction): void {
  for (const [key, data] of qc.getQueriesData<InfiniteData<ConversationPage>>({ queryKey: keys.inboxLists })) {
    if (!data?.pages) continue;
    const filter = (key[2] as InboxFilter | undefined) ?? "all";
    qc.setQueryData<InfiniteData<ConversationPage>>(key, {
      ...data,
      pages: data.pages.map((p) => ({
        ...p,
        items: p.items.flatMap((c) => {
          if (c.id !== id) return [c];
          const next = changed(c, action);
          return fits(next, filter) ? [next] : [];
        }),
      })),
    });
  }
}

export function useRowActions(t: T) {
  const qc = useQueryClient();
  const toast = useToast();

  const apply = useCallback(
    async (c: Conversation, action: RowAction): Promise<boolean> => {
      patchLists(qc, c.id, action);
      try {
        await call(action, c.id);
        return true;
      } catch {
        haptics.warning();
        toast.show({ text: t("inbox.error.action"), tone: "warn" });
        return false;
      } finally {
        invalidateInbox(qc);
      }
    },
    [qc, t, toast],
  );

  return useCallback(
    async (c: Conversation, action: RowAction) => {
      if (!(await apply(c, action))) return;
      if (action === "resolve") haptics.success();
      else haptics.select();
      const agent = c.handled_by_agent?.name ?? c.agent?.name ?? null;
      const text =
        action === "resolve"
          ? t("v13.inbox.toast.resolved")
          : action === "reopen"
            ? agent
              ? t("v13.inbox.toast.reopened", { agent })
              : t("v13.inbox.toast.reopened.noAgent")
            : action === "read"
              ? t("v13.inbox.toast.read")
              : t("inbox.toast.unread");
      toast.show({ text, tone: "ok", action: { label: t("v13.inbox.undo"), onPress: () => void apply(changed(c, action), UNDO[action]) } });
    },
    [apply, t, toast],
  );
}
