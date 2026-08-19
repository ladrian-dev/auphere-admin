"use client";

import { Check, ChevronRight, CircleDashed, TriangleAlert } from "lucide-react";
import * as React from "react";

import { formatLatency } from "@nexus/ui";

import { useLocale, useT } from "@/i18n/client";

import { optionalKey } from "./i18n";
import type { Citation, ToolItem } from "./state";

/**
 * One tool call (§8.3): human name, state, duration, and a disclosure with
 * the raw request for whoever wants to see it.
 *
 * The name comes from three places in falling order of preference: the
 * `label` the backend sends from the CO-02 tool catalogue (one of the two
 * strings §1.4 lets us paint verbatim), our own translation of the tool
 * name, and finally the raw name. The last one is not a nice thing to
 * show, but it beats an empty card.
 *
 * There is no raw *response*: tool results never travel over the stream —
 * they go into the model's context. That is not an omission to fix, it is
 * what keeps an end customer's message body out of the partner console
 * (decision C8), and the card says so rather than showing an empty panel.
 */
export function ToolCard({ item, citation }: { item: ToolItem; citation: Citation | null }) {
  const t = useT();
  const locale = useLocale();
  const [open, setOpen] = React.useState(false);
  const id = React.useId();

  const nameKey = optionalKey(`companion.tool.name.${item.name}`);
  const label = item.label || (nameKey ? t(nameKey) : item.name);

  const state =
    item.status === "running"
      ? { icon: CircleDashed, text: t("companion.tool.running"), tone: "text-muted-foreground" }
      : item.status === "ok"
        ? { icon: Check, text: t("companion.tool.ok"), tone: "text-status-positive" }
        : { icon: TriangleAlert, text: t("companion.tool.failed"), tone: "text-status-danger" };
  const Icon = state.icon;
  const hasArgs = Object.keys(item.args).length > 0;

  return (
    <div className="min-w-0 rounded-sm border border-border bg-card px-3 py-2">
      <div className="flex min-w-0 items-center gap-2">
        <Icon
          aria-hidden="true"
          className={`size-4 shrink-0 ${state.tone} ${item.status === "running" ? "animate-spin motion-reduce:animate-none" : ""}`}
        />
        <span className="min-w-0 flex-1 truncate text-xs text-foreground" title={label}>
          {label}
        </span>
        <span className="sr-only">{state.text}</span>
        {item.latencyMs !== null ? (
          <span className="shrink-0 font-mono text-xs tabular-nums text-muted-foreground">
            {formatLatency(item.latencyMs, locale)}
          </span>
        ) : null}
      </div>

      {item.error ? <p className="mt-1 text-xs text-pretty text-status-danger">{item.error}</p> : null}

      {citation ? (
        <p className="mt-1 min-w-0 text-xs text-muted-foreground">
          {/* `claim` is written by the tool catalogue, never by a customer. */}
          <span className="text-pretty break-words">{citation.claim}</span>
          {/* A source is a path or a URL: it has no spaces to wrap at. */}
          {citation.source ? <span className="ml-1 font-mono break-all opacity-70">· {citation.source}</span> : null}
        </p>
      ) : null}

      <button
        type="button"
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen((v) => !v)}
        className="mt-1 flex min-h-6 items-center gap-1 rounded-sm text-xs text-muted-foreground transition-colors hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
      >
        <ChevronRight
          aria-hidden="true"
          className={`size-3 shrink-0 transition-transform motion-reduce:transition-none ${open ? "rotate-90" : ""}`}
        />
        {t("companion.tool.raw")}
      </button>

      {open ? (
        <div id={id} className="mt-1 min-w-0 space-y-2">
          <div className="min-w-0">
            <p className="text-xs font-medium text-muted-foreground">{t("companion.tool.args")}</p>
            <pre className="mt-1 max-h-48 overflow-auto rounded-sm bg-muted p-2 font-mono text-xs whitespace-pre-wrap">
              {hasArgs ? JSON.stringify(item.args, null, 2) : "{}"}
            </pre>
          </div>
          <div className="min-w-0">
            <p className="text-xs font-medium text-muted-foreground">{t("companion.tool.result")}</p>
            <p className="mt-1 text-xs text-pretty text-muted-foreground">{t("companion.tool.noResult")}</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
