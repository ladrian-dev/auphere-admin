"use client";

import { Ban, Check, Loader2, Wrench, X } from "lucide-react";

import { Badge, formatLatency, formatNumber } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";

import type { ToolCall, Turn } from "./transcript";

/** Per-turn side panel: tools invoked (with dry-run blocks), tokens in/out
 * (units, never USD), client-measured latency, run status. */
export function TurnInspector({ turn }: { turn: Turn | null }) {
  const t = useT();
  const locale = useLocale();
  if (!turn) {
    return <p className="text-sm text-muted-foreground">{t("playground.inspector.empty")}</p>;
  }
  const running = turn.status === "running" || turn.status === "pending";
  const rows: Array<[string, string]> = [
    [t("playground.inspector.status"), t(`playground.inspector.status.${turn.status === "pending" ? "running" : turn.status}`)],
    [t("playground.inspector.tokensIn"), turn.inputTokens || !running ? formatNumber(turn.inputTokens, locale) : t("playground.inspector.pending")],
    [t("playground.inspector.tokensOut"), turn.outputTokens || !running ? formatNumber(turn.outputTokens, locale) : t("playground.inspector.pending")],
    [t("playground.inspector.latency"), turn.latencyMs !== null ? formatLatency(turn.latencyMs, locale) : t("playground.inspector.pending")],
    [t("playground.inspector.model"), turn.model ?? t("playground.inspector.pending")],
  ];
  return (
    <div className="flex flex-col gap-4" aria-busy={running}>
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="contents">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="min-w-0 truncate text-right font-mono text-xs tabular-nums" title={v}>
              {v}
            </dd>
          </div>
        ))}
      </dl>
      <div className="flex flex-col gap-2">
        <h4 className="text-xs font-medium tracking-eyebrow text-muted-foreground uppercase">{t("playground.inspector.tools")}</h4>
        {turn.tools.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("playground.inspector.tools.none")}</p>
        ) : (
          <ul className="flex flex-col gap-1" aria-label={t("playground.inspector.tools")}>
            {turn.tools.map((call) => (
              <ToolRow key={call.id} call={call} />
            ))}
          </ul>
        )}
      </div>
      {turn.error ? (
        <p className="text-sm text-status-danger" role="alert">
          {t("playground.run.error")}: <span className="font-mono text-xs">{turn.error}</span>
        </p>
      ) : null}
    </div>
  );
}

function ToolRow({ call }: { call: ToolCall }) {
  const t = useT();
  const locale = useLocale();
  const status =
    call.status === "blocked"
      ? { label: t("playground.inspector.tool.blocked"), icon: Ban, variant: "outline" as const, cls: "text-status-warning" }
      : call.status === "running"
        ? { label: t("playground.inspector.tool.running"), icon: Loader2, variant: "secondary" as const, cls: "animate-spin" }
        : call.status === "error"
          ? { label: t("playground.inspector.status.error"), icon: X, variant: "destructive" as const, cls: "" }
          : { label: t("playground.inspector.tool.done"), icon: Check, variant: "secondary" as const, cls: "" };
  const Icon = status.icon;
  return (
    <li className="flex min-w-0 items-center gap-2 rounded-sm border border-border px-2 py-1 text-sm">
      <Wrench aria-hidden="true" className="size-3 shrink-0 text-muted-foreground" />
      <span className="min-w-0 flex-1 truncate font-mono text-xs" title={call.name}>
        {call.name}
      </span>
      {call.latencyMs !== undefined ? <span className="font-mono text-xs tabular-nums text-muted-foreground">{formatLatency(call.latencyMs, locale)}</span> : null}
      <Badge variant={status.variant} className="gap-1">
        <Icon aria-hidden="true" className={status.cls} />
        {status.label}
      </Badge>
    </li>
  );
}
