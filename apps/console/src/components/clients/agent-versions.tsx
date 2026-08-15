"use client";

import { FileText } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  ConfirmDialog,
  EmptyState,
  StatusBadge,
  Textarea,
  formatDateTime,
} from "@nexus/ui";

import { publishAgentAction, rollbackAgentAction, stageAgentAction } from "@/app/(console)/clients/actions";
import { useLocale, useT } from "@/i18n/client";
import type { AgentBundle, AgentVersion } from "@/lib/backend";

import { PromptDiff } from "./prompt-diff";

type Props = { refId: string; bundle: AgentBundle; canWrite: boolean };

export function AgentVersions({ refId, bundle, canWrite }: Props) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const active = bundle.versions.find((v) => v.version === bundle.active_version) ?? null;
  const [draft, setDraft] = React.useState<string>(active?.system_prompt ?? "");
  const [draftOpen, setDraftOpen] = React.useState(bundle.versions.length === 0);
  const [publishing, setPublishing] = React.useState<AgentVersion | null>(null);
  const [expanded, setExpanded] = React.useState<number | null>(null);
  const versions = [...bundle.versions].sort((a, b) => b.version - a.version);

  function saveDraft() {
    if (!draft.trim()) {
      toast.error(t("agent.promptTooShort"));
      return;
    }
    startTransition(async () => {
      const res = await stageAgentAction({ ref: refId, system_prompt: draft });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("agent.draft.saved", { v: res.data.version }));
      setDraftOpen(false);
      router.refresh();
    });
  }

  function rollback(v: AgentVersion) {
    startTransition(async () => {
      const res = await rollbackAgentAction({ ref: refId, version: v.version });
      if (!res.ok) return void toast.error(res.message);
      toast.success(t("agent.rolledBack", { v: v.version }));
      router.refresh();
    });
  }

  return (
    <div className="flex min-w-0 flex-col gap-4" aria-busy={pending}>
      {canWrite ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={() => setDraftOpen((o) => !o)} variant={draftOpen ? "secondary" : "default"}>
            {t("agent.draft.title")}
          </Button>
          {active ? <span className="text-sm text-muted-foreground">{t("agent.draft.from", { v: active.version })}</span> : null}
        </div>
      ) : null}

      {canWrite && draftOpen ? (
        <Card>
          <CardHeader>
            <CardTitle>{t("agent.draft.title")}</CardTitle>
            <CardDescription>{t("agent.draft.prompt")}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <Textarea
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="min-h-64 font-mono text-xs"
              aria-label={t("agent.draft.prompt")}
              spellCheck={false}
            />
            {active ? (
              <details className="text-sm">
                <summary className="cursor-pointer text-muted-foreground">{t("agent.diff")}</summary>
                <PromptDiff before={active.system_prompt} after={draft} noneLabel={t("agent.diff.none")} />
              </details>
            ) : null}
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setDraftOpen(false)}>
                {t("common.cancel")}
              </Button>
              <Button onClick={saveDraft} disabled={pending}>
                {t("agent.draft.save")}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {versions.length === 0 && !draftOpen ? (
        <EmptyState
          icon={FileText}
          title={t("agent.empty")}
          description={t("agent.empty.body")}
          action={canWrite ? <Button onClick={() => setDraftOpen(true)}>{t("agent.draft.title")}</Button> : undefined}
          readonly={!canWrite}
        />
      ) : null}

      {versions.length > 0 ? (
        <ol className="flex flex-col gap-2" aria-label={t("agent.versions")}>
          {versions.map((v) => {
            const isActive = v.version === bundle.active_version;
            const open = expanded === v.version;
            return (
              <li key={v.version} className="rounded-md bg-card p-4 ring-1 ring-foreground/10">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-semibold">v{v.version}</span>
                  <StatusBadge tone={isActive ? "positive" : v.status === "staged" ? "info" : "muted"}>
                    {isActive ? t("agent.active") : t(`status.${v.status}` as "status.staged")}
                  </StatusBadge>
                  <span className="min-w-0 truncate text-sm text-muted-foreground" title={v.created_by ?? undefined}>
                    {formatDateTime(v.created_at, locale)}
                    {v.created_by ? ` · ${t("agent.by", { who: v.created_by.replace(/^console:/, "") })}` : ""}
                  </span>
                  <span className="ml-auto flex flex-wrap gap-2">
                    <Button variant="ghost" size="sm" onClick={() => setExpanded(open ? null : v.version)} aria-expanded={open}>
                      {t("agent.viewPrompt")}
                    </Button>
                    {canWrite && !isActive && v.status === "staged" ? (
                      <Button size="sm" onClick={() => setPublishing(v)} disabled={pending}>
                        {t("agent.publish")}
                      </Button>
                    ) : null}
                    {canWrite && !isActive && v.status !== "staged" ? (
                      <Button size="sm" variant="outline" onClick={() => rollback(v)} disabled={pending}>
                        {t("agent.rollback")}
                      </Button>
                    ) : null}
                  </span>
                </div>
                {open ? (
                  <div className="mt-3 flex flex-col gap-2">
                    {v.tools.length ? (
                      <p className="text-xs text-muted-foreground">
                        {t("agent.tools")}: <span className="font-mono">{v.tools.join(", ")}</span>
                      </p>
                    ) : null}
                    <pre className="max-h-96 overflow-auto rounded-md bg-muted p-3 font-mono text-xs whitespace-pre-wrap">{v.system_prompt}</pre>
                    {active && !isActive ? (
                      <details className="text-sm">
                        <summary className="cursor-pointer text-muted-foreground">{t("agent.diff")}</summary>
                        <PromptDiff before={active.system_prompt} after={v.system_prompt} noneLabel={t("agent.diff.none")} />
                      </details>
                    ) : null}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>
      ) : null}

      <ConfirmDialog
        open={publishing !== null}
        onOpenChange={(o) => !o && setPublishing(null)}
        title={t("agent.publish.title", { v: publishing?.version ?? "" })}
        description={t("agent.publish.body")}
        confirmLabel={t("agent.publish")}
        cancelLabel={t("common.cancel")}
        onConfirm={async () => {
          if (!publishing) return;
          const res = await publishAgentAction({ ref: refId, version: publishing.version });
          if (!res.ok) {
            toast.error(res.message);
            return;
          }
          toast.success(t("agent.published", { v: publishing.version }));
          setPublishing(null);
          router.refresh();
        }}
      />
    </div>
  );
}
