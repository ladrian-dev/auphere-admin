"use client";

import { useState } from "react";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Field,
  Textarea,
} from "@nexus/ui";
import { REASON_MAX } from "@/lib/levers";

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  pendingLabel: string;
  /** The dry run takes an optional reason; the switch needs one. */
  optional?: boolean;
  destructive?: boolean;
  hint: string;
  validate: (reason: string) => string | null;
  /** Resolves to the failure in words, or `null` when it went through (the dialog closes). */
  onConfirm: (reason: string | null) => Promise<string | null>;
};

/**
 * Spec 047 (T172): a write of the new console with its reason, which goes to
 * the report and to the audit. The API's refusal stays in the dialog.
 */
export function ReasonDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  pendingLabel,
  optional = false,
  destructive = false,
  hint,
  validate,
  onConfirm,
}: Props) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  function change(next: boolean) {
    if (!next) {
      setReason("");
      setError(null);
      setFailure(null);
    }
    onOpenChange(next);
  }

  async function submit() {
    setFailure(null);
    const why = validate(reason);
    setError(why);
    if (why) return;
    setPending(true);
    try {
      const failed = await onConfirm(reason.trim() || null);
      if (failed) {
        setFailure(failed);
        return;
      }
      change(false);
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={change}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <Field
            label={optional ? "Motivo (opcional)" : "Motivo"}
            required={!optional}
            requiredLabel="Obligatorio"
            hint={hint}
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
            <Button type="button" variant="ghost" onClick={() => change(false)} disabled={pending}>
              Cancelar
            </Button>
            <Button type="submit" variant={destructive ? "destructive" : "default"} disabled={pending}>
              {pending ? pendingLabel : confirmLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
