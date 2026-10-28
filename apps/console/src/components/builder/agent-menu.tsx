"use client";

import { MoreHorizontal } from "lucide-react";
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
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Field,
  Input,
  Label,
  NativeSelect,
} from "@nexus/ui";

import {
  archiveAgentWithAction,
  pauseAgentAction,
  renameAgentLifeAction,
  restoreAgentAction,
  resumeAgentAction,
  setDefaultAgentAction,
} from "@/app/(console)/clients/[ref]/agents/life-actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { ClientAgent } from "@/lib/backend";
import type { AgentHeader, ChannelDestination } from "@/lib/backend/agent-life-types";

import type { Result } from "./builder-model";
import { destinations, menuItems, otherLiveAgents } from "./life-model";

type Ids = { ref: string; agent: string };
export type AgentLifeActions = {
  rename: (body: Ids & { name: string }) => Promise<Result<ClientAgent>>;
  pause: (body: Ids & { confirm?: boolean }) => Promise<Result<AgentHeader>>;
  resume: (body: Ids) => Promise<Result<AgentHeader>>;
  archive: (body: Ids & { channels: ChannelDestination[] }) => Promise<Result<AgentHeader>>;
  restore: (body: Ids) => Promise<Result<AgentHeader>>;
  makeDefault: (body: Ids) => Promise<Result<AgentHeader>>;
};

export const LIFE_ACTIONS: AgentLifeActions = {
  rename: (body) => renameAgentLifeAction(body),
  pause: (body) => pauseAgentAction(body),
  resume: (body) => resumeAgentAction(body),
  archive: (body) => archiveAgentWithAction(body),
  restore: (body) => restoreAgentAction(body),
  makeDefault: (body) => setDefaultAgentAction(body),
};

/**
 * El ⋯ de la cabecera de un agente (spec 047, historias 19 y 20; requisitos
 * 26 a 28): solo lo que esta persona puede hacer (`allowed`, §V) —renombrar,
 * pausar o reanudar, hacerlo agente por defecto, archivar o restaurar—.
 *
 * Pausar no pide confirmación salvo que haya conversaciones en curso, y
 * entonces dice cuántas (27.8). Archivar pide en la misma acción quién atiende
 * cada uno de sus números, otro agente o «Dejar en pausa» (28.1), y si es el
 * agente por defecto pide antes elegir otro (28.4). Restaurar lo devuelve en
 * pausa (28.2).
 */
