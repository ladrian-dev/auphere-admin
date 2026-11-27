"use client";

/**
 * Meta WhatsApp Embedded Signup wizard.
 *
 * Two cards side by side — Cloud API (recommended) and Coexistence —
 * matching the visual pattern Meta uses in the Cloud Console "Create
 * Channel" modal. Clicking "Empezar" lazy-loads the Facebook SDK and
 * triggers ``FB.login`` with the matching configuration ID. On success
 * the server action runs the post-signup orchestrator and the dialog
 * closes.
 *
 * Spec 047 (30.4, T101) and 049 (7.2, 2026-11-26), as in the console:
 * while Meta's window is open the wait can be cancelled with «Cancelar»,
 * Escape or the ×; a click outside does not. Each attempt carries its
 * number and its ``AbortController``, so whatever Meta returns to a
 * cancelled one never reaches the backend. Once the backend is connecting
 * the number, it cannot be cancelled.
 */

import { CheckCircle2, Smartphone } from "lucide-react";
import { useEffect, useRef, useState, useTransition } from "react";
import { toast } from "sonner";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@nexus/ui";
import {
  META_CONFIG_ID_CLOUD_API,
  META_CONFIG_ID_COEXISTENCE,
  loginWithMeta,
} from "@/lib/meta-fb-sdk";

import { connectMetaWhatsAppSetupAction } from "./setup-actions";

type SignupMode = "cloud_api" | "coexistence";

/** Waiting for Meta's window (cancellable) or the backend connecting the number (not). */
type Busy = { mode: SignupMode; phase: "meta" | "saving" };

interface Props {
  tenantId: string;
  alreadyConnected: boolean;
  /** Spec 035: the channel wizard moves on to «Asignar agente». */
  onConnected?: () => void;
}

