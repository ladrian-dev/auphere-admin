"use client";

/**
 * What each of a tenant's WhatsApp numbers is for.
 *
 * Two independent settings per number, both stored in `channels.config`:
 *
 * - **Rol** — which line business-initiated sends leave from (broadcasts,
 *   cobranza reminders, the template API). With two active numbers and no
 *   `notifications` role assigned, the backend REFUSES to send rather than
 *   guessing — so this control is what unblocks a multi-number client, and
 *   the warning below says so before the operator finds out from a failure.
 * - **Agente** — whether inbound on this number gets answered. Silencing a
 *   line still stores everything the customer writes; it just stops replying
 *   and stops sending read receipts.
 *
 * Only WhatsApp channels are listed: the roles govern WhatsApp sends, and
 * showing the qa_playground / web_widget rows here would imply they can be
 * picked as a sender, which they cannot.
 */

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { StatusDot } from "@/components/brand/status-dot";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { ChannelOut } from "@/lib/backend";
import {
  channelAgentEnabled,
  channelRole,
  type ChannelRole,
} from "@/lib/channels";

import { updateChannelRoleAction } from "./actions";

const UNASSIGNED = "__unassigned__";

const ROLE_LABEL: Record<ChannelRole, string> = {
  agent: "Línea del agente",
  notifications: "Línea de notificaciones",
};

const STATUS_TONE: Record<
  ChannelOut["status"],
  "positive" | "warning" | "danger" | "muted"
> = {
  active: "positive",
  degraded: "warning",
  paused: "muted",
  disconnected: "muted",
};

function phoneOf(channel: ChannelOut): string {
  // A retired channel keeps its number behind a `disconnected:<id>:` prefix
  // so the global UNIQUE on (type, provider_identifier) stays free for a
  // reconnect. Show the number, not the bookkeeping.
  const raw = channel.provider_identifier;
  const marker = raw.lastIndexOf(":");
  return raw.startsWith("disconnected:") && marker > 0
    ? raw.slice(marker + 1)
    : raw;
}