export function AgentMenu({
  refId,
  header,
  agents,
  onHeader,
  onArchived,
  actions = LIFE_ACTIONS,
}: {
  refId: string;
  header: AgentHeader;
  /** Los agentes del cliente: los números de este y a quién pueden ir. */
  agents: readonly ClientAgent[];
  onHeader: (header: AgentHeader) => void;
  onArchived?: (header: AgentHeader) => void;
  actions?: AgentLifeActions;
}) {
  const t = useT();
  const ids = { ref: refId, agent: header.id };
  const [renaming, setRenaming] = React.useState(false);
  const [confirmPause, setConfirmPause] = React.useState<number | null>(null);
  const [archiving, setArchiving] = React.useState(false);
  const items = menuItems(header);
  if (!items.length) return null;

  const fail = () => toast.error(t("builder.life.error"));

  async function pause(confirm = false) {
    const res = await actions.pause({ ...ids, ...(confirm ? { confirm: true } : {}) });
    if (res.ok) {
      setConfirmPause(null);
      onHeader(res.data);
      toast.success(t("builder.life.paused.toast", { name: header.name }));
      return;
    }
    if (res.code === "confirm_required") {
      const n = Number(res.info?.open_conversations ?? 0);
      setConfirmPause(Number.isFinite(n) ? n : 0);
      return;
    }
    fail();
  }

  async function resume() {
    const res = await actions.resume(ids);
    if (!res.ok) return fail();
    onHeader(res.data);
    toast.success(t("builder.life.resumed", { name: header.name }));
  }

  async function restore() {
    const res = await actions.restore(ids);
    if (!res.ok) return fail();
    onHeader(res.data);
    toast.success(t("builder.life.restored", { name: header.name }));
  }

  async function makeDefault() {
    const res = await actions.makeDefault(ids);
    if (!res.ok) return fail();
    onHeader(res.data);
    toast.success(t("builder.life.defaulted", { name: header.name }));
  }

  function run(action: (typeof items)[number]) {
    if (action === "rename") setRenaming(true);
    else if (action === "pause") void pause();
    else if (action === "resume") void resume();
    else if (action === "make_default") void makeDefault();
    else if (action === "archive") setArchiving(true);
    else if (action === "restore") void restore();
  }

  const [first, ...rest] = items;
  const label = (a: (typeof items)[number]) => t(`builder.life.action.${a}` as MessageKey);

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label={t("builder.life.menu", { name: header.name })}
          className="inline-flex size-8 shrink-0 items-center justify-center rounded-sm outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
          data-slot="agent-menu"
        >
          <MoreHorizontal aria-hidden="true" className="size-4" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          {first ? (
            <DropdownMenuItem onClick={() => run(first)} className="font-medium">
              {label(first)}
            </DropdownMenuItem>
          ) : null}
          {rest.length ? <DropdownMenuSeparator /> : null}
          {rest.map((a) => (
            <DropdownMenuItem key={a} onClick={() => run(a)}>
              {label(a)}
            </DropdownMenuItem>
          ))}
        </DropdownMenuContent>
      </DropdownMenu>

      {renaming ? (
        <RenameDialog
          name={header.name}
        onOpenChange={setRenaming}
        onSave={async (name) => {
          const res = await actions.rename({ ...ids, name });
          if (res.ok) {
            setRenaming(false);
            onHeader({ ...header, name: res.data.name });
            toast.success(t("builder.life.renamed", { name: res.data.name }));
          }
          return res;
        }}
        />
      ) : null}

      <ConfirmDialog
        open={confirmPause !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmPause(null);
        }}
        title={t("builder.life.pause.title", { name: header.name })}
        description={
          confirmPause === 1 ? t("builder.life.pause.open.one") : t("builder.life.pause.open.other", { n: confirmPause ?? 0 })
        }
        confirmLabel={t("builder.life.pause.confirm")}
        cancelLabel={t("builder.life.cancel")}
        onConfirm={() => pause(true)}
      />

      {archiving ? (
        <ArchiveDialog
          refId={refId}
          header={header}
          agents={agents}
          actions={actions}
          onClose={() => setArchiving(false)}
          onHeader={onHeader}
          onArchived={(archived) => {
            setArchiving(false);
            toast.success(t("builder.life.archived.toast", { name: header.name }));
            onArchived?.(archived);
          }}
        />
      ) : null}
    </>
  );
}

