"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
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
  Section,
  StatusBadge,
  Textarea,
} from "@nexus/ui";
import type { SovereignState } from "@/lib/backend-levers";
import { REASON_MAX, reasonError } from "@/lib/levers";

import { setSovereignAction } from "./sovereign-actions";
import { SOVEREIGN_ERRORS, SOVEREIGN_WHAT, sovereignCopy } from "./sovereign";

type Props = { tenantId: string; clientName: string; state: SovereignState | null };

/**
 * Spec 047 (T172, 54.6): the client's sovereign restriction — only European
 * providers and open weights. Only Auphere sets it, always with a reason that
 * goes to the audit; the partner sees it as a badge.
 */
export function SovereignCard({ tenantId, clientName, state }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  if (state === null) {
    return (
      <Section title="Restricción soberana" description={SOVEREIGN_WHAT}>
        <p className="text-sm text-muted-foreground">No se pudo leer. Vuelve a intentarlo en un momento.</p>
      </Section>
    );
  }

  const copy = sovereignCopy(state, clientName);
  const noProfile = state.has_profile === false;

  async function submit() {
    setFailure(null);
    const why = reasonError(reason);
    setError(why);
    if (why || !state) return;
    setPending(true);
    try {
      const result = await setSovereignAction(tenantId, { enabled: !state.enabled, reason: reason.trim() });
      if (!result.ok) {
        setFailure(result.error);
        return;
      }
      toast.success(copy.done);
      setOpen(false);
      setReason("");
      router.refresh();
    } finally {
      setPending(false);
    }
  }

  return (
    <Section
      title="Restricción soberana"
      description={SOVEREIGN_WHAT}
      actions={<StatusBadge tone={copy.tone}>{copy.badge}</StatusBadge>}
    >
      <div className="flex flex-col gap-3">
        {noProfile ? (
          <Callout tone="info" title="Sin ficha del negocio">
            {SOVEREIGN_ERRORS.no_business_profile}
          </Callout>
        ) : null}
        <Dialog
          open={open}
          onOpenChange={(next) => {
            setOpen(next);
            if (!next) {
              setReason("");
              setError(null);
              setFailure(null);
            }
          }}
        >
          <Button
            variant={state.enabled ? "outline" : "default"}
            size="sm"
            className="self-start"
            disabled={noProfile}
            onClick={() => setOpen(true)}
          >
            {copy.action}
          </Button>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{copy.title}</DialogTitle>
              <DialogDescription>{copy.description}</DialogDescription>
            </DialogHeader>
            <form
              className="flex flex-col gap-4"
              onSubmit={(e) => {
                e.preventDefault();
                void submit();
              }}
            >
              <Field
                label="Motivo"
                required
                requiredLabel="Obligatorio"
                hint="Queda en la auditoría con tu nombre. Por ejemplo: «El contrato del cliente lo exige»."
                error={error ?? undefined}
              >
                {(a11y) => (
                  <Textarea {...a11y} rows={2} maxLength={REASON_MAX} value={reason} onChange={(e) => setReason(e.target.value)} />
                )}
              </Field>
              {failure ? (
                <p role="alert" className="text-sm text-destructive text-pretty">
                  {failure}
                </p>
              ) : null}
              <DialogFooter>
                <Button type="button" variant="ghost" onClick={() => setOpen(false)} disabled={pending}>
                  Cancelar
                </Button>
                <Button type="submit" disabled={pending}>
                  {pending ? "Guardando…" : copy.action}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>
    </Section>
  );
}
