import { useQueryClient } from "@tanstack/react-query";
import * as Crypto from "expo-crypto";
import { useCallback, useState } from "react";

import { endpoints, type BusinessSections, type Section } from "@/api/endpoints";
import { ApiError } from "@/api/errors";
import { keys } from "@/api/query";
import { useT } from "@/i18n/t";
import { conflictOf, lastUndoable, withSection, writeErrorText } from "@/lib/business-model";
import { haptics } from "@/motion/haptics";
import { useOnline } from "@/ui/online";
import { useToast } from "@/ui/toast";

/**
 * One write to a section of the business (spec 047, T169; 13.3, 13.4, 50.4,
 * 50.5), the same for the four of them:
 *
 * - **Without a connection nothing is sent or queued**: the screen says so and
 *   keeps what was typed (`useDraft`), and the person saves when it is back.
 * - It carries the section's revision (`If-Match`) and its own key.
 * - **Someone wrote first** (412): the section as it is now goes into the
 *   cache — so a second try carries the new revision — and the screen shows
 *   the conflict with its two ways out; nothing of the person's is lost.
 * - **Saved**: the section as the API left it, a vibration, and a brief notice
 *   with «Deshacer» once the history has the change (13.3).
 */
export type WriteOutcome = "saved" | "conflict" | "failed";

export function useSectionWrite<K extends Section>(section: K | K[]) {
  const t = useT();
  const qc = useQueryClient();
  const online = useOnline();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const list = Array.isArray(section) ? section : [section];
  const primary = list[0]!;
  // A string keeps the callbacks stable while the caller passes a fresh array each render.
  const joined = list.join(",");

  const revision = useCallback(
    (s: Section = primary) => qc.getQueryData<BusinessSections>(keys.business)?.[s].revision ?? 0,
    [qc, primary],
  );

  const undo = useCallback(
    async (changeId: string): Promise<boolean> => {
      try {
        await endpoints.undoChange(changeId, Crypto.randomUUID());
        haptics.success();
        toast.show({ text: t("business.history.undoneToast") });
        await qc.invalidateQueries({ queryKey: keys.business });
        return true;
      } catch (e) {
        haptics.warning();
        const text =
          e instanceof ApiError && e.offline
            ? t("negocio.offline")
            : e instanceof ApiError && e.status === 412
              ? t("business.history.conflict")
              : e instanceof ApiError && e.status === 409
                ? t("business.history.unavailable")
                : t("business.section.error.generic");
        toast.show({ text });
        void qc.invalidateQueries({ queryKey: keys.business });
        return false;
      }
    },
    [qc, t, toast],
  );

  /**
   * `write` gets the revision and a fresh key and answers the section as it is
   * now. `saved` is the sentence of the brief notice; `into` is the section the
   * answer replaces (the hook's first one by default); `action` replaces the
   * notice's «Deshacer» of the history with one of the caller's own. A write
   * whose answer does not belong in the business (a location's week) reads its
   * revision with `revisionNow` and keeps its answer with `keep`.
   */
  const run = useCallback(
    async <S extends Section>(
      write: (revision: number, key: string) => Promise<BusinessSections[S]>,
      opts: {
        saved: string;
        into?: S;
        undoable?: boolean;
        action?: { label: string; onPress: () => void };
        revisionNow?: () => number;
        keep?: (answer: BusinessSections[S]) => void;
      },
    ): Promise<WriteOutcome> => {
      const into = (opts.into ?? primary) as S;
      if (!online) {
        setError(t("negocio.offline"));
        return "failed";
      }
      setBusy(true);
      setError(null);
      setConflict(false);
      try {
        const out = await write(opts.revisionNow ? opts.revisionNow() : revision(into), Crypto.randomUUID());
        if (opts.keep) opts.keep(out);
        else qc.setQueryData<BusinessSections>(keys.business, (all) => withSection(all, into, out));
        haptics.success();
        // The history (and the provenance) move with the write: read again, then offer the undo of this change.
        await qc.refetchQueries({ queryKey: keys.business }).catch(() => undefined);
        const last = opts.undoable === false ? null : lastUndoable(qc.getQueryData<BusinessSections>(keys.business)?.history ?? [], joined.split(",") as Section[]);
        toast.show({ text: opts.saved, action: opts.action ?? (last ? { label: t("business.history.undo"), onPress: () => void undo(last.id) } : undefined) });
        return "saved";
      } catch (e) {
        haptics.warning();
        const c = conflictOf<BusinessSections[S]>(e);
        if (c) {
          if (c.current && opts.keep) opts.keep(c.current);
          else if (c.current) qc.setQueryData<BusinessSections>(keys.business, (all) => withSection(all, into, c.current!));
          if (!c.current || opts.keep) void qc.invalidateQueries({ queryKey: keys.business });
          setConflict(true);
          return "conflict";
        }
        setError(writeErrorText(e, t, into));
        return "failed";
      } finally {
        setBusy(false);
      }
    },
    [online, primary, joined, qc, revision, t, toast, undo],
  );

  const reset = useCallback(() => {
    setError(null);
    setConflict(false);
  }, []);

  return { run, undo, busy, error, conflict, online, reset, setError };
}
