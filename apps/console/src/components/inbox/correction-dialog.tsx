"use client";

import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Field,
  StatusBadge,
  Textarea,
} from "@nexus/ui";

import { createCorrectionAction, editCorrectionAction, sendCorrectionAction, undoCorrectionAction } from "@/app/(console)/inbox/correction-actions";
import type { Result } from "@/components/builder/builder-model";
import { idempotencyKey, piiKindKey, piiSpans } from "@/components/lite/lite-agents-model";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { InboxThreadItem } from "@/lib/backend/inbox";
import { CORRECTION_LIMITS, type Correction, type CorrectionPii, type CorrectionScope } from "@/lib/backend/inbox-corrections";

export type CorrectionActions = {
  create: (body: { conversation: string; message: string; text: string; scope: CorrectionScope; key?: string }) => Promise<Result<Correction>>;
  edit: (body: { id: string; revision: number; lesson?: string; paraphrase?: string }) => Promise<Result<Correction>>;
  send: (body: { id: string; revision: number }) => Promise<Result<Correction>>;
  undo: (body: { id: string }) => Promise<Result<Correction>>;
};

const SERVER_ACTIONS: CorrectionActions = {
  create: (b) => createCorrectionAction(b),
  edit: (b) => editCorrectionAction(b),
  send: (b) => sendCorrectionAction(b),
  undo: (b) => undoCorrectionAction(b),
};

type Failure = Extract<Result<unknown>, { ok: false }>;

const EXCERPT = 240;

/**
 * «Corregir esta respuesta» (spec 047, T176; requisitos 52.1 a 52.6), sobre una
 * respuesta del agente en la Bandeja de la consola lite. Tres pasos:
 *
 * 1. **Escribir**: cómo debió responder (o la regla) y el alcance, «Todo el
 *    negocio» o «Solo este agente», que se elige siempre (no hay uno por defecto).
 * 2. **Revisar**: antes de enviar se ve si es un dato (se aplica al momento) o un
 *    comportamiento (llega al partner como propuesta), y la paráfrasis de lo que
 *    preguntó el cliente, que se puede editar. Si la corrección o la paráfrasis
 *    llevan un teléfono, un nombre, un correo o un documento de un cliente
 *    final, se dice cuál y dónde, y no se envía hasta quitarlo (garantía 8).
 * 3. **Hecho**: un dato se puede deshacer; un comportamiento espera al partner.
 *
 * El partner nunca recibe el mensaje original: solo la lección y la paráfrasis.
 */
