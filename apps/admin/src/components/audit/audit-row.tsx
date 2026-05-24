"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import type { AuditLogOut } from "@/lib/backend";
import { fullDateTime } from "@/lib/format";

/**
 * One row of the audit timeline. Renders:
 *
 * - Compact line with timestamp · actor · action · target.
 * - When ``before_json`` or ``after_json`` are present, an expandable
 *   diff panel showing them side-by-side. Most actions carry one or
 *   both — a connector toggle has only ``after``; an agent_config
 *   promote has both; a tenant deletion has only ``before``.
 *
 * The whole row is a button so clicking anywhere expands the diff —
 * matches the Stripe / Linear audit-log UX.
 */
export function AuditRow({ entry }: { entry: AuditLogOut }) {
  const [open, setOpen] = useState(false);
  const hasDiff =
    entry.before_json !== null || entry.after_json !== null;
  const verb = describeAction(entry.action);
  return (
    <div
      className="rounded-md border border-border bg-card"
      data-testid={`audit-row-${entry.id}`}
    >
      <button
        type="button"
        onClick={() => hasDiff && setOpen((v) => !v)}
        className={
          "flex w-full items-center justify-between gap-3 px-3 py-2 text-left " +
          (hasDiff ? "cursor-pointer hover:bg-muted/40" : "cursor-default")
        }
        disabled={!hasDiff}
        aria-expanded={open}
      >
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-[10px] font-mono text-muted-foreground tabular-nums whitespace-nowrap">
            {fullDateTime(entry.created_at)}
          </span>
          <Badge variant="outline" className="font-mono text-[10px]">
            {entry.actor}
          </Badge>
          <span className="text-sm">{verb}</span>
          <code
            className="text-xs font-mono text-muted-foreground truncate"
            title={entry.target}
          >
            {entry.target}
          </code>
        </div>
        {hasDiff ? (
          <span
            aria-hidden="true"
            className="text-xs font-mono text-muted-foreground shrink-0"
          >
            {open ? "▾" : "▸"}
          </span>
        ) : null}
      </button>
      {hasDiff && open ? (
        <div
          className="border-t border-border bg-muted/20 px-3 py-2"
          data-testid={`audit-diff-${entry.id}`}
        >
          <DiffPanel before={entry.before_json} after={entry.after_json} />
        </div>
      ) : null}
    </div>
  );
}

function DiffPanel({
  before,
  after,
}: {
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
}) {
  // Single-side rendering for the common cases (only-after = "created",
  // only-before = "deleted"). Both-sides rendering shows a quick
  // key-by-key diff for the readable case — agent_config updates,
  // connector status changes, runtime flag toggles.
  if (before === null && after !== null) {
    return (
      <div className="grid gap-1">
        <SidePanelHeader label="Resultado" tone="added" />
        <JsonBlock value={after} />
      </div>
    );
  }
  if (after === null && before !== null) {
    return (
      <div className="grid gap-1">
        <SidePanelHeader label="Estado previo" tone="removed" />
        <JsonBlock value={before} />
      </div>
    );
  }
  if (before === null || after === null) return null;
  return (
    <div className="grid gap-3 md:grid-cols-2">
      <div className="grid gap-1">
        <SidePanelHeader label="Antes" tone="removed" />
        <JsonBlock value={before} />
      </div>
      <div className="grid gap-1">
        <SidePanelHeader label="Después" tone="added" />
        <JsonBlock value={after} />
      </div>
    </div>
  );
}

function SidePanelHeader({
  label,
  tone,
}: {
  label: string;
  tone: "added" | "removed";
}) {
  const cls =
    tone === "added"
      ? "text-emerald-700 dark:text-emerald-300"
      : "text-red-700 dark:text-red-300";
  return (
    <span
      className={
        "text-[10px] font-mono uppercase tracking-wider " + cls
      }
    >
      {label}
    </span>
  );
}

function JsonBlock({ value }: { value: Record<string, unknown> }) {
  return (
    <pre className="overflow-x-auto rounded bg-background/80 p-2 text-[11px] leading-tight">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

/**
 * Best-effort humanization of common action names. Falls back to the
 * raw action when not in the catalog — the operator still sees what
 * happened, just less polished.
 */
function describeAction(action: string): string {
  return ACTION_LABELS[action] ?? action;
}

const ACTION_LABELS: Record<string, string> = {
  "agent_config.promote": "promovió la versión",
  "agent_config.rollback": "revirtió a la versión",
  "agent_config.runtime_capabilities_updated":
    "actualizó capacidades de runtime",
  "agent_config.created": "creó borrador",
  "connector.connected": "conectó el connector",
  "connector.disconnected": "desconectó el connector",
  "connector.tools_auto_enabled": "auto-habilitó tools del connector",
  "conversation.agent_toggled": "cambió control del agente",
  "conversation.escalated": "escaló la conversación",
  "tenant.created": "creó tenant",
  "tenant.deleted": "eliminó tenant",
};
