"use client";

import { ArrowRight, Check, CircleAlert, CircleCheck, LoaderCircle, Play, TriangleAlert, X } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Field,
  Input,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Textarea,
} from "@nexus/ui";

import { publishAction, publishPreviewAction, qualityJobAction, undoPublishAction } from "@/app/(console)/clients/[ref]/agents/quality-actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { DiffRow, Gate, PublishBody, PublishPreview, PublishResult, QualityJob, TestSummary } from "@/lib/backend/agent-quality-types";

import { barState } from "./agent-proto-model";
import { sleep, type Result } from "./builder-model";
import { channelsHref, partKey, undoOpen, waitForJob } from "./quality-model";

type Ids = { ref: string; agent: string };
export type PublishActions = {
  preview: (body: Ids) => Promise<Result<PublishPreview>>;
  publish: (body: Ids & PublishBody) => Promise<Result<{ job_id: string }>>;
  poll: (body: { ref: string; job: string }) => Promise<Result<QualityJob>>;
  undo: (body: Ids) => Promise<Result<{ number: number }>>;
};

const SERVER_ACTIONS: PublishActions = {
  preview: (body) => publishPreviewAction(body),
  publish: (body) => publishAction(body),
  poll: (body) => qualityJobAction(body),
  undo: (body) => undoPublishAction(body),
};

const CONDITIONS = new Set(["validator", "critical_tests", "regression", "ai_disclosure", "review"]);
const STEPS = new Set(["testing", "deciding"]);
/** Sonner necesita una duración: la de la ventana de «Deshacer», como mucho 10 minutos. */
const UNDO_MAX_MS = 10 * 60 * 1000;

/**
 * La barra de acción de la pantalla del agente (spec 047, historia 9;
 * requisitos 23 y 24.1). Guardar es publicar, con red: el botón dice lo que va
 * a pasar —«Guardar», «Guardar y conectar un canal» (y después lleva a los
 * canales) o «Guardar cambios» (y antes enseña el diff en lenguaje llano)—, y
 * el trabajo prueba, revisa y decide.
 *
 * Si no pasa la puerta, se dice condición a condición. Con solo pruebas
 * normales en rojo hay «Guardar igualmente», con confirmación. Con una crítica
 * o un bloqueante, solo un owner o un admin ve «Guardar igualmente…», que pide
 * el motivo; a los demás no se les enseña un control que no pueden usar (§V).
 * Después de guardar, el aviso trae «Deshacer» mientras dura su ventana.
 *
 * Como el prototipo aprobado (§4.5): a la izquierda el estado con su icono, a
 * la derecha los botones píldora. Con las pruebas de la pantalla dice en qué
 * punto están («Borrador completo» con «Ejecutar pruebas», «1 de 20 pruebas
 * falla» con «Guardar igualmente», «20 de 20 pruebas pasan · guardado») y solo
 * ofrece guardar lo que hay que guardar. La puerta bloqueada se explica en una
 * hoja lateral («Ver por qué»), no dentro de la barra.
 */
