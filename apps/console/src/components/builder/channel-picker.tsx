"use client";

import { ArrowRight, Check } from "lucide-react";
import * as React from "react";

import { StatusBadge, cn } from "@nexus/ui";

import { BrandLogo } from "@/components/brand-logo";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";

/**
 * Los canales que se ven en la rejilla, en el orden del prototipo aprobado
 * (`agente.md` §7.1): los de Meta primero. Hoy solo WhatsApp se conecta; el
 * resto se enseña apagado con «Próximamente» o «Pendiente». Los nombres son
 * marcas y no se traducen.
 */
export type ChannelKind = {
  id: "whatsapp" | "messenger" | "instagram" | "threads" | "tiktok" | "telegram" | "x";
  name: string;
  meta: boolean;
  state: "open" | "soon" | "pending";
  body: MessageKey;
  note?: MessageKey;
};

export const CHANNEL_KINDS: readonly ChannelKind[] = [
  { id: "whatsapp", name: "WhatsApp", meta: true, state: "open", body: "channels.proto.kind.whatsapp", note: "channels.proto.kind.whatsapp.note" },
  { id: "messenger", name: "Messenger", meta: true, state: "soon", body: "channels.proto.kind.messenger" },
  { id: "instagram", name: "Instagram", meta: true, state: "soon", body: "channels.proto.kind.instagram" },
  { id: "threads", name: "Threads", meta: true, state: "soon", body: "channels.proto.kind.threads" },
  { id: "tiktok", name: "TikTok", meta: false, state: "pending", body: "channels.proto.kind.tiktok", note: "channels.proto.kind.tiktok.note" },
  { id: "telegram", name: "Telegram", meta: false, state: "soon", body: "channels.proto.kind.telegram" },
  { id: "x", name: "X", meta: false, state: "soon", body: "channels.proto.kind.x" },
];

/** 0 elegir, 1 conectar, 2 configurar, 3 listo. */
export type WizardStep = 0 | 1 | 2 | 3;

const STEPS = [
  ["channels.proto.step.choose", "channels.proto.step.choose.hint"],
  ["channels.proto.step.connect", "channels.proto.step.connect.hint"],
  ["channels.proto.step.configure", "channels.proto.step.configure.hint"],
  ["channels.proto.step.ready", "channels.proto.step.ready.hint"],
] as const satisfies ReadonlyArray<readonly [MessageKey, MessageKey]>;

/**
 * El asistente de la pestaña Canales (`agente.md` §7.1, hueco H4): a la
 * izquierda los cuatro pasos (el actual en verde, los hechos con ✓); a la
 * derecha «Elige un canal» y la rejilla. Una tarjeta que se conecta es un
 * botón; las demás no lo son (`aria-disabled`, sobre fondo apagado).
 *
 * `connected` dice cuántos números tiene ya el agente de cada canal: la
 * tarjeta lo cuenta y ofrece «Conectar otro número».
 */