function RenameDialog({
  name,
  onOpenChange,
  onSave,
}: {
  name: string;
  onOpenChange: (open: boolean) => void;
  onSave: (name: string) => Promise<Result<ClientAgent>>;
}) {
  const t = useT();
  const [value, setValue] = React.useState(name);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const clean = value.split(/\s+/).filter(Boolean).join(" ");
    if (!clean || clean.length > 40) {
      setError(t("builder.life.rename.required"));
      return;
    }
    setBusy(true);
    const res = await onSave(clean);
    setBusy(false);
    if (!res.ok) setError(res.code === "name_taken" ? t("builder.new.error.name_taken") : t("builder.life.error"));
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={submit} noValidate className="grid min-w-0 gap-4">
          <DialogHeader>
            <DialogTitle>{t("builder.life.rename.title", { name })}</DialogTitle>
          </DialogHeader>
          <Field label={t("builder.life.rename.field")} error={error ?? undefined} required>
            {(a11y) => <Input {...a11y} value={value} maxLength={40} autoComplete="off" onChange={(e) => setValue(e.target.value)} />}
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              {t("builder.life.cancel")}
            </Button>
            <Button type="submit" loading={busy}>
              {t("builder.life.rename.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** Archivar: el destino de cada número y, si es el agente por defecto, otro antes. */
function ArchiveDialog({
  refId,
  header,
  agents,
  actions,
  onClose,
  onHeader,
  onArchived,
}: {
  refId: string;
  header: AgentHeader;
  agents: readonly ClientAgent[];
  actions: AgentLifeActions;
  onClose: () => void;
  onHeader: (header: AgentHeader) => void;
  onArchived: (header: AgentHeader) => void;
}) {
  const t = useT();
  const base = React.useId();
  const channels = agents.find((a) => a.id === header.id)?.channels ?? [];
  const others = otherLiveAgents(agents, header.id);
  const [isDefault, setIsDefault] = React.useState(header.is_default);
  const [newDefault, setNewDefault] = React.useState(others[0]?.id ?? "");
  const [chosen, setChosen] = React.useState<Record<string, string>>({});
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function changeDefault() {
    if (!newDefault) return;
    setBusy(true);
    setError(null);
    const res = await actions.makeDefault({ ref: refId, agent: newDefault });
    setBusy(false);
    if (!res.ok) {
      setError(t("builder.life.error"));
      return;
    }
    setIsDefault(false);
    onHeader({ ...header, is_default: false });
    toast.success(t("builder.life.defaulted", { name: res.data.name }));
  }

  async function archive(event: React.FormEvent) {
    event.preventDefault();
    const list = destinations(channels, chosen);
    if (!list) {
      setError(t("builder.life.archive.error.destination"));
      return;
    }
    setBusy(true);
    setError(null);
    const res = await actions.archive({ ref: refId, agent: header.id, channels: list });
    setBusy(false);
    if (res.ok) return onArchived(res.data);
    if (res.code === "default_agent_required") {
      setIsDefault(true);
      setError(t("builder.life.archive.default", { name: header.name }));
    } else if (res.code === "channel_destination_required") setError(t("builder.life.archive.error.destination"));
    else if (res.code === "unknown_target_agent") setError(t("builder.life.archive.error.target"));
    else setError(t("builder.life.error"));
  }

  return (
    <Dialog
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={archive} noValidate className="grid min-w-0 gap-4" data-slot="archive-agent">
          <DialogHeader>
            <DialogTitle>{t("builder.life.archive.title", { name: header.name })}</DialogTitle>
            <DialogDescription>{t("builder.life.archive.body")}</DialogDescription>
          </DialogHeader>

          {isDefault ? (
            <div className="grid min-w-0 gap-2 rounded-md border border-status-warning-border bg-status-warning-bg p-3 text-sm" data-slot="archive-default">
              <p className="text-pretty">{t("builder.life.archive.default", { name: header.name })}</p>
              {others.length ? (
                <div className="flex min-w-0 flex-wrap items-end gap-2">
                  <div className="grid min-w-0 flex-1 gap-1">
                    <Label htmlFor={`${base}-default`}>{t("builder.life.archive.defaultPick")}</Label>
                    <NativeSelect id={`${base}-default`} value={newDefault} onChange={(e) => setNewDefault(e.target.value)} wrapperClassName="w-full">
                      {others.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name}
                        </option>
                      ))}
                    </NativeSelect>
                  </div>
                  <Button type="button" variant="outline" onClick={() => void changeDefault()} loading={busy}>
                    {t("builder.life.archive.defaultSave")}
                  </Button>
                </div>
              ) : (
                <p className="text-pretty">{t("builder.life.archive.onlyAgent")}</p>
              )}
            </div>
          ) : (
            <fieldset className="grid min-w-0 gap-3">
              <legend className="mb-2 text-sm font-medium text-muted-foreground">{t("builder.life.archive.channels")}</legend>
              {channels.length ? (
                channels.map((ch) => (
                  <div key={ch.id} className="grid min-w-0 gap-1">
                    <Label htmlFor={`${base}-${ch.id}`}>{t("builder.life.archive.channel", { number: ch.display })}</Label>
                    <NativeSelect
                      id={`${base}-${ch.id}`}
                      value={chosen[ch.id] ?? ""}
                      onChange={(e) => setChosen((prev) => ({ ...prev, [ch.id]: e.target.value }))}
                      wrapperClassName="w-full"
                      required
                    >
                      <option value="" disabled>
                        {t("builder.life.archive.channels")}
                      </option>
                      {others.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name}
                        </option>
                      ))}
                      <option value="pause">{t("builder.life.archive.pause")}</option>
                    </NativeSelect>
                  </div>
                ))
              ) : (
                <p className="text-sm text-pretty text-muted-foreground">{t("builder.life.archive.none")}</p>
              )}
            </fieldset>
          )}

          {error ? (
            <p role="alert" className="text-sm text-destructive text-pretty">
              {error}
            </p>
          ) : null}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
              {t("builder.life.cancel")}
            </Button>
            {!isDefault ? (
              <Button type="submit" variant="destructive" loading={busy}>
                {t("builder.life.archive.confirm")}
              </Button>
            ) : null}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
