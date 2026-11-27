"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as React from "react";

import type { AgentKnowledge } from "@/lib/backend/agent-knowledge-types";
import { keys, unwrap } from "@/lib/query";

import type { Result } from "./builder-model";
import { visibleSources } from "./knowledge-model";

/** Spec 082 (R2.4): how often a list with a source being read is read again… */
export const KNOWLEDGE_POLL_MS = 5_000;
/** …and for how long, from the first time it saw one being read. */
export const KNOWLEDGE_POLL_FOR_MS = 10 * 60_000;

type Ids = { ref: string; agent: string };

/**
 * An agent's own knowledge (spec 082, Historia 2), under
 * `["agent",ref,id,"knowledge"]`: the Knowledge list and «Qué sabe» read this
 * same query, so what one shows the other counts (R2.2). The first paint is
 * the server's read (`initialData`); without one, it reads at once.
 *
 * While a source is still being read (`pending`) and the tab is visible, it
 * reads again every 5 s, and stops 10 minutes after it first saw one (R2.4).
 * `restart()` gives a newly added source its own 10 minutes.
 */
export function useAgentKnowledge(ids: Ids, initial: AgentKnowledge | null, reload: (body: Ids) => Promise<Result<AgentKnowledge>>, opts: { enabled?: boolean } = {}) {
  const qc = useQueryClient();
  const key = React.useMemo(() => keys.agentKnowledge(ids.ref, ids.agent), [ids.ref, ids.agent]);
  const readingSince = React.useRef<number | null>(null);
  const q = useQuery({
    queryKey: key,
    queryFn: async () => unwrap(await reload({ ref: ids.ref, agent: ids.agent })),
    initialData: initial ?? undefined,
    initialDataUpdatedAt: initial ? () => Date.now() : undefined,
    enabled: opts.enabled ?? true,
    refetchIntervalInBackground: false,
    refetchInterval: (query) => {
      const reading = (query.state.data?.items ?? []).some((d) => !d.removed_at && d.status === "pending");
      if (!reading) {
        readingSince.current = null;
        return false;
      }
      readingSince.current ??= Date.now();
      return Date.now() - readingSince.current < KNOWLEDGE_POLL_FOR_MS ? KNOWLEDGE_POLL_MS : false;
    },
  });
  const data = q.data ?? null;
  const live = React.useMemo(() => (data ? visibleSources(data.items).live.length : null), [data]);
  /** Read again now (after a change), and wait for it. */
  const refresh = React.useCallback(async () => {
    readingSince.current = null;
    await qc.invalidateQueries({ queryKey: key });
  }, [qc, key]);
  return { data, live, loading: q.isPending, failed: q.isError && !data, refresh };
}
