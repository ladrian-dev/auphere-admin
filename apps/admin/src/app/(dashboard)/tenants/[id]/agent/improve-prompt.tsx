"use client";

/**
 * Block N — "Mejorar prompt" dialog.
 *
 * Drives the operator-interactive prompt improver:
 *
 *  1. Operator clicks the sparkle button next to the prompt textarea.
 *  2. Dialog opens with mode chips (General / Más específico / etc.).
 *  3. We POST the current draft + chosen mode to
 *     /admin/tenants/:id/agent-config/improve-prompt.
 *  4. The diff view shows the current text on the left and the model's
 *     improved version on the right. Bullet summary of changes is
 *     collapsable below.
 *  5. Operator can Apply (writes back to the editor), Iterate again
 *     (with optional free-text feedback) or Discard.
 *
 * UX rules from ADR-013:
 *  - Never auto-apply. The operator must click Apply.
 *  - Show usage stats so the operator can correlate quality with cost.
 *  - Streaming would be nice but v1 waits for the full response.
 */

import { Sparkles } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { ImprovePromptMode, ImprovePromptOut } from "@/lib/backend";

import { improveAgentPromptAction } from "./actions";

const MODES: Array<{ value: ImprovePromptMode; label: string }> = [
  { value: "general", label: "General" },
  { value: "specific", label: "Más específico" },
  { value: "structure", label: "Estructurar" },
  { value: "examples", label: "Añadir ejemplos" },
  { value: "shorter", label: "Acortar" },
  { value: "edge_cases", label: "Edge cases" },
  { value: "english", label: "Traducir a inglés" },
];

