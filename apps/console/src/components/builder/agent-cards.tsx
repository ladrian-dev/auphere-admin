"use client";

import { Bot, ChevronRight, Sparkles } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, EmptyState, StatusBadge, buttonVariants } from "@nexus/ui";

import { dismissSuggestedAgentAction } from "@/app/(console)/clients/[ref]/agents/suggested-actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { ClientAgent } from "@/lib/backend";
import { suggestedRole, type SuggestedAgent } from "@/lib/backend/suggested-agents";

import type { Result } from "./builder-model";
import { cardHref, isDefault, proposedAgentHref, visibleText, visibleTone } from "./life-model";

type Dismiss = (body: { ref: string; id: string }) => Promise<Result<null>>;
const DISMISS: Dismiss = (body) => dismissSuggestedAgentAction(body);

/**
 * La pestaña Agentes de un cliente con la consola nueva (spec 047, historias 7
 * y 19; requisitos 17.2 y 26.1): una tarjeta por agente con su nombre, su estado
 * visible (el mismo texto y tono que en toda la consola, 25.5), si es el agente
 * por defecto y cuántos canales atiende. Lleva a la pestaña que le toca: un
 * borrador, a construir; «Listo · sin canal», a los canales; el resto, al
 * agente. Un borrador abandonado sigue aquí, como «Borrador».
 *
 * «Nuevo agente» solo para quien puede escribir (§V): a quien lee no se le
 * enseña un botón que no podría usar.
 *
 * Enmienda del 2026-10-29 (T210, requisito 60.6): detrás, los agentes que el
 * sistema sugiere para su ficha, como tarjetas «Sugerido» con «Crear este
 * agente» (abre «Nuevo agente» con su nombre y su descripción, no crea nada) y
 * «Descartar». `suggested` es `null` si no se pudieron leer: entonces no salen.
 * Enmienda del 2026-10-30 (T228, 65.7): el papel de una sugerencia es
 * opcional y no decide nada; sin él, la tarjeta sale entera y sin papel.
 */
export function AgentCards({
  refId,
  agents,
  canWrite,
  suggested = null,
  dismiss = DISMISS,
}: {
  refId: string;
  agents: ClientAgent[] | null;
  canWrite: boolean;
  suggested?: SuggestedAgent[] | null;
  dismiss?: Dismiss;
}) {
  const t = useT();
  const listed = agents ? [...agents].sort((a, b) => Number(a.status === "archived") - Number(b.status === "archived")) : [];
  return (
    <div className="grid min-w-0 gap-4" data-slot="agent-cards">
      {/* Sin título ni «Nuevo agente» propios: como el prototipo, la pestaña es
          la lista, y el botón primario está una sola vez, en la cabecera del
          cliente (Andrés, 2026-10-28). */}
      {agents === null ? (
        <Callout tone="danger">{t("builder.agents.error")}</Callout>
      ) : !listed.length ? (
        <EmptyState
          icon={Bot}
          title={t("builder.agents.empty.title")}
          description={canWrite ? t("builder.agents.empty.body") : t("builder.agents.empty.readonly")}
          readonly={!canWrite}
        />
      ) : (
        <ul aria-label={t("builder.agents.list")} className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {listed.map((agent) => (
            <li key={agent.id} className="min-w-0">
              <AgentCard refId={refId} agent={agent} />
            </li>
          ))}
        </ul>
      )}
      {suggested?.length ? <SuggestedAgents refId={refId} initial={suggested} canWrite={canWrite} dismiss={dismiss} /> : null}
    </div>
  );
}

/** Las tarjetas «Sugerido» (60.6): ninguna se crea sola. */
function SuggestedAgents({ refId, initial, canWrite, dismiss }: { refId: string; initial: SuggestedAgent[]; canWrite: boolean; dismiss: Dismiss }) {
  const t = useT();
  const hintId = React.useId();
  const [items, setItems] = React.useState(initial);
  if (!items.length) return null;
  return (
    <div className="grid min-w-0 gap-2" data-slot="suggested-agents">
      <p id={hintId} className="inline-flex min-w-0 items-center gap-2 text-sm text-pretty text-muted-foreground">
        <Sparkles aria-hidden="true" className="size-4 shrink-0" />
        {t("builder.suggested.hint")}
      </p>
      <ul aria-label={t("builder.suggested.list")} aria-describedby={hintId} className="grid min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((agent) => (
          <SuggestedCard
            key={agent.id}
            refId={refId}
            agent={agent}
            canWrite={canWrite}
            dismiss={dismiss}
            onDismissed={() => setItems((prev) => prev.filter((x) => x.id !== agent.id))}
          />
        ))}
      </ul>
    </div>
  );
}

