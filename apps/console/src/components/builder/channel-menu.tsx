"use client";

import { MoreHorizontal } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
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
} from "@nexus/ui";

import { moveChannelAction, pauseChannelAction, resumeChannelAction } from "@/app/(console)/clients/[ref]/agents/channel-actions";
import { disconnectChannelAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { ChannelDetail } from "@/lib/backend/channels";
import type { AgentRef, ChannelPage } from "@/lib/backend/channel-config-types";

import type { Result } from "./builder-model";
import { channelHref, channelMenuItems } from "./channel-model";

type ChannelIds = { ref: string; channel: string };
export type ChannelMenuActions = {
  move: (body: ChannelIds & { to: string }) => Promise<Result<ChannelPage>>;
  pause: (body: ChannelIds) => Promise<Result<ChannelPage>>;
  resume: (body: ChannelIds) => Promise<Result<ChannelPage>>;
  disconnect: (body: { ref: string; channelId: string }) => Promise<Result<ChannelDetail>>;
};

export const CHANNEL_MENU_ACTIONS: ChannelMenuActions = {
  move: (body) => moveChannelAction(body),
  pause: (body) => pauseChannelAction(body),
  resume: (body) => resumeChannelAction(body),
  disconnect: (body) => disconnectChannelAction(body),
};

/** Lo que el ⋯ necesita de un canal: su número, lo permitido y a quién puede pasar. */
export type MenuChannel = Pick<ChannelPage, "id" | "identifier" | "allowed" | "move_targets">;

/**
 * El ⋯ de cada canal (spec 047, requisito 34.1): «Configuración», «Pasar a
 * otro agente» (si hay otros agentes que no son borradores), «Pausar este
 * canal» o «Reanudar este canal» y «Desconectar». Solo lo que la API permite
 * (`allowed`, §V): a quien no puede, ni el ⋯.
 *
 * Pasar a otro agente vale desde el siguiente mensaje y conserva la
 * configuración y las conversaciones (34.2). Desconectar pide confirmación y
 * conserva el historial; si Meta no confirma la baja, quien llama enseña
 * «Reintentar» con lo que devuelve `onDisconnected` (34.3).
 */
export function ChannelMenu({
  refId,
  agentId,
  channel,
  here = false,
  onChanged,
  onMoved,
  onDisconnected,
  actions = CHANNEL_MENU_ACTIONS,
}: {
  refId: string;
  /** El agente que lo atiende ahora: su página cuelga de él. */
  agentId: string;
  channel: MenuChannel;
  /** En la propia página del canal, sin «Configuración». */
  here?: boolean;
  onChanged?: (page: ChannelPage) => void;
  onMoved?: (page: ChannelPage, to: AgentRef) => void;
  onDisconnected?: (pending: string[]) => void;
  actions?: ChannelMenuActions;
}) {
  const t = useT();
  const ids = { ref: refId, channel: channel.id };
  const [moving, setMoving] = React.useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = React.useState(false);
  const [disconnectError, setDisconnectError] = React.useState<string | null>(null);
  const items = channelMenuItems(channel.allowed, { here });
  if (!items.length) return null;

  const fail = () => toast.error(t("builder.channel.error"));

  async function pause() {
    const res = await actions.pause(ids);
    if (!res.ok) return fail();
    toast.success(t("builder.channel.paused", { number: channel.identifier }));
    onChanged?.(res.data);
  }

  async function resume() {
    const res = await actions.resume(ids);
    if (!res.ok) return fail();
    toast.success(t("builder.channel.resumed", { number: channel.identifier }));
    onChanged?.(res.data);
  }

  async function disconnect() {
    setDisconnectError(null);
    const res = await actions.disconnect({ ref: refId, channelId: channel.id });
    if (!res.ok) {
      setDisconnectError(res.status === 401 || res.status === 403 ? t("common.forbidden") : t("builder.channel.error"));
      return;
    }
    setConfirmDisconnect(false);
    toast.success(t("builder.channel.disconnect.done", { number: channel.identifier }));
    onDisconnected?.(res.data.unlink_pending ?? []);
  }

  const label = (a: (typeof items)[number]) => t(`builder.channel.action.${a}` as MessageKey);
  const item = (a: (typeof items)[number], bold = false) => {
    const className = bold ? "font-medium" : undefined;
    if (a === "configure") {
      return (
        <DropdownMenuItem key={a} render={<Link href={channelHref(refId, agentId, channel.id)} />} className={className}>
          {label(a)}
        </DropdownMenuItem>
      );
    }
    const run = a === "move" ? () => setMoving(true) : a === "pause" ? () => void pause() : a === "resume" ? () => void resume() : () => setConfirmDisconnect(true);
    return (
      <DropdownMenuItem key={a} onClick={run} variant={a === "disconnect" ? "destructive" : undefined} className={className}>
        {label(a)}
      </DropdownMenuItem>
    );
  };
  const [first, ...rest] = items;

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          aria-label={t("builder.channel.menu", { number: channel.identifier })}
          className="inline-flex size-8 shrink-0 items-center justify-center rounded-sm outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring"
          data-slot="channel-menu"
        >
          <MoreHorizontal aria-hidden="true" className="size-4" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          {first ? item(first, true) : null}
          {rest.length ? <DropdownMenuSeparator /> : null}
          {rest.map((a) => item(a))}
        </DropdownMenuContent>
      </DropdownMenu>

      {moving ? (
        <MoveDialog
          number={channel.identifier}
          targets={channel.move_targets}
          onClose={() => setMoving(false)}
          onMove={async (to) => {
            const res = await actions.move({ ...ids, to: to.id });
            if (!res.ok) return res.code === "unknown_target_agent" ? t("builder.channel.move.error.target") : t("builder.channel.error");
            setMoving(false);
            toast.success(t("builder.channel.move.done", { number: channel.identifier, name: to.name }));
            onMoved?.(res.data, to);
            return null;
          }}
        />
      ) : null}

      <ConfirmDialog
        open={confirmDisconnect}
        onOpenChange={(open) => {
          setConfirmDisconnect(open);
          if (!open) setDisconnectError(null);
        }}
        title={t("builder.channel.disconnect.title", { number: channel.identifier })}
        description={t("builder.channel.disconnect.body")}
        confirmLabel={t("builder.channel.disconnect.confirm")}
        cancelLabel={t("builder.channel.cancel")}
        destructive
        error={disconnectError ?? undefined}
        onConfirm={disconnect}
      />
    </>
  );
}

