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

import { Button, StatusDot } from "@nexus/ui";

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
            "El agente responderá el próximo mensaje. Lo que llegó mientras tanto no se contesta solo.",
        });
      } else {
        toast.success("Tomaste control de la conversación", {
          description:
            "El agente no responde en esta conversación hasta que se la devuelvas.",
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

  // Spec 036: the state in words and the action as a real button (H5) — a
  // badge that silenced the agent on click looked like a label.
  return (
    <span className="inline-flex items-center gap-2">
      <span className="inline-flex items-center gap-2 text-sm">
        <StatusDot tone={agentActive ? "positive" : "warning"} />
        {agentActive ? "El agente" : "Una persona"}
      </span>
      <Button variant="ghost" size="sm" onClick={onClick} disabled={pending}>
        {pending ? "…" : agentActive ? "Tomar control" : "Devolver"}
      </Button>
    </span>
  );
}
