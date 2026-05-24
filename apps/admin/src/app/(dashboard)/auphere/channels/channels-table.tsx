"use client";

import Link from "next/link";
import { useTransition } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { AuphereOwnerChannelOut } from "@/lib/backend";
import { relativeTime } from "@/lib/format";

import type {
  deactivateChannelAction,
  updateChannelAction,
} from "./actions";

type UpdateAction = typeof updateChannelAction;
type DeactivateAction = typeof deactivateChannelAction;

export function ChannelsTable({
  channels,
  showingInactive,
  updateAction,
  deactivateAction,
}: {
  channels: AuphereOwnerChannelOut[];
  showingInactive: boolean;
  updateAction: UpdateAction;
  deactivateAction: DeactivateAction;
}) {
  return (
    <div className="grid gap-3">
      <div className="flex items-center justify-end gap-2 text-xs">
        <Link
          href={
            showingInactive
              ? "/auphere/channels"
              : "/auphere/channels?include_inactive=true"
          }
          className="text-muted-foreground hover:text-foreground underline-offset-4 hover:underline"
        >
          {showingInactive
            ? "Ocultar inactivos"
            : "Mostrar inactivos"}
        </Link>
      </div>
      {channels.length === 0 ? (
        <div className="rounded-md border border-dashed py-10 text-center text-sm text-muted-foreground">
          {showingInactive
            ? "Sin canales registrados."
            : "Sin canales activos. Agregá uno desde el formulario."}
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Default</TableHead>
              <TableHead>Display</TableHead>
              <TableHead>Teléfono</TableHead>
              <TableHead>Provider</TableHead>
              <TableHead>País</TableHead>
              <TableHead>Secret</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead>Creado</TableHead>
              <TableHead className="text-right">Acción</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {channels.map((c) => (
              <ChannelRow
                key={c.id}
                channel={c}
                updateAction={updateAction}
                deactivateAction={deactivateAction}
              />
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

function ChannelRow({
  channel,
  updateAction,
  deactivateAction,
}: {
  channel: AuphereOwnerChannelOut;
  updateAction: UpdateAction;
  deactivateAction: DeactivateAction;
}) {
  const [pending, startTransition] = useTransition();

  function onPromoteDefault() {
    if (channel.is_default) return;
    startTransition(async () => {
      const r = await updateAction(channel.id, { is_default: true });
      if (!r.ok) {
        toast.error("No se pudo promover", { description: r.error });
        return;
      }
      toast.success("Marcado como default");
    });
  }

  function onClearDefault() {
    if (!channel.is_default) return;
    startTransition(async () => {
      const r = await updateAction(channel.id, { is_default: false });
      if (!r.ok) {
        toast.error("No se pudo desmarcar", { description: r.error });
        return;
      }
      toast.success("Default removido");
    });
  }

  function onReactivate() {
    startTransition(async () => {
      const r = await updateAction(channel.id, { active: true });
      if (!r.ok) {
        toast.error("No se pudo reactivar", { description: r.error });
        return;
      }
      toast.success("Canal reactivado");
    });
  }

  function onRotateSecret() {
    const next = prompt(
      "Nuevo webhook secret (vacío = usar shared del provider):",
      "",
    );
    if (next === null) return;
    startTransition(async () => {
      const r = await updateAction(channel.id, {
        webhook_secret: next,
      });
      if (!r.ok) {
        toast.error("No se pudo rotar el secret", { description: r.error });
        return;
      }
      toast.success(next ? "Secret rotado" : "Secret limpiado (usa shared)");
    });
  }

  function onDeactivate() {
    if (
      !confirm(
        `Desactivar ${channel.display_name} (${channel.phone_e164})?\n\n` +
          "Los OwnerPhoneIndex que apunten a este canal van a caer al " +
          "default del provider en el próximo envío.",
      )
    ) {
      return;
    }
    startTransition(async () => {
      const r = await deactivateAction(channel.id);
      if (!r.ok) {
        toast.error("No se pudo desactivar", { description: r.error });
        return;
      }
      toast.success("Canal desactivado");
    });
  }

  return (
    <TableRow data-testid={`channel-row-${channel.id}`}>
      <TableCell>
        {channel.is_default ? (
          <button
            type="button"
            onClick={onClearDefault}
            disabled={pending}
            className="text-amber-600 hover:text-amber-700"
            aria-label="Default — click para desmarcar"
            title="Default — click para desmarcar"
          >
            ★
          </button>
        ) : (
          <button
            type="button"
            onClick={onPromoteDefault}
            disabled={pending || !channel.active}
            className="text-muted-foreground hover:text-amber-600 disabled:opacity-30"
            aria-label="Marcar como default"
            title="Marcar como default"
          >
            ☆
          </button>
        )}
      </TableCell>
      <TableCell className="font-medium">{channel.display_name}</TableCell>
      <TableCell className="font-mono text-xs">{channel.phone_e164}</TableCell>
      <TableCell className="text-xs">{channel.provider}</TableCell>
      <TableCell className="font-mono text-xs">
        {channel.country_code ?? "—"}
      </TableCell>
      <TableCell>
        <Badge variant={channel.has_webhook_secret ? "default" : "outline"}>
          {channel.has_webhook_secret ? "per-channel" : "shared"}
        </Badge>
      </TableCell>
      <TableCell>
        <Badge variant={channel.active ? "default" : "destructive"}>
          {channel.active ? "Activo" : "Inactivo"}
        </Badge>
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {relativeTime(channel.created_at)}
      </TableCell>
      <TableCell className="text-right">
        <div className="flex justify-end gap-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={onRotateSecret}
            disabled={pending}
          >
            Rotar secret
          </Button>
          {channel.active ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={onDeactivate}
              disabled={pending}
              className="text-destructive hover:text-destructive"
            >
              Desactivar
            </Button>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              onClick={onReactivate}
              disabled={pending}
            >
              Reactivar
            </Button>
          )}
        </div>
      </TableCell>
    </TableRow>
  );
}