export function CorrectionDialog({
  conversationId,
  message,
  onClose,
  actions = SERVER_ACTIONS,
}: {
  conversationId: string;
  message: InboxThreadItem;
  onClose: () => void;
  actions?: CorrectionActions;
}) {
  const t = useT();
  const base = React.useId();
  // Una clave por apertura: «Continuar» dos veces no crea dos borradores.
  const key = React.useMemo(() => idempotencyKey(), []);
  const [text, setText] = React.useState("");
  const [scope, setScope] = React.useState<CorrectionScope | null>(null);
  const [draft, setDraft] = React.useState<Correction | null>(null);
  const [lesson, setLesson] = React.useState("");
  const [paraphrase, setParaphrase] = React.useState("");
  const [problem, setProblem] = React.useState<string | null>(null);
  const [fieldError, setFieldError] = React.useState<{ text?: string; scope?: string; paraphrase?: string }>({});
  const [pending, startTransition] = React.useTransition();
  const [undone, setUndone] = React.useState(false);

  const done = draft !== null && draft.status !== "draft";
  const dirty = draft !== null && (lesson !== draft.lesson || paraphrase !== (draft.paraphrase ?? ""));
  const spans = draft && !dirty ? piiSpans(draft.pii, { lesson: draft.lesson, paraphrase: draft.paraphrase }) : [];
  const excerpt = (message.text ?? "").length > EXCERPT ? `${(message.text ?? "").slice(0, EXCERPT - 1)}…` : (message.text ?? "");

  function take(next: Correction) {
    setDraft(next);
    setLesson(next.lesson);
    setParaphrase(next.paraphrase ?? "");
  }

  function failure(res: Failure): string {
    switch (res.code) {
      case "not_an_agent_reply":
        return t("lite.correct.error.notAgent");
      case "pii_present":
        return t("lite.correct.error.pii");
      case "paraphrase_required":
        return t("lite.correct.error.paraphrase");
      case "rule_too_long":
        return t("lite.correct.error.ruleTooLong", { max: Number(res.info?.max ?? CORRECTION_LIMITS.rule) });
      case "revision_conflict":
        return t("lite.correct.error.conflict");
      case "not_a_draft":
        return t("lite.correct.error.notDraft");
      case "invalid_proposal":
        return t("lite.correct.error.invalid");
      case "agent_archived":
        return t("lite.correct.error.agentGone");
      default:
        if (res.status === 404) return t("lite.correct.error.gone");
        if (res.status === 403) return t("lite.correct.error.forbidden");
        return t("lite.correct.error.generic");
    }
  }

  function start(event: React.FormEvent) {
    event.preventDefault();
    const errors: { text?: string; scope?: string } = {};
    if (!text.trim()) errors.text = t("lite.correct.error.textRequired");
    if (!scope) errors.scope = t("lite.correct.error.scopeRequired");
    setFieldError(errors);
    if (errors.text || errors.scope || !scope) return;
    setProblem(null);
    startTransition(async () => {
      const res = await actions.create({ conversation: conversationId, message: message.id, text: text.trim(), scope, key });
      if (res.ok) take(res.data);
      else setProblem(failure(res));
    });
  }

  function send() {
    if (!draft) return;
    if (!lesson.trim()) return setFieldError({ text: t("lite.correct.error.textRequired") });
    setFieldError({});
    setProblem(null);
    startTransition(async () => {
      let current = draft;
      if (dirty) {
        const edited = await actions.edit({ id: current.id, revision: current.revision, lesson: lesson.trim(), paraphrase });
        if (!edited.ok) {
          conflictOr(edited);
          return;
        }
        take(edited.data);
        current = edited.data;
        // Lo que se acaba de escribir se vuelve a mirar: si aún lleva un dato, se dice antes de enviar.
        if (current.pii.length) {
          setProblem(t("lite.correct.error.pii"));
          return;
        }
      }
      const sent = await actions.send({ id: current.id, revision: current.revision });
      if (sent.ok) {
        take(sent.data);
        return;
      }
      if (sent.code === "pii_present" && Array.isArray(sent.info?.pii)) {
        setDraft({ ...current, pii: sent.info.pii as CorrectionPii[] });
      }
      // Falta la paráfrasis: se dice bajo su campo, no también abajo.
      if (sent.code === "paraphrase_required") return setFieldError({ paraphrase: t("lite.correct.error.paraphrase") });
      conflictOr(sent);
    });
  }

  function conflictOr(res: Failure) {
    const current = res.info?.current as Correction | undefined;
    if (res.status === 412 && current && typeof current === "object" && "id" in current) take(current);
    setProblem(failure(res));
  }

  function undo() {
    if (!draft) return;
    startTransition(async () => {
      const res = await actions.undo({ id: draft.id });
      if (res.ok) {
        take(res.data);
        setUndone(true);
        toast.success(t("lite.correct.undone"));
      } else setProblem(res.code === "undo_not_available" || res.code === "not_applied" ? t("lite.correct.error.undo") : failure(res));
    });
  }

  const agentName = draft?.agent.name ?? message.author?.name ?? t("lite.correct.theAgent");

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90svh] overflow-y-auto" data-slot="correction-dialog">
        <DialogHeader>
          <DialogTitle>{t("lite.correct.title")}</DialogTitle>
          <DialogDescription>{done ? t("lite.correct.done.description") : t("lite.correct.description")}</DialogDescription>
        </DialogHeader>

        {excerpt ? (
          <figure className="grid min-w-0 gap-1">
            <figcaption className="text-xs font-medium text-muted-foreground">{t("lite.correct.answer")}</figcaption>
            <blockquote className="max-h-32 overflow-y-auto rounded-md bg-muted px-3 py-2 text-sm text-pretty whitespace-pre-wrap [overflow-wrap:anywhere]">{excerpt}</blockquote>
          </figure>
        ) : null}

        {draft === null ? (
          <form onSubmit={start} className="grid min-w-0 gap-4" noValidate>
            <Field label={t("lite.correct.text")} required hint={t("lite.correct.text.hint")} error={fieldError.text}>
              {(a11y) => <Textarea {...a11y} value={text} maxLength={CORRECTION_LIMITS.lesson} rows={4} onChange={(e) => setText(e.target.value)} />}
            </Field>
            <fieldset className="grid min-w-0 gap-2" aria-describedby={fieldError.scope ? `${base}-scope-error` : undefined}>
              <legend className="text-sm font-medium">{t("lite.correct.scope")}</legend>
              {(["business", "agent"] as const).map((s) => (
                <label key={s} className="flex min-h-6 items-start gap-2 text-sm">
                  <input type="radio" name={`${base}-scope`} className="mt-1 size-4 accent-primary" checked={scope === s} onChange={() => setScope(s)} />
                  <span className="grid">
                    {t(`lite.correct.scope.${s}` as MessageKey)}
                    <span className="text-xs text-muted-foreground">{t(`lite.correct.scope.${s}.hint` as MessageKey)}</span>
                  </span>
                </label>
              ))}
              {fieldError.scope ? (
                <p id={`${base}-scope-error`} className="text-sm text-destructive">
                  {fieldError.scope}
                </p>
              ) : null}
            </fieldset>
            {problem ? (
              <p role="alert" className="text-sm text-destructive">
                {problem}
              </p>
            ) : null}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>
                {t("lite.correct.cancel")}
              </Button>
              <Button type="submit" loading={pending}>
                {t("lite.correct.next")}
              </Button>
            </DialogFooter>
          </form>
        ) : done ? (
          <div className="grid min-w-0 gap-4" data-slot="correction-done">
            <Callout tone={undone ? "info" : "positive"}>
              {undone
                ? t("lite.correct.done.undone")
                : draft.status === "applied"
                  ? t("lite.correct.done.data", { agent: agentName })
                  : t("lite.correct.done.behavior")}
            </Callout>
            {problem ? (
              <p role="alert" className="text-sm text-destructive">
                {problem}
              </p>
            ) : null}
            <DialogFooter>
              {draft.status === "applied" && !undone ? (
                <Button type="button" variant="outline" loading={pending} onClick={undo}>
                  {t("lite.correct.undo")}
                </Button>
              ) : null}
              <Button type="button" onClick={onClose}>
                {t("lite.correct.close")}
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="grid min-w-0 gap-4" data-slot="correction-review">
            <div className="grid min-w-0 gap-1" data-kind={draft.kind}>
              <StatusBadge tone={draft.kind === "data" ? "info" : "warn"} className="justify-self-start">
                {t(draft.kind === "data" ? "lite.correct.kind.data" : "lite.correct.kind.behavior")}
              </StatusBadge>
              <p className="text-sm text-pretty">
                {draft.kind === "data"
                  ? draft.scope === "business"
                    ? t("lite.correct.kind.data.business")
                    : t("lite.correct.kind.data.agent", { agent: agentName })
                  : t("lite.correct.kind.behavior.body")}
              </p>
            </div>
            <Field label={t("lite.correct.lesson")} required error={fieldError.text}>
              {(a11y) => <Textarea {...a11y} value={lesson} maxLength={CORRECTION_LIMITS.lesson} rows={3} onChange={(e) => setLesson(e.target.value)} />}
            </Field>
            <Field label={t("lite.correct.paraphrase")} hint={t("lite.correct.paraphrase.hint")} error={fieldError.paraphrase}>
              {(a11y) => <Textarea {...a11y} value={paraphrase} maxLength={CORRECTION_LIMITS.paraphrase} rows={2} onChange={(e) => setParaphrase(e.target.value)} />}
            </Field>
            {spans.length ? (
              <Callout tone="danger" title={t("lite.correct.pii.title")}>
                <ul className="grid list-disc gap-1 pl-5" data-slot="correction-pii">
                  {spans.map((s, i) => (
                    <li key={`${s.field}-${i}`} className="break-words">
                      {t(s.field === "lesson" ? "lite.correct.pii.inLesson" : "lite.correct.pii.inParaphrase", { what: t(piiKindKey(s.kind)), text: s.text })}
                    </li>
                  ))}
                </ul>
              </Callout>
            ) : draft.pii.length && dirty ? (
              <p className="text-sm text-muted-foreground">{t("lite.correct.pii.recheck")}</p>
            ) : null}
            {problem ? (
              <p role="alert" className="text-sm text-destructive">
                {problem}
              </p>
            ) : null}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={onClose}>
                {t("lite.correct.cancel")}
              </Button>
              <Button type="button" loading={pending} disabled={spans.length > 0} onClick={send}>
                {t(draft.kind === "data" ? "lite.correct.send.data" : "lite.correct.send.behavior")}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
