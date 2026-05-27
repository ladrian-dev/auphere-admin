"use client";

/**
 * Block P — Evals section on the agent page.
 *
 * Minimal v1 UI: list of datasets (one dataset is typical for a tenant),
 * inline form to add a case, button to run evals against a specific
 * version, list of the most recent runs with their pass-rate.
 *
 * Out of scope for v1: rich case editor, dataset versioning UI,
 * comparison views. ADR-015 spells out the deferred features.
 */

import { Beaker, Loader2, Play, Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type {
  EvalDataset,
  EvalDatasetDetail,
  EvalRun,
  EvalRunDetail,
} from "@/lib/backend";

import {
  createCaseAction,
  createDatasetAction,
  deleteCaseAction,
  getRunAction,
  triggerRunAction,
} from "./actions";

const POLL_INTERVAL_MS = 3000;
const TERMINAL_STATUSES = new Set<EvalRun["status"]>(["passed", "failed", "error"]);

const STATUS_TONE: Record<EvalRun["status"], "default" | "destructive" | "secondary" | "outline"> = {
  pending: "secondary",
  running: "secondary",
  passed: "default",
  failed: "destructive",
  error: "destructive",
};

export function EvalsSection({
  tenantId,
  datasets,
  primaryDataset,
  recentRuns,
  activeVersion,
}: {
  tenantId: string;
  datasets: EvalDataset[];
  primaryDataset: EvalDatasetDetail | null;
  recentRuns: EvalRun[];
  activeVersion: number | null;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [createDatasetOpen, setCreateDatasetOpen] = useState(false);
  const [createCaseOpen, setCreateCaseOpen] = useState(false);
  const [runResult, setRunResult] = useState<EvalRunDetail | null>(null);
  const lastNotifiedRunId = useRef<string | null>(null);
  const isRunInFlight =
    runResult !== null && !TERMINAL_STATUSES.has(runResult.status);

  // Polling: while the active run is pending/running, fetch detail every
  // POLL_INTERVAL_MS. Stops cleanly when status reaches a terminal value,
  // when the component unmounts, or when the user triggers a new run
  // (which resets ``runResult`` to the new pending row and the effect
  // re-subscribes).
  useEffect(() => {
    if (!runResult || TERMINAL_STATUSES.has(runResult.status)) {
      return;
    }
    let cancelled = false;
    const runId = runResult.id;

    const tick = async () => {
      if (cancelled) return;
      const res = await getRunAction(tenantId, runId);
      if (cancelled) return;
      if (!res.ok) {
        // Network blip — keep polling, don't toast on every retry.
        return;
      }
      setRunResult(res.data);
      if (TERMINAL_STATUSES.has(res.data.status)) {
        // Refresh the parent route so "Últimos runs" shows the final
        // row. The toast fires from the dedicated terminal effect
        // below so it can't double-fire across renders.
        router.refresh();
      }
    };

    const handle = window.setInterval(tick, POLL_INTERVAL_MS);
    // Fire one immediately so the user doesn't wait the full interval
    // for the first progress update.
    void tick();
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [runResult, tenantId, router]);

  // Terminal-status toast — fires once per run id when status crosses
  // into a terminal value. Guard via ``lastNotifiedRunId`` so re-renders
  // from polling don't repeat the toast.
  useEffect(() => {
    if (!runResult || !TERMINAL_STATUSES.has(runResult.status)) return;
    if (lastNotifiedRunId.current === runResult.id) return;
    lastNotifiedRunId.current = runResult.id;
    const r = runResult;
    if (r.status === "passed") {
      toast.success(
        `Run pasó · ${r.pass_count}/${r.case_count} · v${r.agent_config_version}`,
      );
    } else if (r.status === "failed") {
      toast.warning(
        `Run falló · ${r.pass_count}/${r.case_count} · v${r.agent_config_version}`,
      );
    } else {
      toast.error(`Run con errores · ${r.error_count} casos en error`);
    }
  }, [runResult]);

  function onCreateDataset(formData: FormData) {
    const name = String(formData.get("name") ?? "").trim();
    const description = String(formData.get("description") ?? "").trim() || null;
    if (!name) {
      toast.error("Nombre requerido");
      return;
    }
    start(async () => {
      const res = await createDatasetAction(tenantId, { name, description });
      if (!res.ok) {
        toast.error(`No se pudo crear: ${res.error}`);
        return;
      }
      toast.success("Dataset creada");
      setCreateDatasetOpen(false);
    });
  }

  function onCreateCase(formData: FormData) {
    if (!primaryDataset) return;
    const name = String(formData.get("name") ?? "").trim();
    const userMessage = String(formData.get("user_message") ?? "").trim();
    const mustContain = String(formData.get("must_contain") ?? "")
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    const judgeQuestions = String(formData.get("judge_questions") ?? "")
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    const mustEmit = formData.get("must_emit_text") === "on";

    if (!name || !userMessage) {
      toast.error("Nombre y mensaje del usuario requeridos");
      return;
    }
    const assertions: Record<string, unknown> = {};
    if (mustContain.length) assertions.must_contain = mustContain;
    if (judgeQuestions.length) assertions.judge_questions = judgeQuestions;
    if (mustEmit) assertions.must_emit_text = true;
    if (Object.keys(assertions).length === 0) {
      toast.error("Agregá al menos una assertion");
      return;
    }
    start(async () => {
      const res = await createCaseAction(tenantId, primaryDataset.id, {
        name,
        user_message: userMessage,
        assertions: assertions as never,
      });
      if (!res.ok) {
        toast.error(`No se pudo crear el caso: ${res.error}`);
        return;
      }
      toast.success("Caso agregado");
      setCreateCaseOpen(false);
    });
  }

  function onDeleteCase(caseId: string) {
    start(async () => {
      const res = await deleteCaseAction(tenantId, caseId);
      if (!res.ok) toast.error(`No se pudo borrar: ${res.error}`);
      else toast.success("Caso borrado");
    });
  }

  function onRun() {
    if (!primaryDataset) return;
    if (primaryDataset.cases.length === 0) {
      toast.error("La dataset no tiene casos");
      return;
    }
    start(async () => {
      const res = await triggerRunAction(tenantId, primaryDataset.id, {});
      if (!res.ok) {
        toast.error(`No se pudo encolar el run: ${res.error}`);
        return;
      }
      // The endpoint returns 202 with status=pending. The polling
      // effect picks it up from here; terminal toast fires once when
      // status crosses into passed/failed/error.
      setRunResult(res.data);
      toast.info(
        `Run encolado · ${res.data.case_count} casos · v${res.data.agent_config_version}`,
      );
    });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div className="flex flex-col gap-1">
            <CardTitle className="inline-flex items-center gap-2">
              <Beaker className="size-4" /> Evals
            </CardTitle>
            <CardDescription>
              Regresión automatizada. Cuando ``eval_required`` esté on, la
              versión no se promueve sin un run en verde reciente (24h).
            </CardDescription>
          </div>
          <div className="flex gap-2 flex-wrap">
            {primaryDataset && primaryDataset.cases.length > 0 ? (
              <Button
                size="sm"
                disabled={pending || isRunInFlight}
                onClick={onRun}
                className="inline-flex items-center gap-1.5"
              >
                {isRunInFlight ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : (
                  <Play className="size-3.5" />
                )}
                {isRunInFlight
                  ? `Corriendo · ${(runResult?.pass_count ?? 0) + (runResult?.fail_count ?? 0) + (runResult?.error_count ?? 0)}/${runResult?.case_count ?? 0}`
                  : pending
                    ? "Encolando…"
                    : "Run evals"}
              </Button>
            ) : null}
            {datasets.length === 0 ? (
              <Button
                variant="outline"
                size="sm"
                disabled={pending}
                onClick={() => setCreateDatasetOpen(true)}
              >
                Crear dataset
              </Button>
            ) : null}
            {primaryDataset ? (
              <Button
                variant="outline"
                size="sm"
                disabled={pending}
                onClick={() => setCreateCaseOpen(true)}
                className="inline-flex items-center gap-1.5"
              >
                <Plus className="size-3.5" /> Agregar caso
              </Button>
            ) : null}
          </div>
        </div>
      </CardHeader>
      <CardContent className="grid gap-4">
        {primaryDataset === null ? (
          <div className="rounded-md border border-dashed border-border bg-muted/30 px-4 py-8 text-center text-sm text-muted-foreground">
            Sin datasets todavía. Creá una para empezar a validar el agente
            antes de promover.
          </div>
        ) : (
          <>
            <DatasetCases
              dataset={primaryDataset}
              pending={pending}
              onDelete={onDeleteCase}
            />
            {isRunInFlight && runResult ? (
              <RunInFlight run={runResult} />
            ) : null}
            <RecentRuns runs={recentRuns} activeVersion={activeVersion} />
            {runResult && TERMINAL_STATUSES.has(runResult.status) ? (
              <RunInline run={runResult} />
            ) : null}
          </>
        )}
      </CardContent>

      <Dialog open={createDatasetOpen} onOpenChange={setCreateDatasetOpen}>
        <DialogContent>
          <form action={onCreateDataset}>
            <DialogHeader>
              <DialogTitle>Nueva dataset de evals</DialogTitle>
              <DialogDescription>
                Una dataset agrupa los casos críticos del agente. Típicamente
                una por tenant.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-3 py-2">
              <div className="grid gap-1">
                <Label htmlFor="name">Nombre</Label>
                <Input id="name" name="name" placeholder="regresión core" />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="description">Descripción (opcional)</Label>
                <Textarea
                  id="description"
                  name="description"
                  rows={2}
                  placeholder="casos de borde del flujo de booking"
                />
              </div>
            </div>
            <DialogFooter>
              <Button
                variant="ghost"
                type="button"
                size="sm"
                disabled={pending}
                onClick={() => setCreateDatasetOpen(false)}
              >
                Cancelar
              </Button>
              <Button type="submit" size="sm" disabled={pending}>
                {pending ? "Creando…" : "Crear"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={createCaseOpen} onOpenChange={setCreateCaseOpen}>
        <DialogContent className="max-w-2xl">
          <form action={onCreateCase}>
            <DialogHeader>
              <DialogTitle>Nuevo caso de eval</DialogTitle>
              <DialogDescription>
                Un caso es un mensaje del cliente simulado + las assertions
                que la respuesta debe cumplir. Cada línea de las listas es
                una entrada separada.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-3 py-2 max-h-[60vh] overflow-y-auto pr-2">
              <div className="grid gap-1">
                <Label htmlFor="case-name">Nombre del caso</Label>
                <Input
                  id="case-name"
                  name="name"
                  placeholder="saludo inicial"
                />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="user_message">Mensaje del cliente</Label>
                <Textarea
                  id="user_message"
                  name="user_message"
                  rows={2}
                  placeholder="hola, ¿qué horarios tienen?"
                />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="must_contain">
                  must_contain (una por línea)
                </Label>
                <Textarea
                  id="must_contain"
                  name="must_contain"
                  rows={3}
                  placeholder={"horario\nLun-Vie"}
                  className="font-mono text-xs"
                />
              </div>
              <div className="grid gap-1">
                <Label htmlFor="judge_questions">
                  judge_questions — preguntas yes/no al LLM judge (una por
                  línea)
                </Label>
                <Textarea
                  id="judge_questions"
                  name="judge_questions"
                  rows={3}
                  placeholder={"¿respondió en español?\n¿se ofreció a agendar?"}
                  className="text-xs"
                />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" name="must_emit_text" defaultChecked />
                must_emit_text (la respuesta debe ser no-vacía)
              </label>
            </div>
            <DialogFooter>
              <Button
                variant="ghost"
                type="button"
                size="sm"
                disabled={pending}
                onClick={() => setCreateCaseOpen(false)}
              >
                Cancelar
              </Button>
              <Button type="submit" size="sm" disabled={pending}>
                {pending ? "Agregando…" : "Agregar caso"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function DatasetCases({
  dataset,
  pending,
  onDelete,
}: {
  dataset: EvalDatasetDetail;
  pending: boolean;
  onDelete: (caseId: string) => void;
}) {
  return (
    <div className="grid gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono uppercase text-muted-foreground tracking-wider">
          Dataset · {dataset.name} · v{dataset.version} · threshold{" "}
          {Number(dataset.pass_threshold).toFixed(2)}
        </span>
        <span className="text-xs text-muted-foreground tabular-nums">
          {dataset.cases.length} caso{dataset.cases.length === 1 ? "" : "s"}
        </span>
      </div>
      {dataset.cases.length === 0 ? (
        <div className="rounded-md border border-dashed border-border bg-muted/30 px-4 py-6 text-center text-sm text-muted-foreground">
          Sin casos todavía. Agregá uno con &quot;Agregar caso&quot;.
        </div>
      ) : (
        <ul className="grid gap-1">
          {dataset.cases.map((c) => (
            <li
              key={c.id}
              className="flex items-start justify-between gap-3 rounded-md border border-border px-3 py-2"
            >
              <div className="flex-1 min-w-0 grid gap-0.5">
                <span className="text-sm font-medium">{c.name}</span>
                <span className="text-xs text-muted-foreground truncate">
                  {c.user_message}
                </span>
                <div className="flex flex-wrap gap-1 mt-1">
                  {Object.keys(c.assertions).map((k) => (
                    <Badge
                      key={k}
                      variant="outline"
                      className="text-[10px] uppercase font-mono"
                    >
                      {k}
                    </Badge>
                  ))}
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                disabled={pending}
                onClick={() => onDelete(c.id)}
                aria-label="Borrar caso"
                className="size-8 p-0 shrink-0"
              >
                <Trash2 className="size-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RecentRuns({
  runs,
  activeVersion,
}: {
  runs: EvalRun[];
  activeVersion: number | null;
}) {
  if (runs.length === 0) {
    return (
      <div className="text-xs text-muted-foreground">
        Sin runs todavía. Clickeá &quot;Run evals&quot; cuando tengas casos.
      </div>
    );
  }
  return (
    <div className="grid gap-2">
      <span className="text-xs font-mono uppercase text-muted-foreground tracking-wider">
        Últimos runs
      </span>
      <ul className="grid gap-1">
        {runs.slice(0, 5).map((r) => (
          <li
            key={r.id}
            className="flex items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-sm"
          >
            <div className="flex items-center gap-2 min-w-0">
              <Badge variant={STATUS_TONE[r.status]} className="uppercase text-[10px]">
                {r.status}
              </Badge>
              <span className="font-mono">
                v{r.agent_config_version}
                {activeVersion === r.agent_config_version ? (
                  <span className="text-[10px] text-muted-foreground"> (activa)</span>
                ) : null}
              </span>
              <span className="text-xs text-muted-foreground tabular-nums">
                {r.pass_count}/{r.case_count} ·{" "}
                {(Number(r.pass_rate) * 100).toFixed(0)}%
              </span>
            </div>
            <span className="text-[10px] text-muted-foreground tabular-nums">
              {r.finished_at
                ? new Date(r.finished_at).toLocaleString()
                : "en curso"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RunInFlight({ run }: { run: EvalRunDetail }) {
  const completed = run.pass_count + run.fail_count + run.error_count;
  const total = run.case_count || run.results.length || 0;
  const pct = total > 0 ? Math.min(100, Math.round((completed / total) * 100)) : 0;
  return (
    <div
      className="grid gap-2 rounded-md border border-border bg-card px-4 py-3"
      aria-live="polite"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Loader2 className="size-3.5 animate-spin text-primary" />
          <span className="text-sm font-medium">
            Corriendo evals · v{run.agent_config_version}
          </span>
          <Badge variant="secondary" className="uppercase text-[10px]">
            {run.status}
          </Badge>
        </div>
        <span className="text-xs text-muted-foreground tabular-nums">
          {completed}/{total} · {pct}%
        </span>
      </div>
      <div
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={completed}
        aria-label="Progreso del run de evals"
        className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
      >
        <div
          className="h-full bg-primary transition-[width] duration-300 ease-out"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-[11px] text-muted-foreground">
        El run corre en segundo plano (background task). Esta vista se
        actualiza sola; podés navegar y volver — el progreso continúa.
      </p>
    </div>
  );
}

function RunInline({ run }: { run: EvalRunDetail }) {
  const failed = run.results.filter((r) => r.status !== "pass");
  if (failed.length === 0) return null;
  return (
    <div className="grid gap-2 border-t border-border pt-3">
      <span className="text-xs font-mono uppercase text-muted-foreground tracking-wider">
        Detalle de fallas — run actual
      </span>
      {failed.map((r) => (
        <details
          key={r.id}
          className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm"
        >
          <summary className="cursor-pointer flex items-center gap-2">
            <Badge variant="destructive" className="uppercase text-[10px]">
              {r.status}
            </Badge>
            <span className="font-medium">{r.case_name}</span>
          </summary>
          <ul className="mt-2 grid gap-1 text-xs">
            {(r.assertion_results as Array<{
              kind: string;
              pass: boolean;
              detail: string;
            }>).map((a, i) =>
              a.pass ? null : (
                <li key={i} className="flex items-start gap-2">
                  <Badge
                    variant="outline"
                    className="font-mono text-[9px] uppercase"
                  >
                    {a.kind}
                  </Badge>
                  <span>{a.detail}</span>
                </li>
              ),
            )}
          </ul>
        </details>
      ))}
    </div>
  );
}
