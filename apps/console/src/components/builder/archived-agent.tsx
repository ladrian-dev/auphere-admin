"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, StatusBadge } from "@nexus/ui";

import { CrumbName } from "@/components/shell/crumb-names";
import { useT } from "@/i18n/client";
import type { AgentHeader } from "@/lib/backend/agent-life-types";
import { ShellBackButton } from "@/components/shell/shell-back-button";

import { LIFE_ACTIONS, type AgentLifeActions } from "./agent-menu";
import { visibleText, visibleTone } from "./life-model";

/**
 * Un agente archivado (spec 047, historia 19; requisito 28): no responde en
 * ningún número y no se edita. Se ve en solo lectura y, para quien puede,
 * «Restaurar», que lo devuelve en pausa (28.2) y abre su pantalla de siempre.
 */
export function ArchivedAgent({
  refId,
  header,
  actions = LIFE_ACTIONS,
}: {
  refId: string;
  header: AgentHeader;
  actions?: Pick<AgentLifeActions, "restore">;
}) {
  const t = useT();
  const router = useRouter();
  const [busy, setBusy] = React.useState(false);
  const canRestore = header.allowed.includes("restore");

  async function restore() {
    setBusy(true);
    const res = await actions.restore({ ref: refId, agent: header.id });
    setBusy(false);
    if (!res.ok) {
      toast.error(t("builder.life.error"));
      return;
    }
    toast.success(t("builder.life.restored", { name: header.name }));
    router.refresh();
  }

  return (
    <div className="grid min-w-0 gap-4" data-slot="archived-agent">
      <CrumbName id={header.id} label={header.name} />
      <header className="grid min-w-0 gap-2">
        <div className="flex min-w-0 items-center gap-3">
          <ShellBackButton />
          <h1 className="min-w-0 text-2xl font-semibold tracking-tighter text-balance break-words sm:text-display">{header.name}</h1>
        </div>
        <div>
          <StatusBadge tone={visibleTone(header.visible_state)}>{visibleText(t, header.visible_state)}</StatusBadge>
        </div>
      </header>
      <Callout
        tone="neutral"
        action={
          canRestore ? (
            <Button onClick={() => void restore()} loading={busy}>
              {t("builder.life.action.restore")}
            </Button>
          ) : undefined
        }
      >
        <p>{t("builder.life.archivedView")}</p>
        {!canRestore ? <p>{t("builder.life.archivedView.readonly")}</p> : null}
      </Callout>
    </div>
  );
}
