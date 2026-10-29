"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Switch } from "@nexus/ui";

import type { BetaChannel, PartnerBetaChannelsOut } from "@/lib/backend";

import { setPartnerBetaChannelsAction } from "./actions";

const INFO: Record<BetaChannel, { name: string; description: string }> = {
  instagram: {
    name: "Instagram",
    description:
      "Mensajes directos y comentarios de la cuenta profesional del cliente.",
  },
  messenger: {
    name: "Messenger",
    description: "Mensajes a la Página de Facebook del cliente.",
  },
};

/**
 * Spec 049 — Instagram and Messenger before Meta approves them for every
 * partner. A partner without the switch does not see the channel at all in
 * its console (§V); this is where Auphere turns it on for the review partner
 * and for internal tests.
 */
export function BetaChannelsForm({
  partnerId,
  beta,
}: {
  partnerId: string;
  beta: PartnerBetaChannelsOut;
}) {
  const [on, setOn] = useState<BetaChannel[]>(beta.channels);
  const [pending, start] = useTransition();

  function toggle(ch: BetaChannel, value: boolean) {
    const next = beta.catalog.filter((c) =>
      c === ch ? value : on.includes(c),
    );
    const previous = on;
    setOn(next);
    start(async () => {
      const r = await setPartnerBetaChannelsAction(partnerId, next);
      if (!r.ok) {
        setOn(previous);
        toast.error("No se pudo guardar", { description: r.error });
        return;
      }
      setOn(r.data.channels);
      toast.success(
        value
          ? `${INFO[ch].name} encendido para este partner`
          : `${INFO[ch].name} apagado para este partner`,
      );
    });
  }

  if (beta.general_availability) {
    return (
      <p className="text-sm text-muted-foreground">
        Meta ya aprobó Instagram y Messenger: todos los partners los tienen.
      </p>
    );
  }

  return (
    <ul className="flex flex-col gap-3">
      {beta.catalog.map((ch) => (
        <li
          key={ch}
          className="flex items-start justify-between gap-4 rounded-md bg-card p-4 ring-1 ring-foreground/10"
        >
          <div className="flex flex-col gap-1">
            <label htmlFor={`beta-${ch}`} className="text-sm font-medium">
              {INFO[ch].name}{" "}
              <span className="text-xs font-normal text-muted-foreground">
                · beta
              </span>
            </label>
            <p className="text-sm text-pretty text-muted-foreground">
              {INFO[ch].description}
            </p>
          </div>
          <Switch
            id={`beta-${ch}`}
            checked={on.includes(ch)}
            disabled={pending}
            onCheckedChange={(v) => toggle(ch, v)}
          />
        </li>
      ))}
    </ul>
  );
}
