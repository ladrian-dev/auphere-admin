"use client";

import { Archive, Pencil, Plus } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Field,
  Input,
  NativeSelect,
} from "@nexus/ui";

import { archiveAgentAction, renameAgentAction } from "@/app/(console)/clients/[ref]/agents/actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import { actionErrorText } from "@/lib/action-error";
import type { ClientAgent } from "@/lib/backend";

import { NewAgentDialog } from "./new-agent-dialog";

/** The tabs that act on ONE agent (spec 030); every other tab is the client's. */
export const AGENT_TABS = ["agent", "capabilities", "playground"] as const;

export function isAgentTab(pathname: string, base: string): boolean {
  return AGENT_TABS.some((tab) => pathname === `${base}/${tab}` || pathname.startsWith(`${base}/${tab}/`));
}

/** The API's closed vocabulary, in words (principle III). */
const ERRORS: Record<string, MessageKey> = {
  name_taken: "agents.error.name_taken",
  agent_has_channels: "agents.error.agent_has_channels",
  last_agent: "agents.error.last_agent",
};

/**
 * Which agent the tab acts on (spec 030, R14.5). Only on the tabs of one
 * agent — Agente, Habilidades, Playground —, kept in `?agent=` so a link
 * says what it shows. With one agent there is nothing to choose: only
 * «Nuevo agente», for whoever can create one.
 */
export function AgentSwitcher({ refId, agents, canWrite }: { refId: string; agents: ClientAgent[]; canWrite: boolean }) {
  const t = useT();
  const pathname = usePathname();
  const params = useSearchParams();
  const router = useRouter();
  const [creating, setCreating] = React.useState(false);
  const [renaming, setRenaming] = React.useState(false);
  const [archiving, setArchiving] = React.useState(false);
  const [archiveError, setArchiveError] = React.useState<string | null>(null);
  const base = `/clients/${encodeURIComponent(refId)}`;
  if (!isAgentTab(pathname, base)) return null;
  if (agents.length < 2 && !canWrite) return null;

  const principal = agents.find((a) => a.is_principal) ?? null;
  const current = agents.find((a) => a.id === params.get("agent") && !a.is_principal) ?? principal;

  function go(id: string | null) {
    const sp = new URLSearchParams(params.toString());
    if (id && id !== principal?.id) sp.set("agent", id);
    else sp.delete("agent");
    const qs = sp.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  }

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2" data-slot="agent-switcher">
      {agents.length > 1 ? (
        <NativeSelect
          size="sm"
          wrapperClassName="max-w-64"
          aria-label={t("agents.switcher.label")}
          value={current?.id ?? ""}
          onChange={(e) => go(e.target.value)}
        >
          {agents.map((a) => (
            <option key={a.id} value={a.id}>
              {a.active_version === null ? t("agents.switcher.unpublished", { name: a.name }) : a.name}
            </option>
          ))}
        </NativeSelect>
      ) : null}
      {canWrite && current && !current.is_principal ? (
        <>
          <Button type="button" variant="ghost" size="sm" onClick={() => setRenaming(true)}>
            <Pencil aria-hidden="true" />
            {t("agents.rename")}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => {
              // An agent that answers on a number cannot go: say so before
              // anyone confirms, instead of after.
              setArchiveError(current.channels.length > 0 ? t("agents.error.agent_has_channels") : null);
              setArchiving(true);
            }}
          >
            <Archive aria-hidden="true" />
            {t("agents.archive")}
          </Button>
        </>
      ) : null}
      {canWrite ? (
        <Button type="button" variant="outline" size="sm" onClick={() => setCreating(true)}>
          <Plus aria-hidden="true" />
          {t("agents.new")}
        </Button>
      ) : null}

      {canWrite ? (
        <NewAgentDialog
          refId={refId}
          open={creating}
          onOpenChange={setCreating}
          // The new agent is a draft: its own Agent tab is where it is finished.
          onCreated={(agent) => router.push(`${base}/agent?agent=${encodeURIComponent(agent.id)}`)}
        />
      ) : null}
      {canWrite && current && !current.is_principal ? (
        <>
          <RenameDialog key={current.id} refId={refId} agent={current} open={renaming} onOpenChange={setRenaming} />
          <ConfirmDialog
            open={archiving}
            onOpenChange={setArchiving}
            title={t("agents.archive.title", { name: current.name })}
            description={t("agents.archive.description")}
            confirmLabel={t("agents.archive")}
            destructive
            error={archiveError ?? undefined}
            onConfirm={async () => {
              if (current.channels.length > 0) return;
              const res = await archiveAgentAction({ ref: refId, agent: current.id });
              if (res.ok) {
                toast.success(t("agents.archive.done", { name: current.name }));
                setArchiving(false);
                go(null);
                return;
              }
              const known = res.code ? ERRORS[res.code] : undefined;
              setArchiveError(known ? t(known) : actionErrorText(res, t));
            }}
          />
        </>
      ) : null}
    </div>
  );
}

function RenameDialog({
  refId,
  agent,
  open,
  onOpenChange,
}: {
  refId: string;
  agent: ClientAgent;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const t = useT();
  const [name, setName] = React.useState(agent.name);
  const [error, setError] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) {
      setError(t("validation.required"));
      return;
    }
    startTransition(async () => {
      const res = await renameAgentAction({ ref: refId, agent: agent.id, name: name.trim() });
      if (res.ok) {
        toast.success(t("agents.rename.done", { name: res.data.name }));
        onOpenChange(false);
        return;
      }
      const known = res.code ? ERRORS[res.code] : undefined;
      if (known) setError(t(known));
      else toast.error(actionErrorText(res, t));
    });
  }

  function close(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setName(agent.name);
      setError(null);
    }
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("agents.rename.title")}</DialogTitle>
          <DialogDescription>{t("agents.rename.description")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} noValidate className="flex flex-col gap-4">
          <Field label={t("agents.new.name")} error={error ?? undefined}>
            {(a11y) => <Input {...a11y} value={name} maxLength={80} autoComplete="off" onChange={(e) => setName(e.target.value)} />}
          </Field>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => close(false)} disabled={pending}>
              {t("common.cancel")}
            </Button>
            <Button type="submit" loading={pending}>
              {t("common.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
