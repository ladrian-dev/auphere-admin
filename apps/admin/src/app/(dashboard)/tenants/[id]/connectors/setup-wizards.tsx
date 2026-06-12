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

import {
  agendaProSetPublicUrlAction,
  connectWooCommerceSetupAction,
} from "./setup-actions";

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