export function MetaWhatsAppSetupDialog({ tenantId, alreadyConnected, onConnected }: Props) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<Busy | null>(null);
  const [, startTransition] = useTransition();
  const attempt = useRef(0);
  const abort = useRef<AbortController | null>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const statusRef = useRef<HTMLDivElement>(null);
  useEffect(() => () => abort.current?.abort(), []);
  // «Empezar» se desactiva con el foco dentro: el foco pasa a «Cancelar»
  // mientras se espera a Meta, y a la línea de estado durante el canje, para
  // que Escape y el teclado sigan teniendo dónde estar.
  const phase = busy?.phase ?? null;
  useEffect(() => {
    if (phase === "meta") cancelRef.current?.focus();
    else if (phase === "saving") statusRef.current?.focus();
  }, [phase]);

  function cancelWait() {
    attempt.current += 1;
    abort.current?.abort();
    abort.current = null;
    setBusy(null);
  }

  async function runSignup(mode: SignupMode) {
    const configId =
      mode === "cloud_api"
        ? META_CONFIG_ID_CLOUD_API
        : META_CONFIG_ID_COEXISTENCE;
    if (!configId) {
      toast.error("Configuración faltante", {
        description: `Falta NEXT_PUBLIC_META_CONFIG_ID_${
          mode === "cloud_api" ? "WA_CLOUD_API" : "WA_COEXISTENCE"
        } en Vercel.`,
      });
      return;
    }
    abort.current?.abort();
    const mine = ++attempt.current;
    const controller = new AbortController();
    abort.current = controller;
    setBusy({ mode, phase: "meta" });
    try {
      let envelope;
      try {
        envelope = await loginWithMeta(configId, mode, undefined, controller.signal);
      } catch (err) {
        if (attempt.current !== mine) return;
        toast.error("No se completó el flow de Meta", {
          description: err instanceof Error ? err.message : String(err),
        });
        return;
      }
      // A cancelled attempt never reaches the backend, even if Meta answers.
      if (attempt.current !== mine || controller.signal.aborted) return;
      setBusy({ mode, phase: "saving" });
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
      onConnected?.();
    } finally {
      if (attempt.current === mine) {
        abort.current = null;
        setBusy(null);
      }
    }
  }

  return (
    <Dialog
      open={open}
      disablePointerDismissal={busy !== null}
      onOpenChange={(next) => {
        if (busy?.phase === "saving") return;
        if (!next && busy) cancelWait();
        setOpen(next);
      }}
    >
      <DialogTrigger
        render={
          <Button size="sm" variant={alreadyConnected ? "outline" : "default"}>
            {/* Not "Reconectar": the flow adds whatever number the client
                picks in the Meta popup, and a tenant can hold several. Only
                choosing the same number again replaces it. */}
            {alreadyConnected ? "Conectar otro número" : "Conectar"}
          </Button>
        }
      />
      <DialogContent className="max-w-3xl md:max-w-4xl" showCloseButton={busy?.phase !== "saving"}>
        <DialogHeader>
          <DialogTitle>Conectar canal de WhatsApp</DialogTitle>
          <DialogDescription>
            El cliente autoriza desde su Facebook Business en un popup. Los
            tokens nunca pasan por el navegador del operador.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
          <OptionCard
            icon={<CheckCircle2 className="h-5 w-5" strokeWidth={1.5} />}
            title="Cloud API"
            subtitle="Operación 100% por API"
            description="Auphere registra el número bajo nuestra Meta App. La app móvil del cliente queda desactivada. Recomendado para negocios que migran al agente IA por completo."
            cta="Empezar"
            highlighted
            badge="Recomendado"
            busy={busy?.mode === "cloud_api"}
            disabled={busy !== null}
            onSelect={() => runSignup("cloud_api")}
          />
          <OptionCard
            icon={<Smartphone className="h-5 w-5" strokeWidth={1.5} />}
            title="Coexistence"
            subtitle="Convive con la app móvil"
            description="El cliente sigue respondiendo desde la app WhatsApp Business del móvil en paralelo al agente. Menor throughput; útil para transiciones graduales."
            cta="Empezar"
            busy={busy?.mode === "coexistence"}
            disabled={busy !== null}
            onSelect={() => runSignup("coexistence")}
          />
        </div>

        {busy ? (
          <div
            ref={statusRef}
            tabIndex={-1}
            className="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-md bg-muted px-4 py-3 outline-none"
          >
            <p role="status" className="min-w-0 text-sm text-pretty">
              {busy.phase === "meta"
                ? "Continúa en la ventana de Meta. Si la cerraste o no la encuentras, cancela y vuelve a empezar."
                : "Conectando el número…"}
            </p>
            {busy.phase === "meta" ? (
              <Button ref={cancelRef} size="sm" variant="outline" onClick={cancelWait}>
                Cancelar
              </Button>
            ) : null}
          </div>
        ) : null}

        <p className="pt-1 text-xs text-muted-foreground">
          El cliente debe ser admin de su Meta Business Account y tener acceso
          a la WABA. Si no la creó todavía, la propia ventana de Meta lo guía
          para crearla.
        </p>
      </DialogContent>
    </Dialog>
  );
}

// ── card primitive ─────────────────────────────────────────────────────────

interface OptionCardProps {
  icon: React.ReactNode;
  title: string;
  subtitle: string;
  description: string;
  cta: string;
  badge?: string;
  highlighted?: boolean;
  busy: boolean;
  disabled: boolean;
  onSelect: () => void;
}

function OptionCard({
  icon,
  title,
  subtitle,
  description,
  cta,
  badge,
  highlighted,
  busy,
  disabled,
  onSelect,
}: OptionCardProps) {
  return (
    <div
      className={[
        "relative flex flex-col gap-4 rounded-md border p-5 transition",
        highlighted
          ? "border-primary/40 bg-primary/[0.02]"
          : "border-border bg-card hover:border-border/80",
      ].join(" ")}
    >
      {badge ? (
        <span className="absolute right-4 top-4 rounded-full bg-primary/10 px-2 py-1 text-[10px] font-medium uppercase tracking-wider text-primary">
          {badge}
        </span>
      ) : null}

      <div className="flex items-center gap-2 text-muted-foreground">
        {icon}
        <span className="text-[11px] font-mono uppercase tracking-wider">
          {subtitle}
        </span>
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-xl font-semibold leading-tight tracking-tight">
          {title}
        </h3>
        <p className="text-sm text-muted-foreground leading-relaxed">
          {description}
        </p>
      </div>

      <Button
        size="sm"
        className="w-full mt-auto"
        variant={highlighted ? "default" : "outline"}
        onClick={onSelect}
        disabled={disabled}
      >
        {busy ? "Conectando…" : cta}
      </Button>
    </div>
  );
}
