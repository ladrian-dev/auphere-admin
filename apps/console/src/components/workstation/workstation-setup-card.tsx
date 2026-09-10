"use client";

import { Check, CircleDashed, X } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button, cn } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { SetupOut, SetupStepKey } from "@/lib/backend/workstation";

const STEP_HREF: Record<SetupStepKey, string> = {
  paired: "/workstation",
  clients: "/workstation",
  directories: "/workstation",
  executables: "/clients",
};

const PROGRESS_WIDTH = ["w-0", "w-1/4", "w-2/4", "w-3/4", "w-full"] as const;

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

  return (
    <section aria-labelledby="ws-setup-title" className="flex flex-col gap-3 rounded-md border border-border bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 id="ws-setup-title" className="text-base font-semibold text-balance">
            {t("ws.setup.title")}
          </h2>
          {setup ? (
            <p className="text-sm text-muted-foreground">{t("ws.setup.progress", { done, total: setup.steps.length })}</p>
          ) : (
            <p role="alert" className="text-sm text-destructive">
              {t("ws.setup.error")}
            </p>
          )}
        </div>
        <Button type="button" variant="ghost" size="icon-sm" onClick={() => setClosed(true)} aria-label={t("ws.setup.dismiss")}>
          <X className="size-4" aria-hidden="true" />
        </Button>
      </div>
      {setup ? (
        <>
          <div className="h-1 w-full overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuemin={0} aria-valuemax={setup.steps.length} aria-valuenow={done} aria-label={t("ws.setup.title")}>
            <div className={cn("h-full bg-primary transition-[width] duration-300", PROGRESS_WIDTH[Math.min(done, 4)])} />
          </div>
          <ol className="flex flex-col gap-1">
            {setup.steps.map((s) => {
              const inner = (
                <>
                  {s.done ? <Check className="size-4 shrink-0 text-primary" aria-hidden="true" /> : <CircleDashed className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />}
                  <span className={cn("min-w-0 text-pretty", s.done && "text-muted-foreground line-through")}>{t(`ws.setup.step.${s.key}`)}</span>
                  {!s.done && s.pending > 1 ? <span className="text-xs text-muted-foreground">{t("ws.setup.pending", { n: s.pending })}</span> : null}
                </>
              );
              return (
                <li key={s.key} className="text-sm">
                  {!s.done ? (
                    <Link href={STEP_HREF[s.key]} className="flex min-w-0 items-center gap-2 rounded-sm px-1 py-1 hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none">
                      {inner}
                    </Link>
                  ) : (
                    <span className="flex min-w-0 items-center gap-2 px-1 py-1">{inner}</span>
                  )}
                </li>
              );
            })}
          </ol>
          {!setup.steps.find((s) => s.key === "executables")?.done ? (
            <p className="text-xs text-muted-foreground text-pretty">{t("ws.setup.executables.help")}</p>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
