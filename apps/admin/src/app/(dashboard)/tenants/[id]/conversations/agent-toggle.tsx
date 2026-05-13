"use client";

/**
 * Block M.3 — small toggle that flips a conversation's ``agent_active``
 * flag. Used in two surfaces:
 *
 * - The conversations list (compact, status-only — clicking is the action).
 * - The conversation detail header (labelled button with explicit copy).
 *
 * Both surfaces share the same server action so revalidation paths and
 * audit semantics stay aligned.
 */

import { useTransition } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { toggleConversationAgentAction } from "./actions";

type Variant = "badge" | "button";

export function AgentToggle({
  tenantId,
  conversationId,
  agentActive,
  variant = "badge",
}: {
  tenantId: string;
  conversationId: string;
  agentActive: boolean;
  variant?: Variant;
}) {
  const [pending, start] = useTransition();

  function onClick(e: React.MouseEvent) {
    e.stopPropagation();
    e.preventDefault();
    if (pending) return;
    start(async () => {
      const next = !agentActive;
      const res = await toggleConversationAgentAction(
        tenantId,
        conversationId,
        next,
      );
      if (!res.ok) {
        toast.error(`No se pudo cambiar el agente: ${res.error}`);
        return;
      }
      if (next) {
        toast.success("Agente reactivado", {
          description:
            "El agente responderá el próximo mensaje. No hay auto-reply del backlog.",
        });
      } else {
        toast.success("Tomaste control de la conversación", {
          description:
            "El agente queda silenciado en este thread hasta que lo reactivas.",
          action: {
            label: "Reactivar",
            onClick: () => {
              start(async () => {
                await toggleConversationAgentAction(
                  tenantId,
                  conversationId,
                  true,
                );
              });
            },
          },
        });
      }
    });
  }

  if (variant === "button") {
    return (
      <Button
        variant={agentActive ? "outline" : "default"}
        size="sm"
        disabled={pending}
        onClick={onClick}
      >
        {pending
          ? agentActive
            ? "Tomando control…"
            : "Reactivando…"
          : agentActive
            ? "Tomar control"
            : "Reactivar agente"}
      </Button>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={pending}
      className="outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-full"
      aria-label={
        agentActive
          ? "Agente activo — tomar control"
          : "Operador en control — reactivar agente"
      }
    >
      <Badge
        variant={agentActive ? "default" : "secondary"}
        className={
          "text-[10px] uppercase tracking-wider cursor-pointer " +
          (pending ? "opacity-60" : "")
        }
      >
        {agentActive ? "Agente ON" : "Operador"}
      </Badge>
    </button>
  );
}
