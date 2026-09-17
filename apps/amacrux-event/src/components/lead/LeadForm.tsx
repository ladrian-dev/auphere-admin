"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/Button";
import { Callout } from "@/components/ui/Callout";
import { Checkbox } from "@/components/ui/Checkbox";
import { TextField } from "@/components/ui/TextField";
import { ArrowRightIcon } from "@/components/ui/icons";
import type { Lead, PartialAnswers, Result } from "@/domain/types";
import { AnswersSchema, LeadFormSchema, type LeadFormValues } from "@/domain/validation";
import { track } from "@/lib/analytics";
import { readCampaignInfo } from "@/lib/campaign";
import { newIdempotencyKey } from "@/lib/idempotency";
import { LeadSubmitError, defaultLeadRepository, type LeadRepository } from "@/lib/leads/repository";

export interface LeadFormProps {
  result: Result;
  answers: PartialAnswers;
  campaign?: string;
  repository?: LeadRepository;
  onSubmitted: (delivered: boolean) => void;
}

type Status = { kind: "idle" } | { kind: "submitting" } | { kind: "error"; message: string; retryable: boolean };

const ERROR_MESSAGES: Record<LeadSubmitError["kind"], string> = {
  invalid: "Revisa los campos marcados y vuelve a intentarlo.",
  rate_limited: "Has enviado varios formularios seguidos. Espera unos minutos y reintenta.",
  unavailable: "El envío no está disponible ahora mismo. Reintenta en un momento o acércate al equipo de Amacrux.",
  delivery_failed: "No hemos podido enviar tu contacto. Reintenta en unos segundos; tu resultado sigue aquí.",
  network: "No hemos podido enviar tu contacto: parece que no hay conexión. Reintenta cuando la recuperes; no perderás lo escrito.",
  timeout: "No hemos podido enviar tu contacto: la red tarda demasiado. Reintenta; no perderás lo escrito.",
};

export function LeadForm({ result, answers, campaign, repository, onSubmitted }: LeadFormProps) {
  const repo = useMemo(() => repository ?? defaultLeadRepository(), [repository]);
  const keyRef = useRef<string | null>(null);
  const inFlight = useRef(false);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const topCategory = result.recommendations[0].opportunity.category;

  const form = useForm<LeadFormValues>({
    resolver: zodResolver(LeadFormSchema),
    defaultValues: { name: "", company: "", email: "", phone: "", interest: topCategory, consentContact: false as unknown as true, consentMarketing: false },
    mode: "onSubmit",
    reValidateMode: "onChange",
  });

  useEffect(() => {
    track("contact_form_viewed", { intentLevel: result.segment.intent, campaign });
  }, [result.segment.intent, campaign]);

  const onValid = async (values: LeadFormValues) => {
    if (inFlight.current) return;
    if (!keyRef.current) keyRef.current = newIdempotencyKey();
    const idempotencyKey = keyRef.current;
    const parsedAnswers = AnswersSchema.safeParse({ ...answers, ...(campaign ? { campaign } : {}) });
    if (!parsedAnswers.success) {
      setStatus({ kind: "error", message: "Faltan respuestas del diagnóstico. Vuelve al resultado y reinténtalo.", retryable: false });
      return;
    }
    inFlight.current = true;
    setStatus({ kind: "submitting" });
    const info = readCampaignInfo();
    const lead: Lead = {
      name: values.name,
      company: values.company,
      email: values.email,
      role: undefined,
      phone: values.phone && values.phone.length > 0 ? values.phone : undefined,
      interest: values.interest,
      consentContact: true,
      consentMarketing: values.consentMarketing ?? false,
      resultSnapshot: {
        scoreTotal: result.score.total,
        range: result.score.range,
        leadTier: result.score.leadTier,
        segment: result.segment,
        recommendationIds: result.recommendations.map((r) => r.opportunity.id),
      },
      answers: parsedAnswers.data,
      campaign: campaign ?? info.campaign,
      utm: info.utm,
      idempotencyKey,
      fax: (document.getElementById("lead-fax") as HTMLInputElement | null)?.value ?? "",
    };
    try {
      const outcome = await repo.saveLead(lead);
      track("lead_submitted", { intentLevel: result.segment.intent, recommendationCategory: values.interest, campaign });
      setStatus({ kind: "idle" });
      onSubmitted(outcome.delivered || outcome.stored === true);
    } catch (e) {
      const kind = e instanceof LeadSubmitError ? e.kind : "delivery_failed";
      if (e instanceof LeadSubmitError && e.kind === "invalid" && e.fields) {
        for (const [field, message] of Object.entries(e.fields)) form.setError(field as keyof LeadFormValues, { message });
      }
      setStatus({ kind: "error", message: ERROR_MESSAGES[kind], retryable: kind !== "invalid" });
      track("error_shown", { step: "lead", campaign });
    } finally {
      inFlight.current = false;
    }
  };

  const { errors } = form.formState;
  const submitting = status.kind === "submitting";

  return (
    <form onSubmit={(e) => void form.handleSubmit(onValid)(e)} noValidate className="fade-up">
      <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-accent-deep">Último paso</p>
      <h1 className="mb-2 font-display text-3xl font-bold text-ink">Tu diagnóstico está listo</h1>
      <p className="mb-6 text-sm text-ink-muted">Déjanos tus datos para verlo. Solo los usaremos para que Amacrux te escriba sobre tu diagnóstico.</p>

      <div className="grid gap-4">
        <TextField label="Nombre y apellido" autoComplete="name" error={errors.name?.message} {...form.register("name")} />
        <TextField label="Empresa" autoComplete="organization" error={errors.company?.message} {...form.register("company")} />
        <TextField label="Correo profesional" type="email" inputMode="email" autoComplete="email" error={errors.email?.message} {...form.register("email")} />
        <TextField label="Teléfono" optional type="tel" inputMode="tel" autoComplete="tel" hint="Solo si prefieres que te llamen o te escriban por WhatsApp." error={errors.phone?.message} {...form.register("phone")} />

        <input type="hidden" {...form.register("interest")} />

        {/* Honeypot: invisible para personas; los bots lo rellenan. */}
        <div aria-hidden className="absolute -left-[9999px] top-0 h-0 w-0 overflow-hidden">
          <label htmlFor="lead-fax">Fax</label>
          <input id="lead-fax" name="fax" type="text" tabIndex={-1} autoComplete="off" />
        </div>

        <Checkbox
          label="Acepto que Amacrux me contacte sobre este diagnóstico"
          description="Solo para esto. Puedes retirarlo cuando quieras."
          error={errors.consentContact?.message}
          {...form.register("consentContact")}
        />
        <input type="hidden" {...form.register("consentMarketing")} />
      </div>

      {status.kind === "error" ? (
        <div className="mt-4">
          <Callout tone="warning" title="No hemos podido enviar tu contacto">
            {status.message}
            {/* TODO_COMERCIAL: validar con Amacrux la vía alternativa de contacto (correo o WhatsApp). */}
          </Callout>
        </div>
      ) : null}

      <div className="mt-6 flex flex-col gap-3">
        <Button type="submit" variant="accent" size="lg" full loading={submitting} loadingLabel="Enviando…">
          {status.kind === "error" && status.retryable ? "Reintentar" : "Ver mi diagnóstico"}
          <ArrowRightIcon />
        </Button>
      </div>
      <p className="mt-4 text-xs text-ink-muted">
        Al enviar aceptas el tratamiento descrito en la{" "}
        <a href="/privacidad" className="underline underline-offset-2">
          política de privacidad
        </a>
        .
      </p>
    </form>
  );
}
