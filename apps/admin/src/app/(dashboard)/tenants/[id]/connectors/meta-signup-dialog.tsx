"use client";

/**
 * Meta WhatsApp Embedded Signup wizard.
 *
 * UX shape (matches the inspiration screenshot Luis shared 2026-05-21):
 *
 * 1. Operator opens the dialog from the connector catalogue card.
 * 2. Two side-by-side options:
 *      - WhatsApp Business API       (Cloud-only flow)
 *      - WhatsApp Business APP Coex. (preserves the tenant's mobile app)
 * 3. Click on "Get started" lazy-loads the Facebook SDK and triggers
 *    ``FB.login`` with the matching configuration ID.
 * 4. The customer authenticates in the popup; on success we resolve a
 *    ``MetaSignupEnvelope`` (code + waba_id + phone_number_id + business_id)
 *    and hand it to ``connectMetaWhatsAppSetupAction`` which runs the
 *    server-side post-signup orchestrator.
 * 5. On success the dialog closes; the connectors page revalidates and
 *    the new channel appears under "Conectados".
 */

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { loginWithMeta } from "@/lib/meta-fb-sdk";

import { connectMetaWhatsAppSetupAction } from "./setup-actions";

type SignupMode = "cloud_api" | "coexistence";

interface Props {
  tenantId: string;
  alreadyConnected: boolean;
}

export function MetaWhatsAppSetupDialog({ tenantId, alreadyConnected }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<SignupMode | null>(null);
  const [, startTransition] = useTransition();

  async function runSignup(mode: SignupMode) {
    setBusy(mode);
    try {
      const configId =
        mode === "cloud_api"
          ? process.env.NEXT_PUBLIC_META_CONFIG_ID_WA_CLOUD_API
          : process.env.NEXT_PUBLIC_META_CONFIG_ID_WA_COEXISTENCE;
      if (!configId) {
        toast.error("Configuración faltante", {
          description: `Falta NEXT_PUBLIC_META_CONFIG_ID_${
            mode === "cloud_api" ? "WA_CLOUD_API" : "WA_COEXISTENCE"
          } en Vercel.`,
        });
        return;
      }
      let envelope;
      try {
        envelope = await loginWithMeta(configId);
      } catch (err) {
        toast.error("No se completó el flow de Meta", {
          description: err instanceof Error ? err.message : String(err),
        });
        return;
      }
      const result = await connectMetaWhatsAppSetupAction(tenantId, {
        code: envelope.code,
        waba_id: envelope.waba_id,
        phone_number_id: envelope.phone_number_id,
        business_id: envelope.business_id,
        mode,
      });
      if (!result.ok) {
        toast.error("El backend rechazó el signup", {
          description: result.error,
        });
        return;
      }
      toast.success("WhatsApp conectado vía Meta", {
        description: `${result.data.display_phone_number} — el canal ya recibe webhooks.`,
      });
      startTransition(() => setOpen(false));
    } finally {
      setBusy(null);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (busy) return; // don't allow closing mid-flow
        setOpen(next);
      }}
    >
      <DialogTrigger
        render={
          <Button size="sm" variant={alreadyConnected ? "outline" : "default"}>
            {alreadyConnected ? "Reconectar" : "Conectar"}
          </Button>
        }
      />
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Conectar canal de WhatsApp</DialogTitle>
          <DialogDescription>
            Elegí cómo se va a onboardear el número. El cliente autoriza desde
            su cuenta de Facebook Business en un popup; los tokens nunca pasan
            por el navegador del operador.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
          <OptionCard
            title="WhatsApp Business API"
            subtitle="Cloud-only"
            description="Para negocios medianos y grandes que quieren operar el canal 100% por API. Auphere registra el número bajo nuestra Meta App; la app móvil del cliente queda desactivada."
            badge="Recomendado"
            busy={busy === "cloud_api"}
            disabled={busy !== null}
            onSelect={() => runSignup("cloud_api")}
          />
          <OptionCard
            title="WhatsApp Coexistence"
            subtitle="Mantiene la app móvil"
            description="Para tenants que quieren seguir respondiendo desde la app WhatsApp Business del móvil en paralelo al agente IA. Más limitado en throughput pero útil en transición."
            badge="Compatible"
            busy={busy === "coexistence"}
            disabled={busy !== null}
            onSelect={() => runSignup("coexistence")}
          />
        </div>

        <p className="pt-2 text-xs text-muted-foreground">
          El cliente debe ser admin de su Meta Business Account y tener acceso
          a la WABA que quiere conectar. Si todavía no creó la WABA, la propia
          ventana de Meta lo guía para crearla durante el flow.
        </p>
      </DialogContent>
    </Dialog>
  );
}

// ── card primitive ─────────────────────────────────────────────────────────

interface OptionCardProps {
  title: string;
  subtitle: string;
  description: string;
  badge: string;
  busy: boolean;
  disabled: boolean;
  onSelect: () => void;
}

function OptionCard({
  title,
  subtitle,
  description,
  badge,
  busy,
  disabled,
  onSelect,
}: OptionCardProps) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-border bg-card p-5 transition hover:border-primary/40">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
            {subtitle}
          </span>
          <h3 className="text-lg font-semibold leading-tight">{title}</h3>
        </div>
        <span className="rounded-full border border-border px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
          {badge}
        </span>
      </div>
      <p className="text-sm text-muted-foreground leading-relaxed">
        {description}
      </p>
      <div className="mt-auto pt-2">
        <Button
          size="sm"
          className="w-full"
          onClick={onSelect}
          disabled={disabled}
        >
          {busy ? "Conectando…" : "Empezar"}
        </Button>
      </div>
    </div>
  );
}
