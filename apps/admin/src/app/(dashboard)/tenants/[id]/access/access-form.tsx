"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import type { ClientAccessOut, ClientModule } from "@/lib/backend";

import { setAccessAction } from "./actions";
import { INELIGIBLE, MODULE_LABELS } from "./messages";

const ORDER: ClientModule[] = ["panel", "inbox", "usage"];

/**
 * Spec 030 (R1.1–R1.3): switch the client console on, and choose its modules.
 * Same shape as the runtime capabilities card: rows with a checkbox and one
 * «Guardar» that only sends what changed.
 */
export function AccessForm({ tenantId, access }: { tenantId: string; access: ClientAccessOut }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [enabled, setEnabled] = useState(access.enabled);
  const [modules, setModules] = useState<Set<ClientModule>>(new Set(access.modules));

  if (!access.eligible) {
    return (
      <p className="text-sm text-muted-foreground" role="status">
        {access.ineligible_reason ? INELIGIBLE[access.ineligible_reason] : null}
      </p>
    );
  }

  const ordered = ORDER.filter((m) => modules.has(m));
  const dirty = enabled !== access.enabled || ordered.join(",") !== access.modules.join(",");
  const missingModules = enabled && ordered.length === 0;
  const inboxLocked = !access.whatsapp_connected && !access.modules.includes("inbox");

  function toggle(m: ClientModule, on: boolean) {
    setModules((prev) => {
      const next = new Set(prev);
      if (on) next.add(m);
      else next.delete(m);
      return next;
    });
  }

  function onSave() {
    startTransition(async () => {
      const res = await setAccessAction(tenantId, { enabled, modules: ordered });
      if (!res.ok) {
        toast.error("No se pudo guardar el acceso", { description: res.error });
        return;
      }
      toast.success(res.data.enabled ? "Acceso guardado" : "Acceso apagado: se cerraron las sesiones de sus personas");
      router.refresh();
    });
  }

  return (
    <div className="grid gap-4">
      <Row
        id="access-enabled"
        label="Consola lite encendida"
        description="Las personas de este cliente entran con su correo y ven solo los módulos de abajo."
        checked={enabled}
        onChange={setEnabled}
      />
      <fieldset className="grid gap-3 border-l border-border pl-4" aria-label="Módulos">
        {ORDER.map((m) => (
          <Row
            key={m}
            id={`module-${m}`}
            label={MODULE_LABELS[m].label}
            description={
              m === "inbox" && inboxLocked
                ? "La Bandeja de entrada necesita un WhatsApp conectado."
                : MODULE_LABELS[m].description
            }
            checked={modules.has(m)}
            onChange={(on) => toggle(m, on)}
            disabled={m === "inbox" && inboxLocked}
          />
        ))}
      </fieldset>
      {missingModules ? (
        <p className="text-sm text-destructive" role="alert">
          Elige al menos un módulo para encender el acceso.
        </p>
      ) : null}
      <div className="flex justify-end">
        <Button type="button" onClick={onSave} disabled={!dirty || missingModules || pending}>
          {pending ? "Guardando…" : "Guardar acceso"}
        </Button>
      </div>
    </div>
  );
}

function Row({
  id,
  label,
  description,
  checked,
  onChange,
  disabled,
}: {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}) {
  return (
    <div className="flex items-start gap-3">
      <Checkbox
        id={id}
        checked={checked}
        onCheckedChange={(v) => onChange(v === true)}
        disabled={disabled}
        aria-describedby={`${id}-desc`}
        className="mt-0.5"
      />
      <div className="min-w-0 flex-1">
        <Label htmlFor={id} className={"text-sm font-medium " + (disabled ? "text-muted-foreground" : "")}>
          {label}
        </Label>
        <p id={`${id}-desc`} className="mt-0.5 text-xs text-muted-foreground text-pretty">
          {description}
        </p>
      </div>
    </div>
  );
}
