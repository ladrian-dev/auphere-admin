"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Alert, AlertDescription, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, cn } from "@nexus/ui";

import { saveModelAction } from "@/app/(console)/clients/[ref]/agent/actions";
import { useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";
import type { ClientModel, ConsoleModel } from "@/lib/backend/models";

type Props = { refId: string; models: ConsoleModel[]; current: ClientModel; canWrite: boolean };

/**
 * «Modelo» card (spec 016, US4). Lives OUTSIDE the settings form: the
 * model is not part of the draft, it applies on the next turn. Each option
 * shows its cost relative to the cheapest («×N créditos»), the current one
 * is marked, and a bound model the plan no longer includes is called out
 * with the model that answers meanwhile.
 */
export function ModelPicker({ refId, models, current, canWrite }: Props) {
  const t = useT();
  const router = useRouter();
  // What answers right now: the binding when the plan allows it, otherwise
  // the platform default the API names (not the first of the list).
  const effective = current.is_bound && current.allowed ? current.model_id : current.fallback_model_id;
  const [choice, setChoice] = React.useState<string | null>(effective);
  const [pending, start] = React.useTransition();
  const dirty = choice != null && choice !== effective;

  function save() {
    if (!choice || !dirty) return;
    start(async () => {
      const res = await saveModelAction({ ref: refId, model_id: choice });
      if (!res.ok) return void toast.error(actionErrorText(res, t));
      toast.success(t("agent.model.saved", { model: res.data.display_name ?? choice }));
      router.refresh();
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("agent.model.title")}</CardTitle>
        <CardDescription>{t("agent.model.description")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {current.is_bound && !current.allowed ? (
          <Alert role="status">
            <AlertDescription>
              {t("agent.model.notAllowed", { model: current.display_name ?? current.model_id ?? "—", fallback: current.fallback_display_name })}
            </AlertDescription>
          </Alert>
        ) : null}
        {models.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("agent.model.none")}</p>
        ) : (
          <div role="radiogroup" aria-label={t("agent.model.title")} className="grid gap-2 sm:grid-cols-3">
            {models.map((m) => {
              const selected = choice === m.model_id;
              const isCurrent = effective === m.model_id;
              return (
                <button
                  key={m.model_id}
                  type="button"
                  role="radio"
                  aria-checked={selected}
                  disabled={!canWrite || pending}
                  onClick={() => setChoice(m.model_id)}
                  className={cn(
                    "flex flex-col items-start gap-1 rounded-md border p-3 text-left text-sm transition-colors",
                    selected ? "border-foreground" : "border-border hover:border-foreground/40",
                    (!canWrite || pending) && "cursor-not-allowed opacity-70",
                  )}
                >
                  <span className="flex w-full items-center justify-between gap-2">
                    <span className="font-medium">{m.display_name}</span>
                    {isCurrent ? <span className="font-mono text-xs text-muted-foreground">{t("agent.model.current")}</span> : null}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {m.relative_cost <= 1 ? t("agent.model.cheapest") : t("agent.model.cost", { n: m.relative_cost })}
                  </span>
                </button>
              );
            })}
          </div>
        )}
        {canWrite ? (
          <div className="flex items-center gap-3">
            <Button type="button" size="sm" onClick={save} disabled={!dirty || pending} aria-busy={pending}>
              {t("agent.model.save")}
            </Button>
            <p className="text-xs text-muted-foreground text-pretty">{t("agent.model.hint")}</p>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
