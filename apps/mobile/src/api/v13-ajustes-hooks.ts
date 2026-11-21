import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ajustesApi, isAutoclose, type Autoclose, type InboxSettings } from "./v13-ajustes";

/** Its own key, under the Bandeja's: nothing the live line invalidates touches it. */
export const inboxSettingsKey = ["inbox", "settings"] as const;

export type AutocloseState =
  | { state: "off" }
  | { state: "loading" }
  | { state: "error"; retry: () => void }
  | { state: "ready"; hours: Autoclose | undefined; status: "idle" | "saving" | "saved" | "failed"; save: (hours: Autoclose) => Promise<void> };

/**
 * The inactivity close in Ajustes (spec 069, R17.2), only with the Bandeja
 * (the API's scope needs the module). What is chosen shows at once; a refusal
 * puts back what is stored and says so (as the web does, spec 064 R5).
 */
export function useInboxAutoclose(enabled: boolean): AutocloseState {
  const qc = useQueryClient();
  const query = useQuery({ queryKey: inboxSettingsKey, queryFn: ajustesApi.inboxSettings, enabled });
  const [status, setStatus] = useState<"idle" | "saving" | "saved" | "failed">("idle");
  if (!enabled) return { state: "off" };
  if (query.data) {
    const stored = query.data.autoclose_hours;
    const save = async (hours: Autoclose) => {
      if (status === "saving") return;
      const before = qc.getQueryData<InboxSettings>(inboxSettingsKey);
      qc.setQueryData<InboxSettings>(inboxSettingsKey, { autoclose_hours: hours });
      setStatus("saving");
      try {
        const saved = await ajustesApi.setInboxSettings(hours);
        qc.setQueryData<InboxSettings>(inboxSettingsKey, saved);
        setStatus("saved");
      } catch {
        if (before) qc.setQueryData<InboxSettings>(inboxSettingsKey, before);
        setStatus("failed");
      }
    };
    // A value this version does not know is not said to be «Nunca»: none of the choices is ticked.
    return { state: "ready", hours: isAutoclose(stored) ? stored : undefined, status, save };
  }
  if (query.isError) return { state: "error", retry: () => void query.refetch() };
  return { state: "loading" };
}
