"use client";

/**
 * Spec 005 · el puente entre la pantalla de planes y el servidor.
 *
 * Existe para que `MembershipPanel` siga siendo una función de sus props —lo
 * que hace que sus tests no necesiten montar Next— y para que los errores del
 * proveedor se traduzcan **aquí**: el mensaje crudo de una API externa es
 * contenido externo y no se pone delante de una persona (§III).
 */

import { useState } from "react";

import { toast } from "sonner";

import { openPortalAction, startCheckoutAction } from "@/app/(console)/billing/actions";
import { useT } from "@/i18n/client";
import type { MembershipOut } from "@/lib/backend/membership";

import { MembershipPanel } from "./membership-panel";

/** Códigos del contrato → frases nuestras. Cualquier otro cae en el genérico. */

export function MembershipSection({ membership }: { membership: MembershipOut }) {
  const t = useT();
  const [pending, setPending] = useState(false);

  function explain(code: string | null | undefined, info: Record<string, unknown> | undefined): string {
    if (code === "tier_below_usage") {
      const over = Object.entries((info?.over ?? {}) as Record<string, number>)
        .map(
          ([kind, n]) =>
            `${n} ${kind === "teammates" ? t("membership.teammates") : t("membership.members")}`,
        )
        .join(", ");
      return t("membership.error.belowUsage", { over: over.toLowerCase() });
    }
    if (code === "subscription_pending") return t("membership.error.pending");
    // Cualquier otro caso, incluido un fallo del proveedor: una frase nuestra.
    // El mensaje crudo del backend se queda en el log.
    return t("membership.error.unavailable");
  }

  async function choose(code: string) {
    if (pending) return;
    setPending(true);
    try {
      const res = await startCheckoutAction({ tier_code: code });
      if (!res.ok) {
        toast.error(explain(res.code, res.info));
        return;
      }
      // Una subida se aplica sin página de pago; una alta sí la abre.
      if (res.data.url) window.location.assign(res.data.url);
    } finally {
      setPending(false);
    }
  }

  async function fixCard() {
    const res = await openPortalAction();
    if (!res.ok) {
      toast.error(t("membership.error.unavailable"));
      return;
    }
    window.location.assign(res.data.url);
  }

  return <MembershipPanel membership={membership} onChoose={choose} onFixCard={fixCard} />;
}