export function PublishBar({
  refId,
  agentId,
  preview: initial,
  hadActive,
  canWrite,
  refreshKey = 0,
  tests = null,
  pendingQuestions = 0,
  onConnect,
  onPublished,
  actions = SERVER_ACTIONS,
  wait = sleep,
}: {
  refId: string;
  agentId: string;
  /** `null` si no se pudo leer. */
  preview: PublishPreview | null;
  /** Había una versión atendiendo: «Deshacer» tiene adónde volver. */
  hadActive: boolean;
  canWrite: boolean;
  refreshKey?: number;
  /** Las pruebas de la pantalla: en qué punto están y «Ejecutar pruebas». Sin ellas, la barra de siempre. */
  tests?: { summary: TestSummary | null; running: boolean; canRun: boolean; run: () => void } | null;
  /** Las preguntas del borrador nuevo sin responder (§4.5, fila 3): se puede probar igualmente. */
  pendingQuestions?: number;
  /** Conectar un canal sin salir de la pantalla (la pestaña Canales). Sin él, la página de canales del cliente. */
  onConnect?: () => void;
  /** Se publicó o se deshizo: el borrador, el historial y las pruebas cambiaron. */
  onPublished?: () => void;
  actions?: PublishActions;
  wait?: (ms: number) => Promise<void>;
}) {
  const t = useT();
  const router = useRouter();
  const ids = React.useMemo(() => ({ ref: refId, agent: agentId }), [refId, agentId]);
  const [preview, setPreview] = React.useState(initial);
  const [step, setStep] = React.useState<string | null>(null);
  const [gate, setGate] = React.useState<Gate | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [diffOpen, setDiffOpen] = React.useState(false);
  const [note, setNote] = React.useState("");
  const [confirmNormal, setConfirmNormal] = React.useState(false);
  const [overrideOpen, setOverrideOpen] = React.useState(false);
  const [gateOpen, setGateOpen] = React.useState(false);
  const running = step !== null;

  const reload = React.useCallback(async () => {
    const res = await actions.preview(ids);
    if (res.ok) setPreview(res.data);
  }, [actions, ids]);

  const seen = React.useRef(refreshKey);
  React.useEffect(() => {
    if (seen.current === refreshKey) return;
    seen.current = refreshKey;
    void reload();
  }, [refreshKey, reload]);

  async function undo() {
    const res = await actions.undo(ids);
    if (res.ok) {
      toast.success(t("builder.publish.undone", { n: res.data.number }));
      onPublished?.();
      return;
    }
    toast.error(res.code === "undo_window_closed" ? t("builder.publish.undo.closed") : t("builder.publish.error.generic"));
  }

  async function publish(body: PublishBody = {}) {
    if (!preview) return;
    const action = preview.action;
    setStep("queued");
    setGate(null);
    setError(null);
    const res = await actions.publish({ ...ids, ...(note.trim() ? { note: note.trim() } : {}), ...body });
    if (!res.ok) {
      setStep(null);
      setError(
        res.code === "override_forbidden"
          ? t("builder.publish.error.forbidden")
          : res.code === "no_draft"
            ? t("builder.publish.error.noDraft")
            : res.status === 401 || res.status === 403
              ? t("common.forbidden")
              : t("builder.publish.error.generic"),
      );
      return;
    }
    const done = await waitForJob(() => actions.poll({ ref: refId, job: res.data.job_id }), {
      wait,
      onUpdate: (job) => setStep(job.progress?.step && STEPS.has(job.progress.step) ? job.progress.step : "queued"),
    });
    setStep(null);
    if (!done) return;
    if (!done.ok) {
      setError(t("builder.publish.error.generic"));
      return;
    }
    const job = done.data;
    if (job.status === "done") {
      const result = job.result as PublishResult | null;
      setNote("");
      setDiffOpen(false);
      const open = hadActive && undoOpen(result?.undo_until);
      const left = open && result ? Math.min(Date.parse(result.undo_until) - Date.now(), UNDO_MAX_MS) : undefined;
      toast.success(t("builder.publish.saved", { n: result?.number ?? "" }), {
        ...(open ? { action: { label: t("builder.publish.undo"), onClick: () => void undo() }, duration: left } : {}),
      });
      onPublished?.();
      await reload();
      if (action === "save_and_connect") {
        if (onConnect) onConnect();
        else router.push(channelsHref(refId));
      }
      return;
    }
    if (job.error_code === "gate_blocked") {
      const block = job.progress?.blocks?.find((b) => b.key === "gate") as (Gate & { key: string }) | undefined;
      setGate(block ? { ...EMPTY_GATE, ...block } : EMPTY_GATE);
      setDiffOpen(false);
      setGateOpen(true);
      return;
    }
    setError(
      job.error_code === "override_forbidden"
        ? t("builder.publish.error.forbidden")
        : job.error_code === "no_draft"
          ? t("builder.publish.error.noDraft")
          : t("builder.publish.error.generic"),
    );
  }

  function save() {
    if (!preview) return;
    if (preview.action === "save_changes") setDiffOpen(true);
    else void publish();
  }

  if (!preview) {
    return (
      <div className="flex min-w-0 flex-wrap items-center gap-2 text-sm" data-slot="publish-bar">
        <p className="text-muted-foreground">{t("builder.publish.error.generic")}</p>
        <Button size="sm" variant="outline" onClick={() => void reload()}>
          {t("builder.suite.retry")}
        </Button>
      </div>
    );
  }

  const canSkip = gate !== null && gate.hard.length === 0;
  const offerOverride = canSkip && gate.overridable.length > 0 && preview.can_override;
  const offerAnyway = canSkip && gate.overridable.length === 0 && gate.normal_failures.length > 0;

  // Qué dice la barra y qué ofrece; lo que está pasando ahora manda sobre las pruebas.
  const state = barState({ canWrite, preview, tests: tests ? { summary: tests.summary, running: tests.running, canRun: tests.canRun } : null });
  const saveButton = (
    <Button key="save" onClick={save} loading={running} className={PILL}>
      {t(`builder.publish.${preview.action}` as MessageKey)}
      {preview.action === "save_and_connect" ? <ArrowRight aria-hidden="true" /> : null}
    </Button>
  );
  let icon: React.ReactNode = null;
  let text: string;
  let buttons: React.ReactElement[] = [];
  switch (state.kind) {
    case "readonly":
      text = t("builder.publish.readonly");
      break;
    case "running":
      icon = <LoaderCircle aria-hidden="true" className={`${ICON} animate-spin motion-reduce:animate-none`} />;
      text = t("agentProto.bar.running");
      break;
    case "failing":
      icon = <TriangleAlert aria-hidden="true" className={`${ICON} text-warning`} />;
      text = t(state.failing === 1 ? "agentProto.bar.failing.one" : "agentProto.bar.failing.other", { n: state.failing, total: state.total });
      if (state.save)
        buttons = [
          <Button key="anyway" variant="outline" onClick={save} loading={running} className={PILL}>
            {t("builder.publish.anyway")}
          </Button>,
        ];
      break;
    case "passing":
      icon = <CircleCheck aria-hidden="true" className={`${ICON} text-status-positive-text`} />;
      text = t(state.saved ? "agentProto.bar.passing.saved" : "agentProto.bar.passing", { passed: state.passed, total: state.total });
      if (state.next === "save") buttons = [saveButton];
      else if (state.next === "connect" && onConnect)
        buttons = [
          <Button key="connect" onClick={onConnect} className={PILL}>
            {t("agentProto.bar.connect")}
            <ArrowRight aria-hidden="true" />
          </Button>,
        ];
      break;
    case "pending":
      text = state.draft ? t("agentProto.bar.complete") : t("agentProto.bar.notRun");
      buttons = [
        <Button key="run" onClick={() => tests?.run()} className={PILL}>
          <Play aria-hidden="true" />
          {t("agentProto.bar.run")}
        </Button>,
      ];
      break;
    case "plain":
      if (preview.has_draft) {
        text = t("builder.publish.hint");
        buttons = [saveButton];
      } else text = t("builder.publish.nothing");
      break;
  }
  // §4.5, fila 3: con preguntas sin responder y las pruebas sin terminar, se dice que se puede probar igualmente.
  if (pendingQuestions > 0 && (state.kind === "pending" || state.kind === "plain") && canWrite) {
    icon = null;
    text = t(pendingQuestions === 1 ? "agentProto.bar.pending.one" : "agentProto.bar.pending.other", { n: pendingQuestions });
  }
  if (running) {
    icon = <LoaderCircle aria-hidden="true" className={`${ICON} animate-spin motion-reduce:animate-none`} />;
    text = t(`builder.publish.step.${step}` as MessageKey);
    buttons = [];
  } else if (gate && canWrite) {
    // No pasó la puerta: se dice aquí y se explica en la hoja.
    icon = <TriangleAlert aria-hidden="true" className={`${ICON} text-warning`} />;
    text = t("builder.publish.blocked.title");
    buttons = [
      <Button key="why" variant="outline" onClick={() => setGateOpen(true)} className={PILL}>
        {t("agentProto.bar.why")}
      </Button>,
      ...buttons.filter((b) => b.key === "run"),
    ];
  }

  return (
    <div role="region" aria-label={t("builder.publish.bar")} className="flex min-w-0 flex-wrap items-center justify-between gap-x-3 gap-y-2" data-slot="publish-bar">
      {error ? (
        <p role="alert" className="inline-flex min-w-0 items-center gap-2 text-sm text-pretty text-destructive">
          <CircleAlert aria-hidden="true" className={ICON} />
          <span className="min-w-0">{error}</span>
        </p>
      ) : (
        <p role="status" className="inline-flex min-w-0 items-center gap-2 text-sm text-pretty text-muted-foreground">
          {icon}
          <span className="min-w-0">{text}</span>
        </p>
      )}
      {buttons.length ? <div className="ml-auto flex min-w-0 flex-wrap gap-2 max-[560px]:w-full max-[560px]:*:flex-1">{buttons}</div> : null}

      <Sheet open={gateOpen && gate !== null} onOpenChange={setGateOpen}>
        <SheetContent className="w-full gap-0 sm:max-w-md">
          <SheetHeader>
            <SheetTitle>{t("agentProto.gate.title")}</SheetTitle>
            <SheetDescription>{t("agentProto.gate.intro")}</SheetDescription>
          </SheetHeader>
          <div className="grid min-w-0 gap-4 overflow-y-auto px-4 pb-4">
            {gate ? (
              <GateNotice
                gate={gate}
                offerAnyway={offerAnyway && canWrite}
                offerOverride={offerOverride && canWrite}
                onAnyway={() => setConfirmNormal(true)}
                onOverride={() => setOverrideOpen(true)}
              />
            ) : null}
          </div>
        </SheetContent>
      </Sheet>

      <Sheet open={diffOpen} onOpenChange={setDiffOpen}>
        <SheetContent className="w-full gap-0 sm:max-w-md">
          <SheetHeader>
            <SheetTitle>{t("builder.publish.diff.title")}</SheetTitle>
            <SheetDescription>{t("builder.publish.diff.intro")}</SheetDescription>
          </SheetHeader>
          <div className="grid min-w-0 gap-4 overflow-y-auto px-4 pb-4">
            <DiffList rows={preview.diff} />
            <Field label={t("builder.publish.note")}>
              {(a11y) => <Input {...a11y} value={note} maxLength={500} autoComplete="off" onChange={(e) => setNote(e.target.value)} />}
            </Field>
          </div>
          <SheetFooter className="flex-row flex-wrap justify-end">
            <Button variant="outline" onClick={() => setDiffOpen(false)} disabled={running}>
              {t("builder.publish.cancel")}
            </Button>
            <Button onClick={() => void publish()} loading={running}>
              {t("builder.publish.save_changes")}
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>

      <ConfirmDialog
        open={confirmNormal}
        onOpenChange={setConfirmNormal}
        title={t("builder.publish.anyway.title")}
        description={t("builder.publish.anyway.body", { names: gate?.normal_failures.join(", ") ?? "" })}
        confirmLabel={t("builder.publish.anyway")}
        cancelLabel={t("builder.publish.cancel")}
        onConfirm={async () => {
          setConfirmNormal(false);
          setGateOpen(false);
          await publish({ accept_normal_failures: true });
        }}
      />

      {offerOverride ? (
        <OverrideDialog
          open={overrideOpen}
          onOpenChange={setOverrideOpen}
          busy={running}
          onConfirm={async (reason) => {
            setOverrideOpen(false);
            setGateOpen(false);
            await publish({ override_reason: reason, accept_normal_failures: true });
          }}
        />
      ) : null}
    </div>
  );
}

