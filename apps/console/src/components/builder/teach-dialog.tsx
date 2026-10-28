"use client";

import * as React from "react";

import { Button, Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, Field, Textarea } from "@nexus/ui";

import { useT } from "@/i18n/client";
import { TEACH_MAX_CHARS, type TeachScope } from "@/lib/backend/agent-knowledge-types";

import { retestKey, teachProblem } from "./knowledge-model";

const SCOPES: readonly TeachScope[] = ["agent", "business"];

/**
 * «Enseñar» (spec 047, requisito 37.3): lo que debe saber, con las palabras de
 * la persona, y **siempre** dónde se guarda —«Solo este agente» o «Todo el
 * negocio (todos los agentes)»—. No hay alcance por defecto: sin elegirlo no se
 * manda. Dice qué pruebas se vuelven a pasar según el alcance.
 *
 * `onTeach` devuelve el texto del error, o `null` si se aplicó.
 */
export function TeachDialog({
  agentName,
  onOpenChange,
  onTeach,
}: {
  agentName: string;
  onOpenChange: (open: boolean) => void;
  onTeach: (body: { text: string; scope: TeachScope }) => Promise<string | null>;
}) {
  const t = useT();
  const base = React.useId();
  const [text, setText] = React.useState("");
  const [scope, setScope] = React.useState<TeachScope | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [scopeError, setScopeError] = React.useState(false);
  const [busy, setBusy] = React.useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const problem = teachProblem(text, scope);
    if (problem === "builder.teach.required.scope") {
      setError(null);
      setScopeError(true);
      return;
    }
    if (problem) {
      setScopeError(false);
      setError(t(problem));
      return;
    }
    setBusy(true);
    setError(null);
    setScopeError(false);
    const failed = await onTeach({ text: text.trim(), scope: scope as TeachScope });
    setBusy(false);
    if (failed) setError(failed);
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={submit} noValidate className="grid min-w-0 gap-4" data-slot="teach-dialog">
          <DialogHeader>
            <DialogTitle>{t("builder.teach.title", { name: agentName })}</DialogTitle>
            <DialogDescription>{t("builder.teach.body")}</DialogDescription>
          </DialogHeader>
          <Field label={t("builder.teach.text")} hint={t("builder.teach.text.hint")} error={error ?? undefined} required>
            {(a11y) => <Textarea {...a11y} value={text} rows={4} maxLength={TEACH_MAX_CHARS} onChange={(e) => setText(e.target.value)} />}
          </Field>
          <fieldset
            className="grid min-w-0 gap-2"
            aria-describedby={scopeError ? `${base}-scope-error` : undefined}
            data-slot="teach-scope"
          >
            <legend className="mb-1 text-sm font-medium">{t("builder.teach.scope")}</legend>
            {SCOPES.map((s) => (
              <label key={s} className="flex min-h-6 min-w-0 items-start gap-2 text-sm">
                <input
                  type="radio"
                  name={`${base}-scope`}
                  value={s}
                  className="mt-1 size-4 shrink-0 accent-primary"
                  checked={scope === s}
                  onChange={() => {
                    setScope(s);
                    setScopeError(false);
                  }}
                />
                <span className="grid min-w-0 gap-1">
                  <span className="text-pretty">{t(s === "agent" ? "builder.teach.scope.agent" : "builder.teach.scope.business")}</span>
                  <span className="text-xs text-pretty text-muted-foreground">
                    {t(s === "agent" ? "builder.teach.scope.agent.hint" : "builder.teach.scope.business.hint")}
                  </span>
                </span>
              </label>
            ))}
            {scopeError ? (
              <p id={`${base}-scope-error`} role="alert" className="text-xs text-destructive text-pretty">
                {t("builder.teach.required.scope")}
              </p>
            ) : null}
          </fieldset>
          <p className="text-sm text-pretty text-muted-foreground" aria-live="polite" data-slot="teach-retest">
            {t(retestKey(scope))}
          </p>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              {t("builder.teach.cancel")}
            </Button>
            <Button type="submit" loading={busy}>
              {t("builder.teach.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
