"use client";

import { useTransition } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type {
  AuphereOwnerChannelOut,
  OwnerPhoneIndexOut,
} from "@/lib/backend";
import { relativeTime } from "@/lib/format";

import type {
  deregisterOwnerAction,
  updateOwnerAction,
} from "./actions";

type UpdateAction = typeof updateOwnerAction;
type DeregisterAction = typeof deregisterOwnerAction;

const _SENTINEL_DEFAULT = "__default__";

export function OwnersTable({
  tenantId,
  owners,
  channels,
  updateAction,
  deregisterAction,
}: {
  tenantId: string;
  owners: OwnerPhoneIndexOut[];
  channels: AuphereOwnerChannelOut[];
  updateAction: UpdateAction;
  deregisterAction: DeregisterAction;
}) {
  if (owners.length === 0) {
    return (
      <div className="rounded-md border border-dashed py-10 text-center text-sm text-muted-foreground">
        Sin dueños registrados todavía. Añadí uno desde el formulario de
        abajo.
      </div>
    );
  }
  const channelMap = new Map(channels.map((c) => [c.id, c]));
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Teléfono</TableHead>
          <TableHead>Etiqueta</TableHead>
          <TableHead>Estado</TableHead>
          <TableHead>Canal Auphere</TableHead>
          <TableHead>Alta</TableHead>
          <TableHead className="text-right">Acción</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {owners.map((owner) => (
          <OwnerRow
            key={owner.phone_e164}
            tenantId={tenantId}
            owner={owner}
            channels={channels}
            channelMap={channelMap}
            updateAction={updateAction}
            deregisterAction={deregisterAction}
          />
        ))}
      </TableBody>
    </Table>
  );
}

function OwnerRow({
  tenantId,
  owner,
  channels,
  channelMap,
  updateAction,
  deregisterAction,
}: {
  tenantId: string;
  owner: OwnerPhoneIndexOut;
  channels: AuphereOwnerChannelOut[];
  channelMap: Map<string, AuphereOwnerChannelOut>;
  updateAction: UpdateAction;
  deregisterAction: DeregisterAction;
}) {
  const [pending, startTransition] = useTransition();

  function onChangeChannel(value: string) {
    const isDefault = !value || value === _SENTINEL_DEFAULT;
    startTransition(async () => {
      const result = await updateAction(
        tenantId,
        owner.phone_e164,
        isDefault
          ? { clear_channel_id: true }
          : { auphere_channel_id: value },
      );
      if (!result.ok) {
        toast.error("No se pudo actualizar el canal", {
          description: result.error,
        });
        return;
      }
      toast.success("Canal actualizado");
    });
  }

  function onToggleActive() {
    startTransition(async () => {
      const result = await updateAction(tenantId, owner.phone_e164, {
        active: !owner.active,
      });
      if (!result.ok) {
        toast.error(
          owner.active ? "No se pudo desactivar" : "No se pudo reactivar",
          { description: result.error },
        );
        return;
      }
      toast.success(owner.active ? "Desactivado" : "Reactivado");
    });
  }

  function onDeregister() {
    if (!confirm(`¿Desregistrar ${owner.phone_e164} de este tenant?`)) {
      return;
    }
    startTransition(async () => {
      const result = await deregisterAction(tenantId, owner.phone_e164);
      if (!result.ok) {
        toast.error("No se pudo desregistrar", {
          description: result.error,
        });
        return;
      }
      toast.success(`Desregistrado ${owner.phone_e164}`);
    });
  }

  const pinnedChannel = owner.auphere_channel_id
    ? channelMap.get(owner.auphere_channel_id)
    : null;

  return (
    <TableRow data-testid={`owner-row-${owner.phone_e164}`}>
      <TableCell className="font-mono text-xs">{owner.phone_e164}</TableCell>
      <TableCell>{owner.user_label ?? "—"}</TableCell>
      <TableCell>
        <Badge variant={owner.active ? "default" : "outline"}>
          {owner.active ? "Activo" : "Inactivo"}
        </Badge>
      </TableCell>
      <TableCell>
        <Select
          value={owner.auphere_channel_id ?? _SENTINEL_DEFAULT}
          onValueChange={(v) => onChangeChannel(v || _SENTINEL_DEFAULT)}
          disabled={pending}
        >
          <SelectTrigger className="h-8 text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={_SENTINEL_DEFAULT}>
              Default del provider
            </SelectItem>
            {channels.map((c) => (
              <SelectItem key={c.id} value={c.id} className="text-xs">
                {c.display_name} · {c.phone_e164}
                {c.is_default ? " ★" : ""}
              </SelectItem>
            ))}
            {/* Show stale pin if the pinned channel was deactivated. */}
            {pinnedChannel === null && owner.auphere_channel_id ? (
              <SelectItem value={owner.auphere_channel_id} className="text-xs text-amber-700">
                (canal eliminado)
              </SelectItem>
            ) : null}
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell className="text-xs text-muted-foreground">
        {relativeTime(owner.added_at)}
      </TableCell>
      <TableCell className="text-right">
        <div className="flex justify-end gap-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={onToggleActive}
            disabled={pending}
          >
            {owner.active ? "Desactivar" : "Reactivar"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={onDeregister}
            disabled={pending}
            className="text-destructive hover:text-destructive"
          >
            Desregistrar
          </Button>
        </div>
      </TableCell>
    </TableRow>
  );
}
