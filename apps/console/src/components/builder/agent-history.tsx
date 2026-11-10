"use client";

import { RotateCcw } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, ConfirmDialog, StatusBadge, formatDateTime, formatNumber } from "@nexus/ui";

import { historyAction, restoreVersionAction } from "@/app/(console)/clients/[ref]/agents/quality-actions";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { HistoryEntry, RestoreResult } from "@/lib/backend/agent-quality-types";

import type { Result } from "./builder-model";
import { cleanActor, partKey } from "./quality-model";

type Ids = { ref: string; agent: string };
export type HistoryActions = {
  load: (body: Ids) => Promise<Result<HistoryEntry[]>>;
  restore: (body: Ids & { number: number }) => Promise<Result<RestoreResult>>;
};

const SERVER_ACTIONS: HistoryActions = {
  load: (body) => historyAction(body),
  restore: (body) => restoreVersionAction(body),
};

const STATUS_TONE: Record<string, "positive" | "info" | "muted"> = { active: "positive", staged: "info", archived: "muted" };

/**
 * El historial del agente (spec 047, historia 9; requisito 24.2 y 24.3): cada
 * versión con su número, quién la guardó y cuándo, su nota, lo que cambió
 * respecto a la anterior, cómo le fue en las pruebas y, si se guardó saltando
 * la puerta, el motivo. «Restaurar» una versión anterior crea un borrador con
 * ella, que pasa las pruebas antes de llegar a clientes. Quien solo lee no ve
 * «Restaurar» (§V).
 */
export function AgentHistory({
  refId,
  agentId,
  history: initial,
  canWrite,
  refreshKey = 0,
  onRestored,
  actions = SERVER_ACTIONS,
}: {
  refId: string;
  agentId: string;
  /** `null` si no se pudo leer. */
  history: HistoryEntry[] | null;
  canWrite: boolean;
  refreshKey?: number;
  onRestored?: () => void;
  actions?: HistoryActions;
}) {
  const t = useT();
  const ids = React.useMemo(() => ({ ref: refId, agent: agentId }), [refId, agentId]);
  const [history, setHistory] = React.useState(initial);
  const [asking, setAsking] = React.useState<number | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const reload = React.useCallback(async () => {
    const res = await actions.load(ids);
    if (res.ok) setHistory(res.data);
  }, [actions, ids]);

  const seen = React.useRef(refreshKey);
  React.useEffect(() => {
    if (seen.current === refreshKey) return;
    seen.current = refreshKey;
    void reload();
  }, [refreshKey, reload]);

  async function restore(number: number) {
    setError(null);
    const res = await actions.restore({ ...ids, number });
    if (!res.ok) {
      setError(res.status === 401 || res.status === 403 ? t("common.forbidden") : t("builder.history.restore.failed"));
      return;
    }
    setAsking(null);
    toast.success(t("builder.history.restored", { n: res.data.restored_from }));
    await reload();
    onRestored?.();
  }

  if (!history) {
    return (
      <div className="flex min-w-0 flex-wrap items-center gap-3 text-sm" data-slot="agent-history">
        <p className="text-muted-foreground">{t("builder.history.error")}</p>
        <Button size="sm" variant="outline" onClick={() => void reload()}>
          {t("builder.suite.retry")}
        </Button>
      </div>
    );
  }

  return (
    <div className="grid min-w-0 gap-3" data-slot="agent-history">
      <p className="text-sm text-pretty text-muted-foreground">{t("builder.history.intro")}</p>
      {!history.length ? <p className="text-sm text-muted-foreground">{t("builder.history.empty")}</p> : null}
      <ol className="grid min-w-0 gap-2">
        {history.map((entry) => (
          <VersionRow
            key={entry.number}
            entry={entry}
            canRestore={canWrite && entry.status === "archived"}
            onRestore={() => {
              setError(null);
              setAsking(entry.number);
            }}
          />
        ))}
      </ol>
      <ConfirmDialog
        open={asking !== null}
        onOpenChange={(open) => {
          if (!open) setAsking(null);
        }}
        title={t("builder.history.restore.title", { n: asking ?? "" })}
        description={t("builder.history.restore.body", { n: asking ?? "" })}
        confirmLabel={t("builder.history.restore")}
        cancelLabel={t("builder.publish.cancel")}
        error={error ?? undefined}
        onConfirm={() => (asking !== null ? restore(asking) : undefined)}
      />
    </div>
  );
}

function VersionRow({ entry, canRestore, onRestore }: { entry: HistoryEntry; canRestore: boolean; onRestore: () => void }) {
  const t = useT();
  const locale = useLocale();
  const titleId = React.useId();
  const when = entry.published_at ?? entry.created_at;
  const who = entry.published_by ?? entry.author ?? "";
  // Solo las partes con palabra: `mode` o `schema_version` son del formato,
  // no algo que el partner cambió (recorrido UI de la 047).
  const parts = [...new Set(entry.changed.flatMap((p) => (partKey(p) ? [t(partKey(p) as MessageKey)] : [])))];
  const statusKey = (["active", "staged", "archived"].includes(entry.status) ? `builder.history.status.${entry.status}` : null) as MessageKey | null;
  return (
    <li aria-labelledby={titleId} className="grid min-w-0 gap-2 rounded-md border border-border p-3" data-slot="history-entry" data-status={entry.status}>
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
        <div className="grid min-w-0 flex-1 basis-48 gap-1">
          <span className="flex min-w-0 flex-wrap items-center gap-2">
            <span id={titleId} className="text-sm font-semibold tabular-nums">
              {t("builder.history.version", { n: entry.number })}
            </span>
            {statusKey ? <StatusBadge tone={STATUS_TONE[entry.status] ?? "muted"}>{t(statusKey)}</StatusBadge> : null}
          </span>
          <span className="text-xs text-muted-foreground">{t("builder.history.by", { who: cleanActor(who), when: formatDateTime(when, locale) })}</span>
        </div>
        {canRestore ? (
          <Button size="sm" variant="outline" onClick={onRestore} aria-label={t("builder.history.restore.label", { n: entry.number })}>
            <RotateCcw aria-hidden="true" />
            {t("builder.history.restore")}
          </Button>
        ) : null}
      </div>
      {entry.note ? <p className="text-sm text-pretty break-words">{entry.note}</p> : null}
      {parts.length ? <p className="text-xs text-pretty text-muted-foreground">{t("builder.history.changed", { parts: parts.join(", ") })}</p> : null}
      {entry.tests?.rate != null ? <p className="text-xs text-muted-foreground">{t("builder.history.tests", { rate: formatNumber(entry.tests.rate, locale, { maximumFractionDigits: 1 }) })}</p> : null}
      {entry.override_reason ? (
        <p className="text-xs text-pretty break-words text-status-warning-text" data-slot="history-override">
          {t("builder.history.override", { reason: entry.override_reason })}
        </p>
      ) : null}
    </li>
  );
}

