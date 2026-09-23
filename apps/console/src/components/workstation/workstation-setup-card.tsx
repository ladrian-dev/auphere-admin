"use client";

import { X } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button, Checklist, type ChecklistItem, Meter, Section } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { SetupOut, SetupStepKey } from "@/lib/backend/workstation";

const STEP_HREF: Record<SetupStepKey, string> = {
  paired: "/workstation",
  clients: "/workstation",
  directories: "/workstation",
  executables: "/clients",
};

/**
 * La puesta en marcha del puesto — Requisito 6 (spec 002).
 *
 * Cuatro pasos calculados por la plataforma **en cada visita** para la persona
 * que mira; cerrarla es estado de esta visita y **no** se persiste: mientras
 * falte algo, reaparece. Con los cuatro en verde no se renderiza, y no hay
 * control para volver a verla — la ausencia se diseña. Continúa el paso 3 del
 * onboarding del diseño («tienes teammates; ahora dales tu máquina») en vez
 * de abrir un segundo onboarding.
 */
export function WorkstationSetupCard({ setup }: { setup: SetupOut | null }) {
  const t = useT();
  const [closed, setClosed] = React.useState(false);
  if (closed) return null;
  if (setup?.complete) return null;
  const done = setup ? setup.steps.filter((s) => s.done).length : 0;
  const firstPending = setup?.steps.find((s) => !s.done)?.key;
  const items: ChecklistItem[] =
    setup?.steps.map((s) => ({
      key: s.key,
      label: t(`ws.setup.step.${s.key}`),
      status: s.done ? "done" : s.key === firstPending ? "current" : "todo",
      href: s.done ? undefined : STEP_HREF[s.key],
      detail: !s.done && s.pending > 1 ? t("ws.setup.pending", { n: s.pending }) : undefined,
    })) ?? [];

  return (
    <Section
      id="ws-setup"
      title={t("ws.setup.title")}
      description={
        setup ? (
          t("ws.setup.progress", { done, total: setup.steps.length })
        ) : (
          <span role="alert" className="text-destructive">
            {t("ws.setup.error")}
          </span>
        )
      }
      actions={
        <Button type="button" variant="ghost" size="icon-sm" onClick={() => setClosed(true)} aria-label={t("ws.setup.dismiss")}>
          <X className="size-4" aria-hidden="true" />
        </Button>
      }
    >
      {setup ? (
        <>
          <Meter label={t("ws.setup.title")} labelHidden value={done} max={setup.steps.length} tone="positive" size="sm" />
          <Checklist
            ariaLabel={t("ws.setup.title")}
            items={items}
            renderLink={(item, children, className) => (
              <Link href={item.href ?? "#"} className={className}>
                {children}
              </Link>
            )}
          />
          {!setup.steps.find((s) => s.key === "executables")?.done ? (
            <p className="text-xs text-muted-foreground text-pretty">{t("ws.setup.executables.help")}</p>
          ) : null}
        </>
      ) : null}
    </Section>
  );
}