export function ImprovePromptButton({
  tenantId,
  currentPrompt,
  onApply,
}: {
  tenantId: string;
  currentPrompt: string;
  /** Called when the operator clicks "Aplicar". Receives the improved
   *  text — the editor writes it back into its textarea state. */
  onApply: (improvedPrompt: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [mode, setMode] = useState<ImprovePromptMode>("general");
  const [feedback, setFeedback] = useState("");
  const [result, setResult] = useState<ImprovePromptOut | null>(null);
  const [showSummary, setShowSummary] = useState(true);

  function runImprove() {
    if (!currentPrompt.trim()) {
      toast.error(
        "El prompt está vacío — escribí algo primero o aplicá una plantilla.",
      );
      return;
    }
    start(async () => {
      const res = await improveAgentPromptAction(tenantId, {
        prompt: currentPrompt,
        mode,
        feedback: feedback.trim() || null,
      });
      if (!res.ok) {
        toast.error(`No se pudo mejorar: ${res.error}`);
        return;
      }
      setResult(res.data);
    });
  }

  function reset() {
    setResult(null);
    setFeedback("");
    setMode("general");
  }

  function onOpenChange(next: boolean) {
    if (pending) return;
    setOpen(next);
    if (!next) reset();
  }

  function apply() {
    if (!result) return;
    onApply(result.improved_prompt);
    toast.success("Prompt aplicado al editor", {
      description:
        "Revisá el textarea y guardá el borrador cuando estés conforme.",
    });
    setOpen(false);
    reset();
  }

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => setOpen(true)}
        className="inline-flex items-center gap-1.5"
      >
        <Sparkles className="size-3.5" />
        Mejorar prompt
      </Button>

      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-5xl">
          <DialogHeader>
            <DialogTitle className="inline-flex items-center gap-2">
              <Sparkles className="size-4" /> Mejorar prompt
            </DialogTitle>
            <DialogDescription>
              El improver usa Claude Sonnet 4.6 con el contexto de este
              tenant (canal, vertical, tools whitelisteadas). Es una
              sugerencia — siempre revisás antes de aplicar.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-wrap items-center gap-2">
            <Label className="text-xs uppercase tracking-wider text-muted-foreground mr-2">
              Modo
            </Label>
            {MODES.map((m) => {
              const active = mode === m.value;
              return (
                <button
                  key={m.value}
                  type="button"
                  disabled={pending}
                  onClick={() => setMode(m.value)}
                  className={
                    "rounded-full border px-3 py-1 text-xs transition-colors " +
                    (active
                      ? "border-foreground bg-foreground text-background"
                      : "border-border bg-transparent text-muted-foreground hover:text-foreground")
                  }
                >
                  {m.label}
                </button>
              );
            })}
          </div>

          {result === null ? (
            <div className="grid gap-3">
              <Label htmlFor="feedback" className="text-sm">
                Feedback opcional
              </Label>
              <Textarea
                id="feedback"
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                rows={2}
                placeholder="ej: más conciso, mantené el tono casual"
                disabled={pending}
              />
              <p className="text-xs text-muted-foreground">
                Vamos a usar el prompt que tenés en el editor (
                {currentPrompt.length} caracteres).
              </p>
            </div>
          ) : (
            <div className="grid gap-3">
              <div className="grid gap-2 md:grid-cols-2">
                <div className="grid gap-1">
                  <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                    Actual
                  </Label>
                  <pre className="max-h-[420px] overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs whitespace-pre-wrap break-words font-mono">
                    {currentPrompt}
                  </pre>
                </div>
                <div className="grid gap-1">
                  <Label className="text-xs uppercase tracking-wider text-muted-foreground">
                    Sugerido
                  </Label>
                  <pre className="max-h-[420px] overflow-auto rounded-md border border-emerald-300/50 bg-emerald-50/40 dark:bg-emerald-950/20 p-3 text-xs whitespace-pre-wrap break-words font-mono">
                    {result.improved_prompt}
                  </pre>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground tabular-nums">
                <Badge variant="outline" className="text-[10px] uppercase">
                  {result.mode}
                </Badge>
                <span>{result.latency_ms} ms</span>
                {result.input_tokens !== null ? (
                  <span>in: {result.input_tokens}</span>
                ) : null}
                {result.output_tokens !== null ? (
                  <span>out: {result.output_tokens}</span>
                ) : null}
                {result.cached_input_tokens ? (
                  <span>cached: {result.cached_input_tokens}</span>
                ) : null}
                <span className="text-muted-foreground/60">
                  meta {result.meta_prompt_version}
                </span>
              </div>

              {result.summary_of_changes.length > 0 ? (
                <details
                  open={showSummary}
                  onToggle={(e) =>
                    setShowSummary((e.target as HTMLDetailsElement).open)
                  }
                  className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm"
                >
                  <summary className="cursor-pointer text-xs uppercase tracking-wider text-muted-foreground">
                    Resumen de cambios ({result.summary_of_changes.length})
                  </summary>
                  <ul className="mt-2 grid gap-1 pl-4 list-disc">
                    {result.summary_of_changes.map((bullet, i) => (
                      <li key={i}>{bullet}</li>
                    ))}
                  </ul>
                </details>
              ) : null}

              <div className="grid gap-2">
                <Label htmlFor="feedback-iter" className="text-sm">
                  Volver a iterar (opcional)
                </Label>
                <Textarea
                  id="feedback-iter"
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                  rows={2}
                  placeholder="ej: añadí un ejemplo de cómo manejar fechas ambiguas"
                  disabled={pending}
                />
              </div>
            </div>
          )}

          <DialogFooter className="flex-wrap gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onOpenChange(false)}
              disabled={pending}
            >
              {result === null ? "Cancelar" : "Descartar"}
            </Button>
            {result !== null ? (
              <Button
                variant="outline"
                size="sm"
                onClick={runImprove}
                disabled={pending}
              >
                {pending ? "Mejorando…" : "Iterar"}
              </Button>
            ) : null}
            {result === null ? (
              <Button size="sm" onClick={runImprove} disabled={pending}>
                {pending ? "Mejorando…" : "Mejorar"}
              </Button>
            ) : (
              <Button size="sm" onClick={apply} disabled={pending}>
                Aplicar al editor
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
