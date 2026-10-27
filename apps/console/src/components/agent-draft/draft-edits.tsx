"use client";

import * as React from "react";

import type { AgentDraft, DraftPatch } from "@/lib/backend/agent-draft-types";

/**
 * Spec 047 (historia 2): every editor of the agent page writes into ONE draft
 * through ONE save bar.
 *
 * Each editor is a *section* (`prompt`, `settings`). It keeps its own state —
 * validation, inline errors — and tells the provider two things: which of its
 * fields are pending (in the API's keys, so the conflict notice can compare
 * them with the other person's), and how to hand its part of the PATCH over
 * or go back to what the draft says. The bar is the only place that saves.
 *
 * The pending map is an external store read with `useSyncExternalStore`: the
 * sections report from an effect and the bar re-renders, without a state
 * update inside anybody's effect.
 */

export type DraftSectionKey = "prompt" | "settings";
export const SECTION_ORDER: readonly DraftSectionKey[] = ["prompt", "settings"];

export type SectionError = { code?: string | null; message: string; info?: Record<string, unknown> };

export type DraftSectionHandlers = {
  /** Validate and hand over this section's part of the PATCH; `null` when it
   *  has errors (the section shows them). */
  collect: () => Promise<DraftPatch | null>;
  /** Go back to what `draft` says. */
  reset: (draft: AgentDraft) => void;
  /** An error of the API that belongs to this section; `true` when shown. */
  onError?: (error: SectionError) => boolean;
};

/** Pending sections → the fields each one would change. */
export type PendingFields = Readonly<Partial<Record<DraftSectionKey, readonly string[]>>>;

const EMPTY: PendingFields = {};

class DraftEditsStore {
  private pending: PendingFields = EMPTY;
  private readonly listeners = new Set<() => void>();
  readonly handlers: Partial<Record<DraftSectionKey, DraftSectionHandlers>> = {};

  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };

  getSnapshot = () => this.pending;

  /** A section's handlers, until the returned function takes them away. */
  register(key: DraftSectionKey, handlers: DraftSectionHandlers): () => void {
    this.handlers[key] = handlers;
    return () => {
      if (this.handlers[key] === handlers) delete this.handlers[key];
      this.report(key, null);
    };
  }

  report(key: DraftSectionKey, fields: readonly string[] | null) {
    const before = this.pending[key];
    const now = fields && fields.length ? fields : null;
    if (before === undefined && now === null) return;
    if (before && now && before.length === now.length && before.every((f, i) => f === now[i])) return;
    const next: Partial<Record<DraftSectionKey, readonly string[]>> = { ...this.pending };
    if (now) next[key] = now;
    else delete next[key];
    this.pending = next;
    for (const listener of this.listeners) listener();
  }
}

type DraftEditsValue = {
  refId: string;
  /** The agent the page edits — always a real id, the principal's included. */
  agentId: string;
  draft: AgentDraft;
  canWrite: boolean;
  store: DraftEditsStore;
  /** Show `next` and bring every section back to it (after a save, or after
   *  choosing the other person's changes). */
  adopt: (next: AgentDraft) => void;
};

const DraftEditsContext = React.createContext<DraftEditsValue | null>(null);

export function DraftEditsProvider({
  refId,
  agentId,
  initial,
  canWrite,
  children,
}: {
  refId: string;
  agentId: string;
  initial: AgentDraft;
  canWrite: boolean;
  children: React.ReactNode;
}) {
  const [store] = React.useState(() => new DraftEditsStore());
  const pending = React.useSyncExternalStore(store.subscribe, store.getSnapshot, () => EMPTY);
  const [draft, setDraft] = React.useState(initial);
  const [seen, setSeen] = React.useState(initial);
  // A refresh brings the draft as the server has it now. With nothing
  // pending it is the one to show; with something pending the screen keeps
  // what the person is writing, and the next save finds out (412).
  if (initial !== seen) {
    setSeen(initial);
    if (Object.keys(pending).length === 0) setDraft(initial);
  }

  const adopt = React.useCallback(
    (next: AgentDraft) => {
      setDraft(next);
      for (const key of SECTION_ORDER) store.handlers[key]?.reset(next);
    },
    [store],
  );

  const value = React.useMemo(
    () => ({ refId, agentId, draft, canWrite, store, adopt }),
    [refId, agentId, draft, canWrite, store, adopt],
  );
  return <DraftEditsContext.Provider value={value}>{children}</DraftEditsContext.Provider>;
}

/** The provider, or `null` when the editor is used on its own (it then keeps
 *  its own save button, as before spec 047). */
export function useDraftEdits(): DraftEditsValue | null {
  return React.useContext(DraftEditsContext);
}

/** The provider, for the pieces that only exist inside it (the bar, the
 *  prompt editor). */
export function useRequiredDraftEdits(): DraftEditsValue {
  const ctx = React.useContext(DraftEditsContext);
  if (!ctx) throw new Error("this piece of the agent page needs a DraftEditsProvider");
  return ctx;
}

/** What is pending, section by section. */
export function usePendingFields(): PendingFields {
  const ctx = useDraftEdits();
  return React.useSyncExternalStore(
    ctx ? ctx.store.subscribe : noopSubscribe,
    ctx ? ctx.store.getSnapshot : emptySnapshot,
    emptySnapshot,
  );
}

/**
 * Register an editor as a section of the bar. `fields` are its pending
 * changes in the API's keys (empty when it has none); `handlers` are read
 * when the bar saves, so they can close over the latest state.
 */
export function useDraftSection(
  key: DraftSectionKey,
  fields: readonly string[],
  handlers: DraftSectionHandlers,
): boolean {
  const ctx = useDraftEdits();
  const store = ctx?.store;
  const latest = React.useRef(handlers);
  React.useEffect(() => {
    latest.current = handlers;
  });
  React.useEffect(
    () =>
      store?.register(key, {
        collect: () => latest.current.collect(),
        reset: (draft) => latest.current.reset(draft),
        onError: (error) => latest.current.onError?.(error) ?? false,
      }),
    [store, key],
  );
  const signature = fields.join("|");
  React.useEffect(() => {
    store?.report(key, signature ? signature.split("|") : null);
  }, [store, key, signature]);
  return Boolean(ctx);
}

function noopSubscribe() {
  return () => {};
}

function emptySnapshot(): PendingFields {
  return EMPTY;
}
