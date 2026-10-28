"use client";

import { Bot, MessageCircle } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { ConfirmDialog, EmptyState, ErrorState, PageHeader, StatusBadge } from "@nexus/ui";

import {
  pauseAgentAction,
  pauseChannelAction,
  reloadAgentsAction,
  resumeAgentAction,
  resumeChannelAction,
} from "@/app/(console)/agentes/actions";
import type { Result } from "@/components/builder/builder-model";
import { channelStateText } from "@/components/builder/channel-model";
import { visibleText, visibleTone } from "@/components/builder/life-model";
import { RowActions, type RowAction } from "@/components/row-actions";
import { foldsIntoMenu } from "@/components/row-actions-rule";
import { useT } from "@/i18n/client";
import type { LiteAgent, LiteAgentChannel, LiteAgents } from "@/lib/backend/lite-agents";

import { pauseLine } from "./lite-agents-model";

export type LiteAgentsActions = {
  reload: () => Promise<Result<LiteAgents>>;
  pauseAgent: (body: { id: string; confirm: boolean }) => Promise<Result<LiteAgent>>;
  resumeAgent: (body: { id: string }) => Promise<Result<LiteAgent>>;
  pauseChannel: (body: { id: string }) => Promise<Result<LiteAgentChannel>>;
  resumeChannel: (body: { id: string }) => Promise<Result<LiteAgentChannel>>;
};

const SERVER_ACTIONS: LiteAgentsActions = {
  reload: () => reloadAgentsAction(),
  pauseAgent: (b) => pauseAgentAction(b),
  resumeAgent: (b) => resumeAgentAction(b),
  pauseChannel: (b) => pauseChannelAction(b),
  resumeChannel: (b) => resumeChannelAction(b),
};

type Confirm = { kind: "agent"; agent: LiteAgent; open: number } | { kind: "channel"; agent: LiteAgent; channel: LiteAgentChannel };

type Failure = Extract<Result<unknown>, { ok: false }>;

/**
 * «Agentes» de la consola lite (spec 047, T168; requisitos 50.1 y 50.2): el
 * estado de cada agente del negocio con los textos y tonos de toda la consola
 * (25.5), sus números con el suyo, y «Pausar» o «Reanudar» los dos. Pausar
 * siempre se confirma, diciendo cuántas conversaciones en curso pasan a la
 * Bandeja (27.8). Una pausa del sistema (sin saldo, el tope) no se quita aquí:
 * se dice por qué y cuándo vuelve (§V, sin botones que no hacen nada).
 *
 * Crear, archivar, publicar o cambiar las instrucciones no existen aquí (50.3).
 * Estados: error con reintento, vacío e ideal; el de carga es `loading.tsx`.
 */