/** Los botones de la barra flotante son píldoras, como el prototipo. */
const PILL = "rounded-full";
const ICON = "size-4 shrink-0";

const EMPTY_GATE: Gate = { conditions: [], hard: [], overridable: [], normal_failures: [], rate: null, reference_rate: null };

/** El diff en lenguaje llano: «+ Reglas», «~ Instrucciones», «− Recepción» (23.5). */
export function DiffList({ rows }: { rows: readonly DiffRow[] }) {
  const t = useT();
  if (!rows.length) return <p className="text-sm text-muted-foreground">{t("builder.publish.diff.empty")}</p>;
  return (
    <ul className="grid min-w-0 gap-2" data-slot="publish-diff">
      {rows.map((row, i) => {
        const key = partKey(row.part);
        const label = key ? t(key) : row.label;
        const verb = row.change === "add" ? "builder.publish.diff.add" : row.change === "remove" ? "builder.publish.diff.remove" : "builder.publish.diff.replace";
        return (
          <li key={`${row.part}-${i}`} className="grid min-w-0 gap-1 text-sm">
            <span className="font-medium">{t(verb, { label })}</span>
            {row.added?.length ? <span className="text-xs break-words text-muted-foreground">{t("builder.publish.diff.added", { items: row.added.join(", ") })}</span> : null}
            {row.removed?.length ? <span className="text-xs break-words text-muted-foreground">{t("builder.publish.diff.removed", { items: row.removed.join(", ") })}</span> : null}
          </li>
        );
      })}
    </ul>
  );
}