export function WhatsAppNumbers({
  tenantId,
  channels,
}: {
  tenantId: string;
  channels: ChannelOut[];
}) {
  const [showRetired, setShowRetired] = useState(false);
  const whatsapp = channels.filter((c) => c.type === "whatsapp");
  const active = whatsapp.filter((c) => c.status !== "disconnected");
  const retired = whatsapp.filter((c) => c.status === "disconnected");
  // Sole number: the backend ignores roles entirely and uses it for
  // everything. Saying "sin asignar" there would be technically true and
  // practically misleading.
  const soleNumber = active.length === 1;
  // The refusal condition, mirrored from the backend resolver: more than one
  // live number and none of them claiming the notifications role.
  const sendsBlocked =
    active.length > 1 &&
    !active.some((c) => channelRole(c) === "notifications");

  if (whatsapp.length === 0) return null;

  return (
    <section className="flex flex-col gap-3">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Números de WhatsApp</CardTitle>
          <CardDescription>
            {active.length > 1
              ? "Asigná cuál manda las notificaciones y cuál atiende el agente."
              : "Con un solo número activo se usa ese para todo: notificaciones y agente."}
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-3">
          {sendsBlocked ? (
            <div
              role="alert"
              className="rounded-md border border-[color:var(--color-status-warning)]/40 bg-[color:var(--color-status-warning)]/8 px-3 py-2 text-sm"
            >
              Ningún número está marcado como línea de notificaciones. Hasta que
              asignes uno, los recordatorios y los envíos por plantilla se van a
              rechazar en vez de salir por el número equivocado.
            </div>
          ) : null}
          {active.map((channel) => (
            <NumberRow
              key={channel.id}
              tenantId={tenantId}
              channel={channel}
              soleNumber={soleNumber}
            />
          ))}
          {retired.length > 0 ? (
            <div className="flex flex-col gap-3">
              <button
                type="button"
                onClick={() => setShowRetired((v) => !v)}
                className="self-start text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
                aria-expanded={showRetired}
              >
                {showRetired
                  ? "Ocultar números retirados"
                  : `Mostrar ${retired.length} número${retired.length > 1 ? "s" : ""} retirado${retired.length > 1 ? "s" : ""}`}
              </button>
              {showRetired
                ? retired.map((channel) => (
                    <NumberRow
                      key={channel.id}
                      tenantId={tenantId}
                      channel={channel}
                      soleNumber={false}
                    />
                  ))
                : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}

function NumberRow({
  tenantId,
  channel,
  soleNumber,
}: {
  tenantId: string;
  channel: ChannelOut;
  soleNumber: boolean;
}) {
  const [pending, start] = useTransition();
  const [confirmSilence, setConfirmSilence] = useState(false);
  const role = channelRole(channel);
  const agentOn = channelAgentEnabled(channel);
  const retired = channel.status === "disconnected";
  // What "no role" actually means depends on how many numbers are live. With
  // one, the backend uses it for everything — so that is what we say. With
  // two, an unassigned number is a real gap the operator has to close.
  const unassignedLabel = soleNumber
    ? "Notificaciones y agente"
    : "Sin asignar";
  const verifiedName =
    typeof channel.config?.verified_name === "string"
      ? channel.config.verified_name
      : null;

  function apply(
    body: { role?: ChannelRole | null; agent_enabled?: boolean },
    successMessage: string,
  ) {
    start(async () => {
      const r = await updateChannelRoleAction(tenantId, channel.id, body);
      if (r.ok) toast.success(successMessage);
      else toast.error(r.error);
    });
  }

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-md border px-3 py-2.5">
      <StatusDot tone={STATUS_TONE[channel.status]} className="shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-sm">{phoneOf(channel)}</p>
        <p className="truncate text-xs text-muted-foreground">
          {verifiedName ?? "Sin nombre verificado"}
          {retired ? " · retirado" : null}
        </p>
      </div>

      {retired ? (
        <Badge variant="outline" className="text-xs">
          Desconectado
        </Badge>
      ) : (
        <>
          <Select
            value={role ?? UNASSIGNED}
            disabled={pending}
            onValueChange={(v) =>
              apply(
                { role: v === UNASSIGNED ? null : (v as ChannelRole) },
                v === UNASSIGNED
                  ? "Rol quitado."
                  : `Marcado como ${ROLE_LABEL[v as ChannelRole].toLowerCase()}.`,
              )
            }
          >
            <SelectTrigger
              className="h-8 w-[230px] text-xs"
              aria-label={`Rol de ${phoneOf(channel)}`}
            >
              {/* base-ui renders the raw value unless it is given a formatter,
                  which would surface the `__unassigned__` sentinel verbatim. */}
              <SelectValue>
                {(value: string | null) =>
                  value && value !== UNASSIGNED
                    ? ROLE_LABEL[value as ChannelRole]
                    : unassignedLabel
                }
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={UNASSIGNED} className="text-xs">
                {unassignedLabel}
              </SelectItem>
              <SelectItem value="notifications" className="text-xs">
                {ROLE_LABEL.notifications}
              </SelectItem>
              <SelectItem value="agent" className="text-xs">
                {ROLE_LABEL.agent}
              </SelectItem>
            </SelectContent>
          </Select>

          <Button
            variant={agentOn ? "outline" : "secondary"}
            size="sm"
            disabled={pending}
            onClick={() =>
              agentOn
                ? setConfirmSilence(true)
                : apply(
                    { agent_enabled: true },
                    "El agente vuelve a responder en este número.",
                  )
            }
          >
            {agentOn ? "Silenciar agente" : "Activar agente"}
          </Button>
        </>
      )}

      <Dialog open={confirmSilence} onOpenChange={setConfirmSilence}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Silenciar el agente en {phoneOf(channel)}</DialogTitle>
            <DialogDescription>
              A partir de ahora nadie contesta en este número: los mensajes que
              lleguen se guardan y los vas a ver en el panel, pero el agente no
              responde y no se manda el doble check azul. Los envíos salientes
              (plantillas, recordatorios) siguen funcionando igual.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="ghost"
              onClick={() => setConfirmSilence(false)}
              disabled={pending}
            >
              Cancelar
            </Button>
            <Button
              disabled={pending}
              onClick={() => {
                setConfirmSilence(false);
                apply(
                  { agent_enabled: false },
                  "Número dejado como sólo notificaciones.",
                );
              }}
            >
              Silenciar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
