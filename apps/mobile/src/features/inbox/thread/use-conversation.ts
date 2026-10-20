import { useQueryClient } from "@tanstack/react-query";
import * as Crypto from "expo-crypto";
import { File } from "expo-file-system";
import { useCallback, useEffect, useState } from "react";

import { endpoints, type Detail } from "@/api/endpoints";
import { ApiError } from "@/api/errors";
import { invalidateInbox, keys } from "@/api/query";
import type { T } from "@/i18n/t";
import { haptics } from "@/motion/haptics";

import { SEND_ERRORS, sendErrorOf, type SendError } from "../model";
import type { Pending } from "./bubble";

/**
 * Everything one does to a conversation (spec 031, R5.6, R6), with the
 * console's rules:
 *
 * - **Control** carries `If-Match`: if someone changed who answers since this
 *   screen read it, the API answers 412 with the conversation as it is now —
 *   it is painted, said, and nothing is applied (R6.2).
 * - **Send** appears at once and carries an `Idempotency-Key` that a retry
 *   reuses, so a contact never gets the same WhatsApp twice (R6.4). A failed
 *   message stays in the thread with its text and a retry (R6.6).
 */
export type Notice = { text: string; tone: "info" | "warning" };

export function sendErrorText(err: SendError, t: T): string {
  if (err === "offline") return t("app.offline.actions");
  if ((SEND_ERRORS as readonly string[]).includes(err)) return t(`inbox.composer.${err as (typeof SEND_ERRORS)[number]}`);
  return t("app.inbox.sendFailed");
}

export function useConversationActions(id: string, t: T) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [pending, setPending] = useState<Pending[]>([]);
  /** Set when this person just took control: the composer focuses and the moment plays once. */
  const [tookOver, setTookOver] = useState(0);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 5000);
    return () => clearTimeout(timer);
  }, [notice]);

  const refresh = useCallback(async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: keys.conversation(id) }),
      qc.invalidateQueries({ queryKey: keys.thread(id) }),
    ]);
    invalidateInbox(qc);
  }, [id, qc]);

  const control = useCallback(
    async (fn: () => Promise<Detail>, onDone?: () => void) => {
      setBusy(true);
      try {
        qc.setQueryData(keys.conversation(id), await fn());
        onDone?.();
      } catch (e) {
        if (e instanceof ApiError && e.status === 412 && e.info.conversation && typeof e.info.conversation === "object") {
          qc.setQueryData(keys.conversation(id), e.info.conversation as Detail);
          setNotice({ text: t("inbox.stale"), tone: "warning" });
        } else {
          setNotice({ text: e instanceof ApiError && e.offline ? t("app.offline.actions") : t("inbox.error.action"), tone: "warning" });
        }
        haptics.warning();
      } finally {
        setBusy(false);
        void refresh();
      }
    },
    [id, qc, refresh, t],
  );

  const takeOver = (version: number) =>
    control(
      () => endpoints.takeOver(id, version),
      () => {
        haptics.success();
        setTookOver((n) => n + 1);
      },
    );
  const giveBack = (version: number) => control(() => endpoints.giveBack(id, version), () => haptics.light());
  const resolve = () =>
    control(
      () => endpoints.resolve(id),
      () => {
        haptics.success();
        setNotice({ text: t("inbox.toast.resolved"), tone: "info" });
      },
    );
  const reopen = () => control(() => endpoints.reopen(id));

  const markUnread = async (): Promise<boolean> => {
    try {
      await endpoints.markUnread(id);
      invalidateInbox(qc);
      return true;
    } catch {
      setNotice({ text: t("inbox.error.action"), tone: "warning" });
      return false;
    }
  };

  const sendNow = useCallback(
    async (text: string, key: string) => {
      setPending((list) => [
        ...list.filter((p) => p.key !== key),
        { key, kind: "text", text, at: new Date().toISOString(), status: "sending", reason: null },
      ]);
      haptics.light();
      try {
        await endpoints.send(id, text, key);
        await qc.refetchQueries({ queryKey: keys.thread(id) });
        setPending((list) => list.filter((p) => p.key !== key));
        haptics.success();
        void qc.invalidateQueries({ queryKey: keys.inboxLists });
      } catch (e) {
        const err = e instanceof ApiError ? sendErrorOf(e.code, e.offline) : sendErrorOf(null);
        setPending((list) => list.map((p) => (p.key === key ? { ...p, status: "failed", reason: sendErrorText(err, t) } : p)));
        haptics.warning();
        // The conversation changed under the person (window, number, control): show it as it is.
        if (err !== "generic" && err !== "offline") void refresh();
      }
    },
    [id, qc, refresh, t],
  );

  const send = (text: string) => sendNow(text, Crypto.randomUUID());
  const retry = (key: string) => {
    const p = pending.find((x) => x.key === key);
    if (p) void sendNow(p.text, p.key);
  };

  /** R6.3: an image or a PDF, already checked against the web's rules. */
  const attach = async (uri: string, label: string) => {
    const key = Crypto.randomUUID();
    setPending((list) => [...list, { key, kind: "file", text: label, at: new Date().toISOString(), status: "sending", reason: null }]);
    try {
      await endpoints.attach(id, new File(uri) as unknown as Blob, key);
      await qc.refetchQueries({ queryKey: keys.thread(id) });
      setPending((list) => list.filter((p) => p.key !== key));
      haptics.success();
    } catch (e) {
      const err = e instanceof ApiError ? sendErrorOf(e.code, e.offline) : sendErrorOf(null);
      // A file is not retried from the bubble: the person picks it again.
      setPending((list) => list.map((p) => (p.key === key ? { ...p, status: "failed", reason: sendErrorText(err, t) } : p)));
      haptics.warning();
    }
  };

  const dismiss = (key: string) => setPending((list) => list.filter((p) => p.key !== key));

  return { busy, notice, setNotice, pending, tookOver, takeOver, giveBack, resolve, reopen, markUnread, send, retry, attach, dismiss, refresh };
}
