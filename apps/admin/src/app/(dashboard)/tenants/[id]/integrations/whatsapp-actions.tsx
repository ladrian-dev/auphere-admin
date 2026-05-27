"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import type { WhatsAppPreview } from "@/lib/backend";

import {
  connectWhatsAppManualAction,
  verifyWhatsAppAction,
} from "./actions";

// See ``connectors/setup-wizards.tsx`` for the rationale on why the
// wizard asks for the E.164 phone instead of the Meta phone_number_id.
const E164_RE = /^\+\d{8,15}$/;

const schema = z.object({
  waba_id: z.string().min(1, "Requerido").max(64),
  phone_number_e164: z
    .string()
    .min(1, "Requerido")
    .max(20)
    .transform((v) => v.replace(/[\s-]/g, ""))
    .refine(
      (v) => E164_RE.test(v),
      "Debe estar en formato E.164 (ej. +34632719028)",
    ),
});

type FormValues = z.infer<typeof schema>;

type Step = "form" | "preview";

export function ConnectWhatsAppManualDialog({
  tenantId,
  alreadyConnected,
}: {
  tenantId: string;
  alreadyConnected: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<Step>("form");
  const [preview, setPreview] = useState<WhatsAppPreview | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [, startTransition] = useTransition();

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { waba_id: "", phone_number_e164: "" },
  });

  function reset() {
    form.reset();
    setPreview(null);
    setStep("form");
    setSubmitting(false);
  }

  async function onVerify(values: FormValues) {
    setSubmitting(true);
    try {
      const result = await verifyWhatsAppAction(
        values.waba_id.trim(),
        values.phone_number_e164,
      );
      if (!result.ok) {
        toast.error("YCloud rechazó la verificación", { description: result.error });
        return;
      }
      setPreview(result.data);
      setStep("preview");
    } finally {
      setSubmitting(false);
    }
  }

  async function onConfirm() {
    if (!preview) return;
    setSubmitting(true);
    try {
      const result = await connectWhatsAppManualAction(tenantId, {
        waba_id: preview.waba_id,
        phone_number_e164: preview.phone_number,
      });
      if (!result.ok) {
        toast.error("No se pudo conectar el número", { description: result.error });
        return;
      }
      toast.success("WhatsApp conectado", {
        description: `${result.data.phone_number} — listo para recibir mensajes.`,
      });
      startTransition(() => {
        setOpen(false);
        reset();
      });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger
        render={
          <Button variant={alreadyConnected ? "outline" : "default"}>
            {alreadyConnected ? "Reconectar" : "Conectar manualmente"}
          </Button>
        }
      />
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Conectar WhatsApp (manual)</DialogTitle>
          <DialogDescription>
            Pegá el WABA ID y el número de teléfono que figura en tu dashboard
            de YCloud. El backend confirma con YCloud antes de guardar.
          </DialogDescription>
        </DialogHeader>

        {step === "form" ? (
          <Form {...form}>
            <form
              onSubmit={form.handleSubmit(onVerify)}
              className="flex flex-col gap-4"
              noValidate
            >
              <FormField
                control={form.control}
                name="waba_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>WABA ID</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        autoComplete="off"
                        className="font-mono"
                        placeholder="123456789012345"
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="phone_number_e164"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Número de teléfono</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        type="tel"
                        autoComplete="off"
                        inputMode="tel"
                        className="font-mono"
                        placeholder="+34632719028"
                      />
                    </FormControl>
                    <p className="mt-1.5 text-[11px] text-muted-foreground">
                      Formato E.164: empieza con + y código de país.
                    </p>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <DialogFooter>
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setOpen(false)}
                  disabled={submitting}
                >
                  Cancelar
                </Button>
                <Button type="submit" disabled={submitting}>
                  {submitting ? "Verificando…" : "Verificar"}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        ) : preview ? (
          <div className="flex flex-col gap-4 text-sm">
            <div className="rounded-md border border-border bg-muted/30 p-4 text-sm">
              <PreviewRow label="Teléfono" value={preview.phone_number} mono />
              <PreviewRow
                label="Display name"
                value={preview.display_name ?? "—"}
              />
              <PreviewRow
                label="Verified name"
                value={preview.verified_name ?? "—"}
              />
              <PreviewRow
                label="Quality rating"
                value={preview.quality_rating ?? "—"}
              />
              <PreviewRow label="WABA" value={preview.waba_id} mono />
            </div>
            <p className="text-muted-foreground">
              Confirmá si los datos coinciden con la cuenta del owner antes de
              guardar. El número quedará atado a este tenant.
            </p>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setStep("form")}
                disabled={submitting}
              >
                Atrás
              </Button>
              <Button onClick={onConfirm} disabled={submitting}>
                {submitting ? "Guardando…" : "Confirmar y conectar"}
              </Button>
            </DialogFooter>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

function PreviewRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-1">
      <span
        className="text-[10px] font-mono uppercase text-muted-foreground"
        style={{ letterSpacing: "var(--tracking-eyebrow)" }}
      >
        {label}
      </span>
      <span className={mono ? "font-mono" : undefined}>{value}</span>
    </div>
  );
}
