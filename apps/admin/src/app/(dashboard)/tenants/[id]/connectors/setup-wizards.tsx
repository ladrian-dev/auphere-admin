"use client";

import { useState, useTransition } from "react";
import { KeyRound } from "lucide-react";
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
  agendaProSetPublicUrlAction,
  connectWhatsAppSetupAction,
  connectWooCommerceSetupAction,
  verifyWhatsAppAction,
} from "./setup-actions";

// ── WhatsApp YCloud manual wizard ──────────────────────────────────────────

// YCloud SMB doesn't expose a Meta phone_number_id in its dashboard
// and its WABA-listing endpoint 404s for SMB-bound accounts, so the
// wizard asks for what the operator always has: the E.164 phone number.
// The backend uses it as the second path segment of YCloud's
// ``/whatsapp/phoneNumbers/{wabaId}/{lookup}`` (YCloud soft-matches by
// phone and returns the canonical id in the payload).
const E164_RE = /^\+\d{8,15}$/;

const whatsappSchema = z.object({
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
    defaultValues: { waba_id: "", phone_number_e164: "" },
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
        values.waba_id.trim(),
        values.phone_number_e164,
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
        phone_number_e164: preview.phone_number,
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
            Pegá el WABA ID y el número de teléfono que figura en tu dashboard
            de YCloud. Confirmamos contra YCloud antes de guardar.
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

// ── AgendaPro public-link wizard (ADR-017) ─────────────────────────────────

export function AgendaProSetupDialog({
  tenantId,
  currentUrl,
}: {
  tenantId: string;
  /** Current ``tenants.agendapro_public_url`` — null when unset. */
  currentUrl?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const alreadyConfigured = Boolean(currentUrl);

  return (
    <div className="flex items-center gap-2">
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogTrigger
          render={
            <Button size="sm" variant={alreadyConfigured ? "outline" : "default"}>
              <KeyRound className="size-4" />
              {alreadyConfigured ? "Editar URL" : "Conectar"}
            </Button>
          }
        />
        <DialogContent>
          <AgendaProPublicUrlForm
            tenantId={tenantId}
            currentUrl={currentUrl ?? null}
            onClose={() => setOpen(false)}
          />
        </DialogContent>
      </Dialog>
    </div>
  );
}

function AgendaProPublicUrlForm({
  tenantId,
  currentUrl,
  onClose,
}: {
  tenantId: string;
  currentUrl: string | null;
  onClose: () => void;
}) {
  const [pending, startTransition] = useTransition();
  const [publicUrl, setPublicUrl] = useState(currentUrl ?? "");

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = publicUrl.trim();
    if (!trimmed) {
      toast.error("Falta la URL", {
        description: "Pegá el link público de AgendaPro de tu negocio.",
      });
      return;
    }
    startTransition(async () => {
      const result = await agendaProSetPublicUrlAction(tenantId, trimmed);
      if (!result.ok) {
        toast.error("No se pudo guardar la URL", { description: result.error });
        return;
      }
      toast.success("AgendaPro conectado", {
        description: result.data.public_url ?? "URL guardada.",
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
            El agente usa el <strong>link público</strong> de tu negocio en
            AgendaPro para consultar disponibilidad y crear citas. No
            necesitamos ni guardamos credenciales de admin.
          </span>
          <span className="block text-xs">
            Modificar o cancelar citas todavía no se hace por el link
            público: el agente le consulta al dueño por WhatsApp y avisa al
            cliente cuando reciba respuesta.
          </span>
        </DialogDescription>
      </DialogHeader>
      <div className="grid gap-2">
        <Label htmlFor="ap-public-url">URL pública del negocio</Label>
        <Input
          id="ap-public-url"
          type="url"
          inputMode="url"
          placeholder="https://miempresa.site.agendapro.com"
          value={publicUrl}
          onChange={(e) => setPublicUrl(e.target.value)}
          required
        />
        <p className="text-[11px] text-muted-foreground">
          Pegá la URL que un cliente final usaría para reservar — la que
          empieza con <code>https://</code> y termina en{" "}
          <code>.agendapro.com</code>.
        </p>
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
          {pending ? "Guardando…" : "Guardar"}
        </Button>
      </DialogFooter>
    </form>
  );
}

// ── WooCommerce api_key wizard (ADR-019) ───────────────────────────────────

const woocommerceSchema = z.object({
  store_url: z
    .string()
    .min(1, "Requerido")
    .max(500)
    .url("Debe ser una URL válida")
    .refine((v) => v.startsWith("https://"), {
      message: "La tienda debe estar en https://",
    }),
  consumer_key: z
    .string()
    .min(1, "Requerido")
    .max(200)
    .refine((v) => v.startsWith("ck_"), {
      message: "El Consumer Key empieza con 'ck_'",
    }),
  consumer_secret: z
    .string()
    .min(1, "Requerido")
    .max(200)
    .refine((v) => v.startsWith("cs_"), {
      message: "El Consumer Secret empieza con 'cs_'",
    }),
});

type WooCommerceFormValues = z.infer<typeof woocommerceSchema>;

export function WooCommerceSetupDialog({
  tenantId,
  alreadyConnected,
}: {
  tenantId: string;
  alreadyConnected: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [, startTransition] = useTransition();

  const form = useForm<WooCommerceFormValues>({
    resolver: zodResolver(woocommerceSchema),
    defaultValues: { store_url: "", consumer_key: "", consumer_secret: "" },
  });

  function reset() {
    form.reset();
    setSubmitting(false);
  }

  async function onSubmit(values: WooCommerceFormValues) {
    setSubmitting(true);
    try {
      const result = await connectWooCommerceSetupAction(tenantId, values);
      if (!result.ok) {
        toast.error("No se pudo conectar WooCommerce", {
          description: result.error,
        });
        return;
      }
      toast.success("WooCommerce conectado", {
        description: result.data.store_url,
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
          <Button
            size="sm"
            variant={alreadyConnected ? "outline" : "default"}
          >
            <KeyRound className="size-4" />
            {alreadyConnected ? "Reconectar" : "Conectar"}
          </Button>
        }
      />
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Conectar WooCommerce</DialogTitle>
          <DialogDescription className="space-y-2">
            <span className="block">
              El owner genera las llaves en <strong>WP-Admin → WooCommerce
              → Settings → Advanced → REST API → Add key</strong> con
              permisos <code>Read/Write</code>. WordPress muestra el
              Consumer Key y Secret una sola vez — copiá ambos antes de
              salir de la pantalla.
            </span>
            <span className="block text-xs">
              El secret se guarda encriptado (Fernet) y nunca vuelve a
              mostrarse. Para rotar, repetí este flujo.
            </span>
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(onSubmit)}
            className="flex flex-col gap-4"
            noValidate
          >
            <FormField
              control={form.control}
              name="store_url"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>URL de la tienda</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      type="url"
                      inputMode="url"
                      autoComplete="off"
                      placeholder="https://shop.example.com"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="consumer_key"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Consumer Key</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      type="password"
                      autoComplete="off"
                      className="font-mono"
                      placeholder="ck_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="consumer_secret"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Consumer Secret</FormLabel>
                  <FormControl>
                    <Input
                      {...field}
                      type="password"
                      autoComplete="off"
                      className="font-mono"
                      placeholder="cs_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
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
                {submitting ? "Guardando…" : "Conectar"}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
