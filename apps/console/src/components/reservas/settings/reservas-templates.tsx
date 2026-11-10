"use client";

import * as React from "react";

import { Button, Callout, Section, Skeleton, StatusBadge, cn, type StatusBadgeTone } from "@nexus/ui";

import { reservasTemplatesAction } from "@/app/(console)/reservas/templates-actions";
import type { MessageKey } from "@/i18n/messages";
import {
  RESERVAS_TEMPLATE_NAMES,
  type ReservasTemplate,
  type ReservasTemplateNotCreated,
  type ReservasTemplateRejection,
  type ReservasTemplates,
  type ReservasTemplateState,
} from "@/lib/backend/reservas-templates";

import { useReservas, useWords } from "../context";
import { useActionLoad } from "../model/use-load";

const NAME: Record<string, MessageKey> = {
  reserva_confirmada: "reservas.templates.name.reserva_confirmada",
  reserva_pide_confirmacion: "reservas.templates.name.reserva_pide_confirmacion",
  reserva_recordatorio: "reservas.templates.name.reserva_recordatorio",
  reserva_cambiada: "reservas.templates.name.reserva_cambiada",
  reserva_cancelada: "reservas.templates.name.reserva_cancelada",
  reserva_hueco_libre: "reservas.templates.name.reserva_hueco_libre",
};

const STATE: Record<ReservasTemplateState, { key: MessageKey; tone: StatusBadgeTone }> = {
  approved: { key: "reservas.templates.state.approved", tone: "positive" },
  in_review: { key: "reservas.templates.state.in_review", tone: "info" },
  rejected: { key: "reservas.templates.state.rejected", tone: "danger" },
  paused: { key: "reservas.templates.state.paused", tone: "warning" },
  not_created: { key: "reservas.templates.state.not_created", tone: "muted" },
};

const REJECTION: Record<ReservasTemplateRejection, MessageKey> = {
  invalid_format: "reservas.templates.rejected.invalid_format",
  incorrect_category: "reservas.templates.rejected.incorrect_category",
  promotional: "reservas.templates.rejected.promotional",
  abusive_content: "reservas.templates.rejected.abusive_content",
  other: "reservas.templates.rejected.other",
};

const NOT_CREATED: Record<ReservasTemplateNotCreated, MessageKey> = {
  no_whatsapp: "reservas.templates.why.no_whatsapp",
  on_its_way: "reservas.templates.why.on_its_way",
  deleted: "reservas.templates.why.deleted",
};

/**
 * Spec 043 (requisito 15.7): the six WhatsApp templates of Reservas and how each
 * one stands in Meta. Nothing to do here for the business — the system asks Meta
 * for the missing ones, and a rejected or paused one is fixed by whoever manages
 * the agents — so the screen says what each state means for the notices.
 *
 * The five states: loading (six rows of skeleton), error (says it, retry),
 * empty (no WhatsApp number: none can exist), partial (some approved, the rest
 * say why not) and ideal (the six approved).
 */
export function ReservasTemplatesSection() {
  const { t } = useReservas();
  const [attempt, setAttempt] = React.useState(0);
  const load = useActionLoad(`reservas-templates-${attempt}`, async () => reservasTemplatesAction());
  return (
    <Section title={t("reservas.templates.title")} description={t("reservas.templates.body")}>
      {load.kind === "ok" ? (
        <Loaded data={load.data} />
      ) : load.kind === "error" ? (
        <Callout
          tone="danger"
          action={
            <Button size="xs" variant="outline" onClick={() => setAttempt((n) => n + 1)}>
              {t("common.retry")}
            </Button>
          }
        >
          {t("reservas.templates.loadError")}
        </Callout>
      ) : (
        <div role="status" aria-label={t("reservas.templates.loading")} className="flex min-w-0 flex-col gap-3">
          {RESERVAS_TEMPLATE_NAMES.map((name) => (
            <Skeleton key={name} className="h-14 w-full" />
          ))}
        </div>
      )}
    </Section>
  );
}

function Loaded({ data }: { data: ReservasTemplates }) {
  const { t } = useReservas();
  const total = data.items.length;
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {!data.whatsapp ? (
        <Callout tone="info">{t("reservas.templates.noWhatsapp")}</Callout>
      ) : total > 0 && data.approved === total ? (
        <Callout tone="positive">{t("reservas.templates.allApproved")}</Callout>
      ) : (
        <p className="text-sm text-pretty text-muted-foreground">{t("reservas.templates.someApproved", { approved: data.approved, total })}</p>
      )}
      <ul aria-label={t("reservas.templates.list")} className="flex min-w-0 flex-col divide-y divide-border">
        {data.items.map((item) => (
          <TemplateRow key={item.name} item={item} />
        ))}
      </ul>
    </div>
  );
}

function TemplateRow({ item }: { item: ReservasTemplate }) {
  const { t } = useReservas();
  const words = useWords();
  const nameId = React.useId();
  const state = STATE[item.state] ?? STATE.not_created;
  const lines: string[] = [];
  if (item.state === "in_review") {
    lines.push(item.since ? t("reservas.templates.inReviewSince", { when: words.instant(item.since) }) : t("reservas.templates.inReview"));
  } else if (item.state === "rejected") {
    lines.push(t(REJECTION[item.rejection ?? "other"] ?? REJECTION.other), t("reservas.templates.rejected.next"));
  } else if (item.state === "paused") {
    lines.push(t("reservas.templates.paused"));
  } else if (item.state === "not_created" && item.why_not_created) {
    lines.push(t(NOT_CREATED[item.why_not_created] ?? NOT_CREATED.on_its_way));
  }
  return (
    <li aria-labelledby={nameId} className="flex min-w-0 flex-wrap items-start justify-between gap-x-3 gap-y-1 py-3">
      <div className="flex min-w-0 flex-1 basis-48 flex-col gap-1">
        <span id={nameId} className="text-sm font-medium text-pretty">
          {t(NAME[item.name] ?? "reservas.templates.name.other")}
        </span>
        <code className="truncate font-mono text-xs text-muted-foreground" title={item.name}>
          {item.name}
        </code>
        {lines.map((line) => (
          <p key={line} className={cn("text-xs text-pretty", item.state === "rejected" || item.state === "paused" ? "text-foreground" : "text-muted-foreground")}>
            {line}
          </p>
        ))}
      </div>
      <StatusBadge tone={state.tone}>{t(state.key)}</StatusBadge>
    </li>
  );
}
