import { useQueryClient } from "@tanstack/react-query";
import { router } from "expo-router";
import { useCallback } from "react";
import { Alert } from "react-native";

import { endpoints, type Detail } from "@/api/endpoints";
import { invalidateInbox, keys } from "@/api/query";
import { bandejaApi } from "@/api/v13-bandeja";
import type { T } from "@/i18n/t";
import { haptics } from "@/motion/haptics";
import { useToast } from "@/ui/toast";

import type { useConversationActions } from "./use-conversation";

/**
 * What the conversation's screen says in the brief notice (spec 069, R11.4,
 * micro 6; the spec amends 044 R16.7):
 *
 * - **Tomar el control** says «Ahora respondes tú…» with «Devolver», the
 *   design's undo. Giving it back says nothing: the strip coming back is the
 *   answer. «Devolver» uses the control version the takeover answered, not
 *   the one the screen read before (a stale one is a 412).
 * - **Marcar como no leída** goes back to the list and offers «Deshacer».
 * - **Resolver** stays and offers «Deshacer», which reopens it — and a
 *   reopened conversation goes back to the agent (`inbox_lifecycle.reopen`).
 * - **Vaciar chat** and **Eliminar chat** ask first, in the console's words.
 *   After «Eliminar» the conversation is a 404: the screen goes back and its
 *   reads are dropped once the way back has played, so nothing re-reads it
 *   into an error.
 */
type Act = ReturnType<typeof useConversationActions>;

/** Longer than the system's pop (about 350 ms on iOS, 300 ms on Android). */
const DROP_AFTER_BACK_MS = 800;

export function useChatActions(id: string, t: T, act: Act, agentName: string | null) {
  const qc = useQueryClient();
  const toast = useToast();
  const version = useCallback(() => qc.getQueryData<Detail>(keys.conversation(id))?.control_version ?? null, [qc, id]);
  const failed = useCallback(() => {
    haptics.warning();
    toast.show({ text: t("inbox.error.action"), tone: "warn" });
  }, [t, toast]);

  const takeOver = async (v: number) => {
    if (!(await act.takeOver(v))) return;
    toast.show({
      text: agentName ? t("v13.conv.toast.tookOver", { agent: agentName }) : t("v13.conv.toast.tookOver.noAgent"),
      tone: "ok",
      action: {
        label: t("app.inbox.giveBack.short"),
        onPress: () => {
          const now = version();
          if (now !== null) void act.giveBack(now);
        },
      },
    });
  };

  const markUnread = async () => {
    if (!(await act.markUnread())) return;
    router.back();
    toast.show({
      text: t("inbox.toast.unread"),
      tone: "ok",
      action: {
        label: t("v13.inbox.undo"),
        onPress: () =>
          void endpoints
            .markRead(id)
            .then(() => invalidateInbox(qc))
            .catch(failed),
      },
    });
  };

  const resolve = async () => {
    if (!(await act.resolve())) return;
    toast.show({
      text: t("v13.conv.toast.resolved"),
      tone: "ok",
      action: {
        label: t("v13.inbox.undo"),
        onPress: () =>
          void endpoints
            .reopen(id)
            .then((d) => {
              qc.setQueryData(keys.conversation(id), d);
              void qc.invalidateQueries({ queryKey: keys.thread(id) });
              invalidateInbox(qc);
            })
            .catch(failed),
      },
    });
  };

  const clear = async () => {
    try {
      qc.setQueryData(keys.conversation(id), await bandejaApi.clear(id));
      await qc.invalidateQueries({ queryKey: keys.thread(id) });
      invalidateInbox(qc);
      haptics.success();
      toast.show({ text: t("inbox.toast.cleared"), tone: "ok" });
    } catch {
      failed();
    }
  };

  const remove = async () => {
    try {
      await bandejaApi.archive(id);
    } catch {
      failed();
      return;
    }
    haptics.success();
    void qc.cancelQueries({ queryKey: keys.conversation(id) });
    router.back();
    toast.show({ text: t("inbox.toast.deleted"), tone: "ok" });
    invalidateInbox(qc);
    // Once the way back has played (the system's push/pop is under this), the screen no longer reads them.
    setTimeout(() => {
      qc.removeQueries({ queryKey: keys.conversation(id) });
      qc.removeQueries({ queryKey: keys.thread(id) });
    }, DROP_AFTER_BACK_MS);
  };

  const confirmClear = () =>
    Alert.alert(t("inbox.clear.title"), t("inbox.clear.body"), [
      { text: t("app.cancel"), style: "cancel" },
      { text: t("inbox.action.clear"), style: "destructive", onPress: () => void clear() },
    ]);
  const confirmDelete = () =>
    Alert.alert(t("inbox.delete.title"), t("inbox.delete.body"), [
      { text: t("app.cancel"), style: "cancel" },
      { text: t("inbox.action.delete"), style: "destructive", onPress: () => void remove() },
    ]);

  return { takeOver, markUnread, resolve, confirmClear, confirmDelete, clear, remove };
}