function SuggestedCard({
  refId,
  agent,
  canWrite,
  dismiss,
  onDismissed,
}: {
  refId: string;
  agent: SuggestedAgent;
  canWrite: boolean;
  dismiss: Dismiss;
  onDismissed: () => void;
}) {
  const t = useT();
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState(false);
  // 65.7: el papel es opcional y ninguno es fijo. Uno que la consola no conoce, o ninguno, no se pinta.
  const role = suggestedRole(agent.role);

  async function discard() {
    if (busy) return;
    setBusy(true);
    setError(false);
    const res = await dismiss({ ref: refId, id: agent.id }).catch(() => null);
    setBusy(false);
    if (res?.ok) {
      toast.success(t("builder.suggested.dismissed"));
      onDismissed();
      return;
    }
    setError(true);
  }

  return (
    <li className="grid h-full min-w-0 content-between gap-3 rounded-md border border-dashed border-input bg-card p-4" data-slot="suggested-agent">
      <div className="grid min-w-0 gap-2">
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
          <p className="min-w-0 font-medium text-pretty break-words">{agent.name}</p>
          <StatusBadge tone="info">{t("builder.suggested.badge")}</StatusBadge>
        </div>
        {role ? <p className="text-xs text-muted-foreground">{t(`builder.suggested.role.${role}` as MessageKey)}</p> : null}
        <p className="line-clamp-3 text-sm text-pretty break-words text-muted-foreground">{agent.description}</p>
      </div>
      {error ? (
        <p role="alert" className="text-xs text-pretty text-destructive">
          {t("builder.suggested.error")}
        </p>
      ) : null}
      {canWrite ? (
        <div className="flex min-w-0 flex-wrap gap-2">
          <Link
            href={proposedAgentHref(refId, agent)}
            className={buttonVariants({ size: "sm", variant: "outline" })}
            aria-label={t("builder.suggested.create.label", { name: agent.name })}
          >
            {t("builder.suggested.create")}
          </Link>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            loading={busy}
            onClick={() => void discard()}
            aria-label={t("builder.suggested.dismiss.label", { name: agent.name })}
          >
            {t("builder.suggested.dismiss")}
          </Button>
        </div>
      ) : null}
    </li>
  );
}

function AgentCard({ refId, agent }: { refId: string; agent: ClientAgent }) {
  const t = useT();
  const channels = agent.channels.length;
  const archived = agent.status === "archived";
  const state = agent.visible_state ?? null;
  return (
    <Link
      href={cardHref(refId, agent)}
      className="group flex h-full min-w-0 items-start gap-3 rounded-md border border-border bg-card p-4 outline-none hover:bg-muted/40 focus-visible:ring-2 focus-visible:ring-ring"
      data-slot="agent-card"
      data-opens={agent.opens ?? undefined}
    >
      <span className="grid min-w-0 flex-1 gap-2">
        <span className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="min-w-0 font-medium break-words">{agent.name}</span>
          {isDefault(agent) && !archived ? <span className="text-xs text-muted-foreground">{t("builder.agents.principal")}</span> : null}
        </span>
        <span className="flex min-w-0 flex-wrap items-center gap-2">
          {state ? (
            // Spec 047 (25.5): el estado visible de la API, con el mismo texto y tono que en toda la consola.
            <StatusBadge tone={visibleTone(state)}>{visibleText(t, state)}</StatusBadge>
          ) : archived ? (
            <StatusBadge tone="muted">{t("builder.agents.state.archived")}</StatusBadge>
          ) : agent.active_version !== null ? (
            <StatusBadge tone="positive">{t("builder.agents.state.published")}</StatusBadge>
          ) : (
            <StatusBadge tone="muted">{t("builder.agents.state.draft")}</StatusBadge>
          )}
          {!archived && agent.active_version !== null && agent.draft_version !== null ? (
            <span className="text-xs text-muted-foreground">{t("builder.agents.pendingChanges")}</span>
          ) : null}
        </span>
        <span className="text-sm text-muted-foreground">
          {channels === 0
            ? t("builder.agents.channels.none")
            : channels === 1
              ? t("builder.agents.channels.one")
              : t("builder.agents.channels.other", { n: channels })}
        </span>
      </span>
      <ChevronRight aria-hidden="true" className="mt-1 size-4 shrink-0 text-muted-foreground group-hover:text-foreground" />
    </Link>
  );
}