export function LiteAgentsView({ initial, actions = SERVER_ACTIONS }: { initial: LiteAgents | null; actions?: LiteAgentsActions }) {
  const t = useT();
  const [data, setData] = React.useState(initial);
  const [reloading, startReload] = React.useTransition();
  const [confirm, setConfirmState] = React.useState<Confirm | null>(null);
  const [busy, setBusy] = React.useState<string | null>(null);
  // El modal se abre desde un botón sin `DialogTrigger`: al cerrarlo, el foco
  // vuelve a quien lo abrió (47.5), si sigue en la página.
  const opener = React.useRef<HTMLElement | null>(null);

  function setConfirm(next: Confirm | null) {
    if (next && !confirm) opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setConfirmState(next);
    if (!next) {
      const back = opener.current;
      opener.current = null;
      restoreFocus(back);
    }
  }

  const items = data?.items ?? [];
  const menu = foldsIntoMenu(items.reduce((n, a) => n + a.allowed.length, 0));

  function retry() {
    startReload(async () => {
      const res = await actions.reload();
      if (res.ok) setData(res.data);
      else toast.error(t("lite.agents.error.load"));
    });
  }

  function putAgent(next: LiteAgent) {
    setData((d) => (d ? { items: d.items.map((a) => (a.id === next.id ? next : a)) } : d));
  }

  function putChannel(agentId: string, next: LiteAgentChannel) {
    setData((d) =>
      d ? { items: d.items.map((a) => (a.id === agentId ? { ...a, channels: a.channels.map((c) => (c.id === next.id ? next : c)) } : a)) } : d,
    );
  }

  function problem(res: Failure): string {
    if (res.status === 409 && res.code === "system_pause") return t("lite.agents.error.system");
    if (res.status === 409 && res.code === "not_allowed") return t("lite.agents.error.notAllowed");
    if (res.status === 403) return t("lite.agents.error.forbidden");
    return t("lite.agents.error.generic");
  }

  async function pauseAgent(agent: LiteAgent, confirmed: boolean) {
    setBusy(agent.id);
    const res = await actions.pauseAgent({ id: agent.id, confirm: confirmed });
    setBusy(null);
    if (res.ok) {
      putAgent(res.data);
      setConfirm(null);
      toast.success(t("lite.agents.paused.toast", { name: agent.name }), {
        action: { label: t("lite.agents.resume"), onClick: () => void resumeAgent(res.data) },
      });
      return;
    }
    if (res.status === 409 && res.code === "confirm_required") {
      // Empezaron conversaciones desde que se leyó la lista: se vuelve a preguntar con la cifra de ahora.
      setConfirm({ kind: "agent", agent, open: Number(res.info?.open_conversations ?? 0) || 1 });
      return;
    }
    setConfirm(null);
    toast.error(problem(res));
  }

  async function resumeAgent(agent: LiteAgent) {
    setBusy(agent.id);
    const res = await actions.resumeAgent({ id: agent.id });
    setBusy(null);
    if (res.ok) {
      putAgent(res.data);
      toast.success(t("lite.agents.resumed.toast", { name: agent.name }));
    } else toast.error(problem(res));
  }

  async function pauseChannel(agent: LiteAgent, channel: LiteAgentChannel) {
    setBusy(channel.id);
    const res = await actions.pauseChannel({ id: channel.id });
    setBusy(null);
    setConfirm(null);
    if (res.ok) {
      putChannel(agent.id, res.data);
      toast.success(t("lite.agents.channel.paused.toast", { number: channel.identifier }), {
        action: { label: t("lite.agents.resume"), onClick: () => void resumeChannel(agent, res.data) },
      });
    } else toast.error(problem(res));
  }

  async function resumeChannel(agent: LiteAgent, channel: LiteAgentChannel) {
    setBusy(channel.id);
    const res = await actions.resumeChannel({ id: channel.id });
    setBusy(null);
    if (res.ok) {
      putChannel(agent.id, res.data);
      toast.success(t("lite.agents.channel.resumed.toast", { number: channel.identifier }));
    } else toast.error(problem(res));
  }

  function agentActions(agent: LiteAgent): RowAction[] {
    return agent.allowed.map((a) =>
      a === "pause"
        ? { label: t("lite.agents.pause"), primary: true, disabled: busy !== null, onSelect: () => setConfirm({ kind: "agent", agent, open: agent.open_conversations }) }
        : { label: t("lite.agents.resume"), primary: true, disabled: busy !== null, onSelect: () => void resumeAgent(agent) },
    );
  }

  return (
    <div className="grid min-w-0 gap-6" data-slot="lite-agents">
      <PageHeader title={t("nav.agents")} description={t("lite.agents.intro")} />
      {data === null ? (
        <ErrorState
          title={t("lite.agents.error.load")}
          description={t("lite.agents.error.load.hint")}
          onRetry={retry}
          retryLabel={t("lite.agents.retry")}
        />
      ) : items.length === 0 ? (
        <EmptyState icon={Bot} title={t("lite.agents.empty")} description={t("lite.agents.empty.hint")} readonly />
      ) : (
        <ul aria-label={t("lite.agents.list")} aria-busy={reloading} className="grid min-w-0 gap-4">
          {items.map((agent) => (
            <li key={agent.id} className="min-w-0">
              <AgentCard agent={agent} actions={agentActions(agent)} menu={menu} busy={busy} onPauseChannel={(c) => setConfirm({ kind: "channel", agent, channel: c })} onResumeChannel={(c) => void resumeChannel(agent, c)} />
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={confirm !== null}
        onOpenChange={(open) => !open && setConfirm(null)}
        title={
          confirm?.kind === "channel"
            ? t("lite.agents.channel.pause.title", { number: confirm.channel.identifier })
            : t("lite.agents.pause.title", { name: confirm?.agent.name ?? "" })
        }
        description={
          confirm?.kind === "channel"
            ? t("lite.agents.channel.pause.body")
            : confirm && confirm.open > 0
              ? t(confirm.open === 1 ? "lite.agents.pause.body.open.one" : "lite.agents.pause.body.open.other", { n: confirm.open })
              : t("lite.agents.pause.body")
        }
        confirmLabel={confirm?.kind === "channel" ? t("lite.agents.channel.pause.confirm") : t("lite.agents.pause.confirm")}
        cancelLabel={t("lite.agents.cancel")}
        destructive
        onConfirm={async () => {
          if (!confirm) return;
          if (confirm.kind === "agent") await pauseAgent(confirm.agent, confirm.open > 0);
          else await pauseChannel(confirm.agent, confirm.channel);
        }}
      />
    </div>
  );
}

/**
 * Devolver el foco cuando el modal ya se fue: mientras sale, su trampa de foco
 * sigue activa y devolvería el foco adentro.
 */
function restoreFocus(el: HTMLElement | null) {
  if (!el) return;
  let tries = 0;
  const tick = () => {
    if (!el.isConnected) return;
    if (document.querySelector("[role=dialog], [role=alertdialog]") && tries++ < 40) {
      window.setTimeout(tick, 25);
      return;
    }
    el.focus();
  };
  window.requestAnimationFrame(tick);
}

function AgentCard({
  agent,
  actions,
  menu,
  busy,
  onPauseChannel,
  onResumeChannel,
}: {
  agent: LiteAgent;
  actions: RowAction[];
  menu: boolean;
  busy: string | null;
  onPauseChannel: (channel: LiteAgentChannel) => void;
  onResumeChannel: (channel: LiteAgentChannel) => void;
}) {
  const t = useT();
  const titleId = React.useId();
  const line = pauseLine(agent);
  const channelMenu = foldsIntoMenu(agent.channels.reduce((n, c) => n + c.allowed.length, 0));
  return (
    <section aria-labelledby={titleId} className="grid min-w-0 gap-4 rounded-md border border-border bg-card p-4 sm:p-6" data-agent={agent.id}>
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-3">
        <div className="grid min-w-0 flex-1 basis-56 gap-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h2 id={titleId} className="min-w-0 text-base font-semibold text-balance break-words">
              {agent.name}
            </h2>
            <StatusBadge tone={visibleTone(agent.visible_state)} data-slot="agent-state">
              {visibleText(t, agent.visible_state)}
            </StatusBadge>
            {agent.is_default ? <span className="text-xs text-muted-foreground">{t("lite.agents.default")}</span> : null}
          </div>
          {line ? (
            <p className="text-sm text-pretty text-muted-foreground">{line.name ? t(line.key, { name: line.name }) : t(line.key)}</p>
          ) : null}
          {agent.open_conversations > 0 ? (
            <p className="flex items-center gap-1 text-sm text-muted-foreground">
              <MessageCircle className="size-4 shrink-0" aria-hidden="true" />
              {t(agent.open_conversations === 1 ? "lite.agents.open.one" : "lite.agents.open.other", { n: agent.open_conversations })}
            </p>
          ) : null}
        </div>
        {actions.length ? <RowActions actions={actions} menu={menu} ariaLabel={t("lite.agents.actions", { name: agent.name })} /> : null}
      </div>
      <div className="grid min-w-0 gap-2">
        <h3 className="text-sm font-medium">{t("lite.agents.channels")}</h3>
        {agent.channels.length === 0 ? (
          <p className="text-sm text-pretty text-muted-foreground">{t("lite.agents.channels.none")}</p>
        ) : (
          <ul aria-label={t("lite.agents.channels.of", { name: agent.name })} className="grid min-w-0 divide-y divide-border-soft border-t border-border-soft">
            {agent.channels.map((c) => {
              const acts: RowAction[] = c.allowed.map((a) =>
                a === "pause"
                  ? { label: t("lite.agents.channel.pause"), primary: true, disabled: busy !== null, onSelect: () => onPauseChannel(c) }
                  : { label: t("lite.agents.channel.resume"), primary: true, disabled: busy !== null, onSelect: () => onResumeChannel(c) },
              );
              return (
                <li key={c.id} className="flex min-w-0 flex-wrap items-center justify-between gap-2 py-2">
                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                    <span className="min-w-0 text-sm font-medium tabular-nums break-words">{c.identifier}</span>
                    <span className="text-xs text-muted-foreground">{t(c.type === "whatsapp" ? "lite.agents.channel.whatsapp" : "lite.agents.channel.other")}</span>
                    <StatusBadge tone={visibleTone(c.visible_state)}>{channelStateText(t, c.visible_state)}</StatusBadge>
                  </div>
                  {acts.length ? <RowActions actions={acts} menu={channelMenu} ariaLabel={t("lite.agents.channel.actions", { number: c.identifier })} /> : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
