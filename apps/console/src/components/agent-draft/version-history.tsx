"use client";

import { FileText } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, ConfirmDialog, EmptyState, ErrorState, Section, StatusBadge, formatDateTime } from "@nexus/ui";

import { publishAgentAction, rollbackAgentAction } from "@/app/(console)/clients/actions";
import { discardDraftAction } from "@/app/(console)/clients/[ref]/agent/actions";
import { PromptDiff } from "@/components/clients/prompt-diff";
import { type RowAction, RowActions } from "@/components/row-actions";
import { foldsIntoMenu } from "@/components/row-actions-rule";
import { useLocale, useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";
import type { AgentVersionEntry } from "@/lib/backend/agent-draft-types";

import { usePendingFields, useRequiredDraftEdits } from "./draft-edits";

type Props = {
  /** `null`: the history could not be read (the rest of the page still works). */
  entries: AgentVersionEntry[] | null;
  /** The instructions of each version, by client-wide `version`, when known. */
  prompts: Record<number, string>;
};

type Shown = "staged" | "active" | "archived" | "discarded";

function shownStatus(v: AgentVersionEntry): Shown {
  // Spec 047 (R3.5): a discarded draft stays in the history, never published.
  if (v.status === "archived" && v.published_at === null) return "discarded";
  return v.status;
}

const TONE: Record<Shown, "positive" | "info" | "muted"> = {
  active: "positive",
  staged: "info",
  archived: "muted",
  discarded: "muted",
};

/**
 * «v{n} de {agente}» with who wrote it and when, who published it, its note
 * and the version it started from (spec 047, historia 2, escenario 3). The
 * draft can be published or discarded from here; an earlier published
 * version can be brought back.
 *
 * Publishing waits for the pending changes to be saved: the button would
 * publish the draft without them, which is exactly the surprise the single
 * draft exists to avoid.
 */
export function AgentVersionHistory({ entries, prompts }: Props) {
  const ctx = useRequiredDraftEdits();
  const pending = usePendingFields();
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [expanded, setExpanded] = React.useState<number | null>(null);
  const [publishing, setPublishing] = React.useState<AgentVersionEntry | null>(null);
  const [rollingBack, setRollingBack] = React.useState<AgentVersionEntry | null>(null);
  const [discarding, setDiscarding] = React.useState<AgentVersionEntry | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const { draft, canWrite, refId, agentId } = ctx;
  const unsaved = Object.keys(pending).length > 0;
  const activePrompt = entries?.find((v) => v.status === "active");

  const title = t("agents.history.title", { agent: draft.agent_name });
  const description = t("agents.history.description");

  if (entries === null) {
    return (
      <Section title={title} description={description} flat headingLevel={2}>
        <ErrorState title={t("agents.history.error")} retryLabel={t("agents.history.retry")} onRetry={() => router.refresh()} />
      </Section>
    );
  }
  if (entries.length === 0) {
    return (
      <Section title={title} description={description} flat headingLevel={2}>
        <EmptyState icon={FileText} title={t("agents.history.empty")} description={t("agents.history.empty.body")} readonly={!canWrite} />
      </Section>
    );
  }

  function actionsFor(v: AgentVersionEntry): RowAction[] {
    const open = expanded === v.version;
    const out: RowAction[] = [];
    const status = shownStatus(v);
    if (canWrite && status === "staged") {
      out.push({ label: t("agent.publish"), onSelect: () => setPublishing(v), primary: true, disabled: unsaved });
      out.push({ label: t("agents.history.discard"), onSelect: () => setDiscarding(v) });
    }
    if (canWrite && status === "archived") {
      out.push({ label: t("agent.rollback"), onSelect: () => setRollingBack(v), primary: true });
    }
    if (prompts[v.version] !== undefined) {
      out.push({ label: open ? t("agent.hidePrompt") : t("agent.viewPrompt"), onSelect: () => setExpanded(open ? null : v.version) });
    }
    return out;
  }
  const menu = foldsIntoMenu(entries.reduce((sum, v) => sum + actionsFor(v).length, 0));

  async function publish(v: AgentVersionEntry) {
    const res = await publishAgentAction({ ref: refId, version: v.version, agent: agentId });
    if (!res.ok) return setError(actionErrorText(res, t));
    toast.success(t("agent.published", { v: v.number }));
    setPublishing(null);
    router.refresh();
  }

  async function rollback(v: AgentVersionEntry) {
    const res = await rollbackAgentAction({ ref: refId, version: v.version, agent: agentId });
    if (!res.ok) return setError(actionErrorText(res, t));
    toast.success(t("agent.rolledBack", { v: v.number }));
    setRollingBack(null);
    router.refresh();
  }

  async function discard() {
    const res = await discardDraftAction({ ref: refId, agent: agentId, revision: draft.revision });
    if (!res.ok) {
      // Someone wrote in between: what they wrote is what the page shows next.
      if (res.code === "revision_conflict") router.refresh();
      return setError(res.code === "revision_conflict" ? t("agents.draft.conflict.titleSomeone") : actionErrorText(res, t));
    }
    ctx.adopt(res.data);
    toast.success(t("agents.history.discarded"));
    setDiscarding(null);
    router.refresh();
  }

  return (
    <Section title={title} description={description} flat headingLevel={2}>
      <ol className="flex min-w-0 flex-col gap-2" aria-label={t("agents.history.list")}>
        {entries.map((v) => {
          const status = shownStatus(v);
          const open = expanded === v.version;
          const actions = actionsFor(v);
          return (
            <li key={v.version} className="min-w-0 rounded-md bg-card p-4 ring-1 ring-foreground/10" data-slot="agent-version">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="font-mono text-sm font-semibold">{t("agents.history.number", { n: v.number })}</span>
                <StatusBadge tone={TONE[status]}>{t(`agents.history.status.${status}`)}</StatusBadge>
                {v.base_number != null ? (
                  <span className="text-xs text-muted-foreground">{t("agents.history.from", { n: v.base_number })}</span>
                ) : null}
                <span className="min-w-0 truncate text-sm text-muted-foreground" title={v.author ?? undefined}>
                  {t("agents.history.written", { who: v.author ?? "—", when: formatDateTime(v.created_at, locale) })}
                </span>
                {actions.length ? (
                  <span className="ml-auto flex flex-wrap gap-2">
                    {menu ? (
                      <RowActions actions={actions} menu ariaLabel={t("agent.actions.aria", { v: v.number })} />
                    ) : (
                      actions.map((a) => (
                        <Button key={a.label} size="sm" variant={a.primary ? "default" : "ghost"} onClick={a.onSelect} disabled={a.disabled}>
                          {a.label}
                        </Button>
                      ))
                    )}
                  </span>
                ) : null}
              </div>
              <p className="mt-1 max-w-prose text-sm text-pretty">
                {v.change_note ? v.change_note : <span className="text-muted-foreground">{t("agents.history.noNote")}</span>}
              </p>
              {v.published_at && v.published_by ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("agents.history.publishedBy", { who: v.published_by, when: formatDateTime(v.published_at, locale) })}
                </p>
              ) : null}
              {status === "staged" && unsaved && canWrite ? (
                <p className="mt-1 text-xs text-muted-foreground">{t("agents.history.saveFirst")}</p>
              ) : null}
              {open ? (
                <div className="mt-3 flex min-w-0 flex-col gap-2">
                  <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 font-mono text-xs whitespace-pre-wrap">{prompts[v.version]}</pre>
                  {activePrompt && activePrompt.version !== v.version && prompts[activePrompt.version] !== undefined ? (
                    <details className="text-sm">
                      <summary className="cursor-pointer text-muted-foreground">{t("agent.diff")}</summary>
                      <PromptDiff before={prompts[activePrompt.version] ?? ""} after={prompts[v.version] ?? ""} noneLabel={t("agent.diff.none")} />
                    </details>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ol>

      <ConfirmDialog
        open={publishing !== null}
        onOpenChange={(o) => {
          if (!o) setPublishing(null);
          setError(null);
        }}
        title={t("agent.publish.title", { v: publishing?.number ?? "" })}
        description={t("agent.publish.body")}
        confirmLabel={t("agent.publish")}
        cancelLabel={t("common.cancel")}
        error={error}
        onConfirm={async () => {
          if (publishing) await publish(publishing);
        }}
      />
      <ConfirmDialog
        open={rollingBack !== null}
        onOpenChange={(o) => {
          if (!o) setRollingBack(null);
          setError(null);
        }}
        title={t("agent.rollback.title", { v: rollingBack?.number ?? "" })}
        description={t("agent.rollback.body", { v: rollingBack?.number ?? "", active: draft.active_number ?? "" })}
        confirmLabel={t("agent.rollback.confirm")}
        cancelLabel={t("common.cancel")}
        error={error}
        onConfirm={async () => {
          if (rollingBack) await rollback(rollingBack);
        }}
      />
      <ConfirmDialog
        open={discarding !== null}
        onOpenChange={(o) => {
          if (!o) setDiscarding(null);
          setError(null);
        }}
        title={t("agents.history.discard.title", { n: discarding?.number ?? "" })}
        description={t("agents.history.discard.body", { agent: draft.agent_name })}
        confirmLabel={t("agents.history.discard.confirm")}
        cancelLabel={t("common.cancel")}
        destructive
        error={error}
        onConfirm={discard}
      />
    </Section>
  );
}