/** «Pasar a otro agente»: los agentes que no son borradores (34.1). */
function MoveDialog({
  number,
  targets,
  onClose,
  onMove,
}: {
  number: string;
  targets: AgentRef[];
  onClose: () => void;
  /** Devuelve el texto del error, o `null` si se pasó. */
  onMove: (to: AgentRef) => Promise<string | null>;
}) {
  const t = useT();
  const base = React.useId();
  const [chosen, setChosen] = React.useState(targets[0]?.id ?? "");
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const to = targets.find((a) => a.id === chosen);
    if (!to) return;
    setBusy(true);
    setError(null);
    const failed = await onMove(to);
    setBusy(false);
    if (failed) setError(failed);
  }

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="sm:max-w-md">
        <form onSubmit={submit} noValidate className="grid min-w-0 gap-4" data-slot="move-channel">
          <DialogHeader>
            <DialogTitle>{t("builder.channel.move.title", { number })}</DialogTitle>
            <DialogDescription>{t("builder.channel.move.body")}</DialogDescription>
          </DialogHeader>
          <fieldset className="grid min-w-0 gap-2">
            <legend className="mb-1 text-sm font-medium">{t("builder.channel.move.field")}</legend>
            {targets.map((a) => (
              <label key={a.id} className="flex min-h-6 min-w-0 items-center gap-2 text-sm">
                <input
                  type="radio"
                  name={`${base}-to`}
                  value={a.id}
                  className="size-4 shrink-0 accent-primary"
                  checked={chosen === a.id}
                  onChange={() => setChosen(a.id)}
                />
                <span className="min-w-0 break-words">{a.name}</span>
              </label>
            ))}
          </fieldset>
          {error ? (
            <p role="alert" className="text-sm text-pretty text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
              {t("builder.channel.cancel")}
            </Button>
            <Button type="submit" loading={busy}>
              {t("builder.channel.move.confirm")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Desconectado, pero Meta no confirmó la baja (34.3): se dice y se ofrece
 * «Reintentar», que vuelve a llamar a desconectar (termina lo que faltó).
 */
export function UnlinkPending({
  refId,
  channelId,
  number,
  canWrite,
  onDone,
  disconnect = CHANNEL_MENU_ACTIONS.disconnect,
}: {
  refId: string;
  channelId: string;
  number: string;
  canWrite: boolean;
  onDone: () => void;
  disconnect?: ChannelMenuActions["disconnect"];
}) {
  const t = useT();
  const [busy, setBusy] = React.useState(false);

  async function retry() {
    setBusy(true);
    const res = await disconnect({ ref: refId, channelId });
    setBusy(false);
    if (!res.ok) return void toast.error(t("builder.channel.error"));
    if ((res.data.unlink_pending ?? []).length) return void toast.warning(t("builder.channel.pending.body", { number }));
    toast.success(t("builder.channel.pending.done"));
    onDone();
  }

  return (
    <Callout
      tone="warning"
      title={t("builder.channel.pending.title")}
      action={
        canWrite ? (
          <Button size="sm" variant="outline" onClick={() => void retry()} loading={busy}>
            {t("builder.channel.pending.retry")}
          </Button>
        ) : undefined
      }
    >
      {t("builder.channel.pending.body", { number })}
    </Callout>
  );
}
