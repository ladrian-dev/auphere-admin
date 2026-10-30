"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Field, Input, StatusBadge, Textarea } from "@nexus/ui";

import { useT } from "@/i18n/client";

import type { FaqValue } from "./proposals-model";
import type { Result } from "./section-frame";

export type Decision = "accept" | "edit" | "discard";
/** Lo que se decide: el texto de una política o la pregunta con su respuesta. */
export type SuggestedValue = string | FaqValue;

/**
 * Una propuesta en su sección de Negocio (spec 047, enmienda del 2026-10-29;
 * requisito 60.5): marcada «Sugerido · confirma», con de dónde sale, lo que
 * propone (y lo que hay ahora, si hay algo) y aceptar, editar o descartar. Editar
 * abre el texto en la propia tarjeta y guarda lo editado. Quien solo lee la ve
 * sin botones (§V). Quien decide es `onDecide`: una sugerencia pendiente va por
 * `POST …/suggestions/{id}/decide`; una pregunta guardada como sugerida, por su
 * `PATCH` o su archivo.
 */
export function SuggestionCard({
  title,
  value,
  sourceLabel,
  current,
  canWrite,
  onDecide,
  onDecided,
}: {
  title: string;
  value: SuggestedValue;
  sourceLabel: string;
  current?: string | null;
  canWrite: boolean;
  onDecide: (decision: Decision, value?: SuggestedValue) => Promise<Result<unknown>>;
  onDecided: (decision: Decision) => void;
}) {
  const t = useT();
  const titleId = React.useId();
  const faq = typeof value === "string" ? null : value;
  const body = faq ? faq.a : (value as string);
  const [editing, setEditing] = React.useState(false);
  const [q, setQ] = React.useState(faq?.q ?? "");
  const [text, setText] = React.useState(body);
  const [busy, setBusy] = React.useState<Decision | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  async function send(decision: Decision) {
    let edited: SuggestedValue | undefined;
    if (decision === "edit") {
      edited = faq ? { q: q.trim(), a: text.trim() } : text.trim();
      const empty = typeof edited === "string" ? !edited : !edited.q || !edited.a;
      if (empty) {
        setError(faq ? t("business.faqs.error.required") : t("business.suggested.error.required"));
        return;
      }
    }
    setBusy(decision);
    setError(null);
    const res = await onDecide(decision, edited).catch(() => null);
    setBusy(null);
    if (res?.ok) {
      toast.success(decision === "discard" ? t("business.suggested.discarded") : t("business.suggested.accepted"));
      onDecided(decision);
      return;
    }
    setError(
      res?.code === "already_decided"
        ? t("business.suggested.error.decided")
        : res?.code === "invalid_value"
          ? t("business.suggested.error.invalid")
          : res?.status === 403
            ? t("common.forbidden")
            : t("business.section.error.generic"),
    );
  }

  return (
    <li aria-labelledby={titleId} className="grid min-w-0 gap-2 rounded-md border border-dashed border-input bg-card p-3" data-slot="business-suggestion">
      <div className="flex min-w-0 flex-wrap items-start justify-between gap-2">
        <p id={titleId} className="min-w-0 flex-1 basis-48 text-sm font-medium text-pretty break-words">
          {title}
        </p>
        <StatusBadge tone="warn">{t("business.suggested.badge")}</StatusBadge>
      </div>
      <p className="text-xs text-pretty text-muted-foreground">{sourceLabel}</p>
      {editing ? (
        <form
          noValidate
          className="grid min-w-0 gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void send("edit");
          }}
        >
          {faq ? (
            <Field label={t("business.faqs.q")} required>
              {(a11y) => <Input {...a11y} value={q} maxLength={300} autoComplete="off" onChange={(e) => setQ(e.target.value)} />}
            </Field>
          ) : null}
          <Field label={faq ? t("business.faqs.a") : t("business.suggested.value")} required>
            {(a11y) => <Textarea {...a11y} value={text} rows={3} maxLength={faq ? 2000 : 1000} onChange={(e) => setText(e.target.value)} />}
          </Field>
          {error ? (
            <p role="alert" className="text-xs text-pretty text-destructive">
              {error}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="sm" loading={busy === "edit"}>
              {t("business.suggested.save")}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={() => setEditing(false)} disabled={busy !== null}>
              {t("business.section.cancel")}
            </Button>
          </div>
        </form>
      ) : (
        <>
          <p className="min-w-0 text-sm text-pretty break-words whitespace-pre-line">{body}</p>
          {current ? <p className="min-w-0 text-xs text-pretty break-words text-muted-foreground">{t("business.suggested.current", { value: current })}</p> : null}
          {error ? (
            <p role="alert" className="text-xs text-pretty text-destructive">
              {error}
            </p>
          ) : null}
          {canWrite ? (
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                onClick={() => void send("accept")}
                loading={busy === "accept"}
                disabled={busy !== null && busy !== "accept"}
                aria-label={t("business.suggested.accept.label", { item: title })}
              >
                {t("business.suggested.accept")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setEditing(true)}
                disabled={busy !== null}
                aria-label={t("business.suggested.edit.label", { item: title })}
              >
                {t("business.suggested.edit")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => void send("discard")}
                loading={busy === "discard"}
                disabled={busy !== null && busy !== "discard"}
                aria-label={t("business.suggested.discard.label", { item: title })}
              >
                {t("business.suggested.discard")}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </li>
  );
}