function GateNotice({
  gate,
  offerAnyway,
  offerOverride,
  onAnyway,
  onOverride,
}: {
  gate: Gate;
  offerAnyway: boolean;
  offerOverride: boolean;
  onAnyway: () => void;
  onOverride: () => void;
}) {
  const t = useT();
  return (
    <Callout
      tone="danger"
      title={t("builder.publish.blocked.title")}
      action={
        offerAnyway ? (
          <Button size="sm" variant="outline" onClick={onAnyway}>
            {t("builder.publish.anyway")}
          </Button>
        ) : offerOverride ? (
          <Button size="sm" variant="outline" onClick={onOverride}>
            {t("builder.publish.override")}
          </Button>
        ) : undefined
      }
    >
      <div className="grid min-w-0 gap-3 text-foreground" data-slot="publish-gate">
        {gate.conditions.length ? (
          <div className="grid min-w-0 gap-1">
            <p className="text-xs font-medium text-muted-foreground">{t("builder.publish.blocked.conditions")}</p>
            <ul className="grid min-w-0 gap-1">
              {gate.conditions.map((c) => (
                <li key={c.condition} className="flex min-w-0 items-start gap-2" data-ok={c.ok}>
                  {c.ok ? (
                    <Check aria-hidden="true" className="mt-1 size-4 shrink-0 text-status-positive-text" />
                  ) : (
                    <X aria-hidden="true" className="mt-1 size-4 shrink-0 text-destructive" />
                  )}
                  <span className="min-w-0 text-pretty">
                    {CONDITIONS.has(c.condition) ? t(`builder.publish.condition.${c.condition}` as MessageKey) : c.condition}
                    <span className="sr-only"> · {c.ok ? t("builder.publish.condition.ok") : t("builder.publish.condition.no")}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <Items title={t("builder.publish.blocked.hard")} items={gate.hard.map((h) => h.message)} />
        <Items title={t("builder.publish.blocked.overridable")} items={gate.overridable.map((o) => o.message)} />
        <Items title={t("builder.publish.blocked.normal")} items={gate.normal_failures} />
      </div>
    </Callout>
  );
}

function Items({ title, items }: { title: string; items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="grid min-w-0 gap-1">
      <p className="text-xs font-medium">{title}</p>
      <ul className="grid min-w-0 list-disc gap-1 pl-5">
        {items.map((item, i) => (
          <li key={i} className="text-pretty break-words">
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Saltar la puerta: solo owner o admin, y siempre con el motivo (23.3). */
function OverrideDialog({
  open,
  onOpenChange,
  busy,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  busy: boolean;
  onConfirm: (reason: string) => Promise<void>;
}) {
  const t = useT();
  const [reason, setReason] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (reason.trim().length < 3) {
      setError(t("builder.publish.override.required"));
      return;
    }
    setError(null);
    void onConfirm(reason.trim());
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          setReason("");
          setError(null);
        }
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <form onSubmit={submit} noValidate className="grid min-w-0 gap-4">
          <DialogHeader>
            <DialogTitle>{t("builder.publish.override.title")}</DialogTitle>
            <DialogDescription>{t("builder.publish.override.body")}</DialogDescription>
          </DialogHeader>
          <Field label={t("builder.publish.override.reason")} error={error ?? undefined} required>
            {(a11y) => <Textarea {...a11y} value={reason} rows={3} maxLength={500} onChange={(e) => setReason(e.target.value)} />}
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              {t("builder.publish.cancel")}
            </Button>
            <Button type="submit" loading={busy}>
              {t("builder.publish.override.confirm")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
