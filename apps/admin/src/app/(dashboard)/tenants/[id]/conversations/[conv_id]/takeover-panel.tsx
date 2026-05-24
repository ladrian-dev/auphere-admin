"use client";

/**
 * Bloque C — takeover panel on the conversation detail view.
 *
 * Combines three things the operator needs in one place:
 *
 * 1. An optional reason / notes when pausing the agent. The notes
 *    survive into ``conversations.takeover_context`` and the dispatcher
 *    uses them on the first turn after resume to brief the LLM.
 * 2. A composer for sending free-form text as the operator while the
 *    agent is paused. The backend rejects sends with 409 when the
 *    agent is still active.
 * 3. A visible banner showing the active takeover (started_at, reason,
 *    notes) so any operator landing on the conversation knows the
 *    context immediately.
 *
 * Concurrency: every PATCH carries the ``agent_active_version`` we last
 * saw. If a different operator beat us to it the action returns
 * ``conflict: true`` and we toast a "recargá y reintentá" message.
 */

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import type { TakeoverContext } from "@/lib/backend";

import {
  operatorSendMessageAction,
  toggleConversationAgentAction,
} from "../actions";

import { useConversationStream } from "./use-conversation-stream";

type Props = {
  tenantId: string;
  conversationId: string;
  agentActive: boolean;
  agentActiveVersion: number;
  takeoverContext: TakeoverContext | null;
};

export function TakeoverPanel({
  tenantId,
  conversationId,
  agentActive,
  agentActiveVersion,
  takeoverContext,
}: Props) {
  useConversationStream(tenantId, conversationId);
  const router = useRouter();
  const [pending, start] = useTransition();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [composerText, setComposerText] = useState("");

  function performToggle(next: boolean, opts?: { reason?: string; notes?: string }) {
    start(async () => {
      const res = await toggleConversationAgentAction(
        tenantId,
        conversationId,
        next,
        {
          reason: opts?.reason ?? null,
          notes: opts?.notes ?? null,
          expectedVersion: agentActiveVersion,
        },
      );
      if (!res.ok) {
        const conflict = "conflict" in res && res.conflict;
        toast.error(
          conflict
            ? "Conflicto de versión"
            : `No se pudo cambiar el agente`,
          { description: res.error },
        );
        if (conflict) router.refresh();
        return;
      }
      setDialogOpen(false);
      setReason("");
      setNotes("");
      toast.success(
        next ? "Agente reactivado" : "Tomaste control de la conversación",
        {
          description: next
            ? "El próximo mensaje del cliente disparará al agente con un briefing de tu intervención."
            : "El agente queda en silencio en este thread hasta que lo reactives.",
        },
      );
    });
  }

  function onPauseClick() {
    setDialogOpen(true);
  }

  function onResumeClick() {
    performToggle(true);
  }

  function onSubmitDialog(e: React.FormEvent) {
    e.preventDefault();
    performToggle(false, {
      reason: reason.trim() || undefined,
      notes: notes.trim() || undefined,
    });
  }

  function onSendOperatorMessage(e: React.FormEvent) {
    e.preventDefault();
    const content = composerText.trim();
    if (!content || pending) return;
    start(async () => {
      const res = await operatorSendMessageAction(
        tenantId,
        conversationId,
        content,
      );
      if (!res.ok) {
        toast.error("No se pudo enviar el mensaje", { description: res.error });
        return;
      }
      setComposerText("");
      toast.success("Mensaje enviado como operador");
    });
  }

  return (
    <div className="grid gap-4">
      {/* Toggle button — visible always */}
      <div className="flex items-center justify-end">
        <Button
          variant={agentActive ? "outline" : "default"}
          size="sm"
          disabled={pending}
          onClick={agentActive ? onPauseClick : onResumeClick}
        >
          {pending
            ? agentActive
              ? "Tomando control…"
              : "Reactivando…"
            : agentActive
              ? "Tomar control"
              : "Reactivar agente"}
        </Button>
      </div>

      {/* Active-takeover banner */}
      {!agentActive && takeoverContext ? (
        <div className="rounded-md border border-amber-300/40 bg-amber-50/40 dark:bg-amber-950/20 px-4 py-3 text-sm grid gap-1">
          <strong>Operador en control de este thread.</strong>
          {takeoverContext.reason ? (
            <div>
              <span className="text-muted-foreground">Razón:</span>{" "}
              {takeoverContext.reason}
            </div>
          ) : null}
          {takeoverContext.notes ? (
            <div>
              <span className="text-muted-foreground">Notas:</span>{" "}
              {takeoverContext.notes}
            </div>
          ) : null}
          {takeoverContext.started_at ? (
            <div className="text-xs text-muted-foreground">
              Pausa iniciada: {takeoverContext.started_at}
            </div>
          ) : null}
        </div>
      ) : null}

      {!agentActive ? (
        <form onSubmit={onSendOperatorMessage} className="grid gap-2">
          <Label htmlFor="operator-composer">Responder como operador</Label>
          <Textarea
            id="operator-composer"
            value={composerText}
            onChange={(e) => setComposerText(e.target.value)}
            placeholder="Escribí tu respuesta al cliente…"
            rows={3}
            maxLength={4096}
            disabled={pending}
          />
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">
              {composerText.length}/4096
            </span>
            <Button
              type="submit"
              size="sm"
              disabled={pending || composerText.trim().length === 0}
            >
              {pending ? "Enviando…" : "Enviar como operador"}
            </Button>
          </div>
        </form>
      ) : null}

      {/* Reason-on-pause dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Tomar control de la conversación</DialogTitle>
            <DialogDescription>
              El agente queda silenciado en este thread hasta que lo reactives.
              Tus notas se le pasan al agente cuando reactives, para que entienda
              qué pasó.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={onSubmitDialog} className="grid gap-3">
            <div className="grid gap-1">
              <Label htmlFor="takeover-reason">Razón (opcional)</Label>
              <Input
                id="takeover-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="ej. queja, escalamiento, error del bot"
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="takeover-notes">Notas para el agente (opcional)</Label>
              <Textarea
                id="takeover-notes"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="ej. el cliente estaba enojado por la demora; le confirmé el envío hoy a las 18hs"
                rows={3}
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setDialogOpen(false)}
                disabled={pending}
              >
                Cancelar
              </Button>
              <Button type="submit" disabled={pending}>
                {pending ? "Tomando control…" : "Tomar control"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
