/**
 * La lista de puesta en marcha — spec 010, Requisitos 7.6 y 7.7.
 *
 * Lo que decide vive en `setup-checklist.ts`; esto lo pinta. Cuatro decisiones:
 *
 * * **los pasos hechos se quedan a la vista.** Que desaparezcan deja sin saber
 *   si se hicieron o si la lista se rompió;
 * * **ninguna casilla marcable**: esto es una lectura de lo que ya es cierto,
 *   no una tarea que alguien pueda tachar sin haberla hecho;
 * * **un paso hecho no lleva botón**, porque no lleva a ninguna parte (§V);
 * * **con todo hecho se felicita y se sale**, en vez de dejar una lista de
 *   seises verdes ocupando sitio para siempre.
 */
import { Check } from "lucide-react";

import { Button } from "@nexus/ui";

import type { SetupSection, SetupStep } from "../../setup-checklist";
import { pendingSteps } from "../../setup-checklist";
import { type AppKey, useAppT } from "../i18n";

export function SetupList({
  steps,
  onGo,
}: {
  steps: readonly SetupStep[];
  onGo: (section: SetupSection) => void;
}) {
  const t = useAppT();
  const faltan = pendingSteps(steps);

  return (
    <section className="flex flex-col gap-4 p-6" aria-labelledby="setup-title">
      <div className="flex flex-col gap-1">
        <h2 id="setup-title" className="text-base font-semibold text-balance">
          {t("setup.title")}
        </h2>
        <p className="max-w-prose text-ui text-pretty text-muted-foreground">
          {faltan.length === 0 ? t("setup.done") : t("setup.body")}
        </p>
      </div>

      <ul className="flex max-w-prose flex-col gap-2">
        {steps.map((step) => (
          <li key={step.key} data-step={step.key} data-state={step.state} className="flex min-w-0 items-start gap-3">
            <span
              aria-hidden="true"
              className={`mt-1 flex size-4 shrink-0 items-center justify-center rounded-full border ${
                step.state === "hecho" ? "border-primary bg-primary text-primary-foreground" : "border-border"
              }`}
            >
              {step.state === "hecho" ? <Check className="size-3" /> : null}
            </span>
            <span className="flex min-w-0 flex-1 flex-col gap-1">
              <span className={`text-ui ${step.state === "no_aplica" ? "text-muted-foreground" : ""}`}>
                {t(`setup.step.${step.key}` as AppKey)}
                <span className="sr-only"> · {t(`setup.state.${step.state}` as AppKey)}</span>
              </span>
              {step.blocked_reason_key ? (
                <span className="text-xs text-pretty text-muted-foreground">
                  {t(step.blocked_reason_key as AppKey)}
                </span>
              ) : null}
            </span>
            {step.state === "pendiente" && step.section ? (
              <Button size="sm" variant="outline" onClick={() => onGo(step.section!)}>
                {t(step.blocked_reason_key ? "setup.unblock" : "setup.go")}
              </Button>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
