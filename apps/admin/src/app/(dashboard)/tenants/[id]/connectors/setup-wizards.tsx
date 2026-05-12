"use client";

import { useState, useTransition } from "react";
import { Activity, KeyRound } from "lucide-react";
import { toast } from "sonner";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

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
import { Label } from "@/components/ui/label";
import type { WhatsAppPreview } from "@/lib/backend";

import {
  agendaProHealthCheckAction,
  agendaProSetupAction,
  connectWhatsAppSetupAction,
  verifyWhatsAppAction,
} from "./setup-actions";

// ── WhatsApp YCloud manual wizard ──────────────────────────────────────────

const whatsappSchema = z.object({
  waba_id: z.string().min(1, "Requerido").max(64),
  phone_number_id: z.string().min(1, "Requerido").max(64),
});

type WhatsappFormValues = z.infer<typeof whatsappSchema>;
type WhatsappStep = "form" | "preview";

export function WhatsAppSetupDialog({
  tenantId,
  alreadyConnected,
}: {
  tenantId: string;
  alreadyConnected: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<WhatsappStep>("form");
  const [preview, setPreview] = useState<WhatsAppPreview | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [, startTransition] = useTransition();

  const form = useForm<WhatsappFormValues>({
    resolver: zodResolver(whatsappSchema),
    defaultValues: { waba_id: "", phone_number_id: "" },
  });

  function reset() {
    form.reset();
    setPreview(null);
    setStep("form");
    setSubmitting(false);
  }

  async function onVerify(values: WhatsappFormValues) {
    setSubmitting(true);
    try {
      const result = await verifyWhatsAppAction(
        values.waba_id,
        values.phone_number_id,
      );
      if (!result.ok) {
        toast.error("YCloud rechazó la verificación", {
          description: result.error,
        });
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
      const result = await connectWhatsAppSetupAction(tenantId, {
        waba_id: preview.waba_id,
        phone_number_id: preview.phone_number_id,
      });
      if (!result.ok) {
        toast.error("No se pudo conectar el número", {
          description: result.error,
        });
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
          <Button size="sm" variant={alreadyConnected ? "outline" : "default"}>
            {alreadyConnected ? "Reconectar" : "Conectar"}
          </Button>
        }
      />
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Conectar WhatsApp</DialogTitle>
          <DialogDescription>
            Pegá el WABA ID y el Phone Number ID que copiaste del dashboard de
            YCloud. Confirmamos contra YCloud antes de guardar.
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
                name="phone_number_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Phone Number ID</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        autoComplete="off"
                        className="font-mono"
                        placeholder="987654321098765"
                      />
                    </FormControl>
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
              guardar. El número queda atado a este tenant.
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

// ── AgendaPro browser_credentials wizard ───────────────────────────────────

export function AgendaProSetupDialog({
  tenantId,
  alreadyConnected,
}: {
  tenantId: string;
  alreadyConnected: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [pending, startTransition] = useTransition();

  function runHealthCheck() {
    startTransition(async () => {
      const result = await agendaProHealthCheckAction(tenantId);
      if (!result.ok) {
        toast.error("Health check falló", { description: result.error });
        return;
      }
      const { healthy, needs_reauth, notes } = result.data;
      if (healthy) {
        toast.success("AgendaPro saludable", {
          description: notes ?? "Sesión válida.",
        });
      } else if (needs_reauth) {
        toast.warning("Re-auth requerida", {
          description:
            notes ?? "El re-login automático falló. Re-bootstrap manual.",
        });
      } else {
        toast.info("Health check completado", {
          description: notes ?? "Revisá el detalle en el log.",
        });
      }
    });
  }

  return (
    <div className="flex items-center gap-2">
      {alreadyConnected ? (
        <Button
          variant="ghost"
          size="sm"
          onClick={runHealthCheck}
          disabled={pending}
        >
          <Activity className="size-4" />
          {pending ? "Verificando…" : "Verificar"}
        </Button>
      ) : null}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger
          render={
            <Button size="sm" variant={alreadyConnected ? "outline" : "default"}>
              <KeyRound className="size-4" />
              {alreadyConnected ? "Reconectar" : "Conectar"}
            </Button>
          }
        />
        <DialogContent>
          <AgendaProBootstrapForm
            tenantId={tenantId}
            onClose={() => setOpen(false)}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AgendaProBootstrapForm({
  tenantId,
  onClose,
}: {
  tenantId: string;
  onClose: () => void;
}) {
  const [pending, startTransition] = useTransition();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [businessUrl, setBusinessUrl] = useState("");

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!login || !password) {
      toast.error("Faltan datos", {
        description: "Email + contraseña requeridos.",
      });
      return;
    }
    startTransition(async () => {
      const result = await agendaProSetupAction(tenantId, {
        login,
        password,
        business_url: businessUrl || null,
      });
      if (!result.ok) {
        toast.error("Bootstrap falló", { description: result.error });
        return;
      }
      toast.success("AgendaPro conectado", {
        description: `context_id ${result.data.context_id.slice(0, 12)}…`,
      });
      onClose();
    });
  }

  return (
    <form onSubmit={onSubmit} className="grid gap-5">
      <DialogHeader>
        <DialogTitle>Conectar AgendaPro</DialogTitle>
        <DialogDescription className="space-y-2">
          <span className="block">
            AgendaPro no expone OAuth ni API key pública, así que el agente
            opera con la sesión del owner. Pegamos sus credenciales una vez,
            las ciframos con Fernet y el agente reutiliza el contexto del
            navegador para crear, modificar y cancelar citas.
          </span>
          <span className="block text-xs">
            Las credenciales no son visibles después de guardarlas y se
            rotan al re-bootstrappear. El agente jamás las recibe en su
            prompt.
          </span>
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-2">
        <Label htmlFor="ap-login">Email</Label>
        <Input
          id="ap-login"
          type="email"
          autoComplete="off"
          placeholder="owner@empresa.com"
          value={login}
          onChange={(e) => setLogin(e.target.value)}
          required
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="ap-password">Contraseña</Label>
        <Input
          id="ap-password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="ap-url">
          URL del negocio{" "}
          <span className="text-muted-foreground text-xs">(opcional)</span>
        </Label>
        <Input
          id="ap-url"
          type="url"
          inputMode="url"
          placeholder="https://miempresa.agendapro.com"
          value={businessUrl}
          onChange={(e) => setBusinessUrl(e.target.value)}
        />
      </div>
      <DialogFooter>
        <Button
          type="button"
          variant="ghost"
          onClick={onClose}
          disabled={pending}
        >
          Cancelar
        </Button>
        <Button type="submit" disabled={pending}>
          {pending ? "Conectando…" : "Conectar"}
        </Button>
      </DialogFooter>
    </form>
  );
}