export function ChannelWizard({
  step,
  connected,
  onConnect,
  headingRef,
  available = [],
}: {
  step: WizardStep;
  connected: Partial<Record<ChannelKind["id"], number>>;
  onConnect: (kind: ChannelKind["id"]) => void;
  headingRef?: React.Ref<HTMLHeadingElement>;
  /** Spec 049: channels switched on for this partner (Instagram, Messenger
   *  in beta): their card connects instead of saying «soon». */
  available?: readonly ChannelKind["id"][];
}) {
  const t = useT();
  const titleId = React.useId();
  const kinds = CHANNEL_KINDS.map((k) => (available.includes(k.id) ? { ...k, state: "open" as const } : k));
  return (
    <section
      aria-labelledby={titleId}
      data-slot="channel-wizard"
      className="grid min-w-0 overflow-hidden rounded-lg border border-border bg-card lg:grid-cols-[240px_minmax(0,1fr)]"
    >
      <ol aria-label={t("channels.proto.steps")} className="grid content-start gap-4 px-5 py-6">
        {STEPS.map(([title, hint], i) => {
          const on = i === step;
          const done = i < step;
          return (
            <li key={title} aria-current={on ? "step" : undefined} className="grid grid-cols-[32px_minmax(0,1fr)] items-start gap-3">
              <span
                className={cn(
                  "grid size-8 place-items-center rounded-full text-sm tabular-nums",
                  on || done ? "bg-status-positive-bg text-status-positive-text" : "bg-muted text-muted-foreground",
                  on && "font-semibold",
                )}
              >
                {done ? (
                  <>
                    <Check aria-hidden="true" className="size-4" data-slot="step-done" />
                    <span className="sr-only">{t("channels.proto.step.done")}</span>
                  </>
                ) : (
                  <span aria-hidden="true">{i + 1}</span>
                )}
              </span>
              <span className="grid min-w-0 gap-1">
                <span data-slot="step-title" className={cn("mt-1 text-base font-medium", on && "text-status-positive-text")}>
                  {t(title)}
                </span>
                <span className="text-sm text-pretty text-muted-foreground">{t(hint)}</span>
              </span>
            </li>
          );
        })}
      </ol>
      <div className="min-w-0 border-t border-border p-6 lg:border-t-0 lg:border-l">
        <h2 id={titleId} ref={headingRef} tabIndex={-1} className="text-xl font-semibold tracking-tight outline-none">
          {t("channels.proto.pick.title")}
        </h2>
        <p className="mt-1 max-w-prose text-sm text-pretty text-muted-foreground">{t("channels.proto.pick.intro")}</p>
        <ul aria-label={t("channels.proto.pick.list")} className="mt-5 grid auto-rows-fr grid-cols-[repeat(auto-fill,minmax(232px,1fr))] gap-4">
          {kinds.map((kind) => (
            <li key={kind.id} className="min-w-0">
              <ChannelCard kind={kind} count={connected[kind.id] ?? 0} onConnect={onConnect} />
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function ChannelCard({ kind, count, onConnect }: { kind: ChannelKind; count: number; onConnect: (kind: ChannelKind["id"]) => void }) {
  const t = useT();
  const open = kind.state === "open";
  const inner = (
    <>
      <span className="mb-1 flex w-full items-start justify-between gap-2">
        <BrandLogo brand={kind.id} size="xl" />
        {kind.meta ? <span className="text-xs text-muted-foreground">{t("channels.proto.meta")}</span> : null}
      </span>
      <span className="flex min-w-0 flex-wrap items-center gap-2">
        <span data-slot="channel-name" className="text-base font-medium">
          {kind.name}
        </span>
        {kind.state === "soon" ? <StatusBadge tone="muted">{t("channels.proto.soon")}</StatusBadge> : null}
        {kind.state === "pending" ? <StatusBadge tone="warn">{t("channels.proto.pending")}</StatusBadge> : null}
      </span>
      <span className="text-sm text-pretty text-muted-foreground">{t(kind.body)}</span>
      {kind.note ? <span className="text-xs text-pretty text-muted-foreground">{t(kind.note)}</span> : null}
      {count > 0 ? (
        <StatusBadge tone="positive">{count === 1 ? t("channels.proto.connected.one") : t("channels.proto.connected.other", { n: count })}</StatusBadge>
      ) : null}
      {open ? (
        <span className="mt-auto inline-flex items-center gap-2 pt-2 text-sm font-medium text-primary-text">
          {count > 0 ? t("channels.proto.cta.another") : t("channels.proto.cta")}
          <ArrowRight aria-hidden="true" className="size-4" />
        </span>
      ) : null}
    </>
  );
  const base = "flex h-full min-h-58 w-full min-w-0 flex-col items-start gap-2 rounded-lg border border-border p-5 text-left";
  if (!open) {
    return (
      <div aria-disabled="true" data-slot="channel-card" className={cn(base, "bg-muted")}>
        {inner}
      </div>
    );
  }
  return (
    <button
      type="button"
      data-slot="channel-card"
      aria-label={t("channels.proto.cta.aria", { name: kind.name })}
      onClick={() => onConnect(kind.id)}
      className={cn(
        base,
        "cursor-pointer bg-card transition-[border-color,box-shadow] duration-150 outline-none hover:border-input hover:shadow-md focus-visible:ring-2 focus-visible:ring-ring motion-reduce:transition-none",
      )}
    >
      {inner}
    </button>
  );
}
