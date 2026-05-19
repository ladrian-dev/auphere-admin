"use client";

/**
 * Left rail of the Playground — list of the operator's threads for the
 * active tenant, plus a "new conversation" button at the top.
 *
 * RLS guarantees the qa-api only returns threads owned by this
 * operator, so we never have to filter client-side. Mutations
 * (rename, archive) live in the thread detail view; this list is
 * read-only navigation.
 */
import { useState } from "react";

import type { QAThread } from "@/lib/qa-api";

export function ThreadList({
  threads,
  activeThreadId,
  onSelect,
  onCreate,
}: {
  threads: QAThread[];
  activeThreadId: string | null;
  onSelect: (thread: QAThread | null) => void;
  onCreate: (title?: string) => Promise<void>;
}) {
  const [creating, setCreating] = useState(false);

  async function handleCreate() {
    if (creating) return;
    setCreating(true);
    try {
      await onCreate();
    } catch (err) {
      console.error("createThread failed", err);
    } finally {
      setCreating(false);
    }
  }

  return (
    <aside
      aria-label="QA threads"
      className="flex min-h-0 flex-col bg-card/40"
    >
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Conversaciones
        </span>
        <button
          type="button"
          onClick={handleCreate}
          disabled={creating}
          className="rounded border border-border px-2 py-0.5 text-xs hover:bg-muted disabled:opacity-50"
        >
          + nueva
        </button>
      </div>
      <ul className="flex-1 overflow-y-auto p-2">
        {threads.length === 0 ? (
          <li className="px-2 py-3 text-xs text-muted-foreground">
            Sin conversaciones. Creá una para empezar.
          </li>
        ) : (
          threads.map((t) => (
            <li key={t.id}>
              <button
                type="button"
                onClick={() => onSelect(t)}
                aria-current={t.id === activeThreadId ? "page" : undefined}
                className={`block w-full rounded px-2 py-1.5 text-left text-sm ${
                  t.id === activeThreadId
                    ? "bg-muted font-medium"
                    : "hover:bg-muted/60"
                }`}
              >
                <span className="line-clamp-1">{t.title}</span>
                <span className="block font-mono text-[10px] text-muted-foreground">
                  {t.id.slice(0, 8)} · {t.message_count} msg
                  {t.archived_at ? " · archivado" : ""}
                </span>
              </button>
            </li>
          ))
        )}
      </ul>
    </aside>
  );
}
