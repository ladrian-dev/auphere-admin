"use client";

import { FolderOpen } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, ConfirmDialog, Label, StatusBadge } from "@nexus/ui";

import { linkClientAction, unlinkClientAction } from "@/app/(console)/workstation/actions";
import { useT } from "@/i18n/client";
import type { MachineClientOut } from "@/lib/backend/workstation";

export type ClientOption = { ref: string; name: string };

const SELECT_CLASS =
  "h-8 min-w-0 rounded-md border border-input bg-transparent px-3 text-sm focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

/**
 * A qué clientes sirve una máquina — Requisitos 4.1, 7 y 8 (spec 002).
 *
 * Vincular aquí crea el vínculo **sin directorio**: la ruta la declara la
 * máquina desde su barra, con el selector nativo. Por eso «pendiente de
 * declarar desde la máquina» es un estado, no un campo. Cuando no hay
 * clientes que vincular, no hay selector apagado: la ausencia se diseña.
 */
export function MachineClients({
  machineId,
  clients,
  options,
  canEdit,
}: {
  machineId: string;
  clients: MachineClientOut[];
  options: ClientOption[];
  canEdit: boolean;
}) {
  const t = useT();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [chosen, setChosen] = React.useState("");
  const [removing, setRemoving] = React.useState<MachineClientOut | null>(null);
  const linked = new Set(clients.map((c) => c.ref));
  const available = options.filter((o) => !linked.has(o.ref));

  function link() {
    if (!chosen) return;
    const option = available.find((o) => o.ref === chosen);
    startTransition(async () => {
      const res = await linkClientAction({ id: machineId, ref: chosen });
      if (!res.ok) {
        toast.error(res.message);
        return;
      }
      toast.success(t("ws.clients.added", { name: option?.name ?? chosen }));
      setChosen("");
      router.refresh();
    });
  }

  function unlink(client: MachineClientOut) {
    startTransition(async () => {
      const res = await unlinkClientAction({ id: machineId, ref: client.ref });
      setRemoving(null);
      if (!res.ok) {
        toast.error(res.message);
        return;
      }
      toast.success(t("ws.clients.removed", { name: client.name ?? client.ref }));
      router.refresh();
    });
  }

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <h4 className="text-sm font-medium">{t("ws.clients.title")}</h4>
      {clients.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("ws.machines.clients.none")}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {clients.map((client) => (
            <li key={client.ref} className="flex min-w-0 flex-wrap items-center gap-2 text-sm">
              <span className="min-w-0 truncate font-medium" title={client.name ?? client.ref}>
                {client.name ?? client.ref}
              </span>
              {client.needs_directory ? (
                <StatusBadge tone="muted">{t("ws.clients.dirPending")}</StatusBadge>
              ) : (
                <span className="inline-flex min-w-0 items-center gap-1 font-mono text-xs text-muted-foreground">
                  <FolderOpen className="size-3 shrink-0" aria-hidden="true" />
                  <span className="truncate" title={client.workdir ?? undefined}>
                    {client.workdir}
                  </span>
                </span>
              )}
              {canEdit ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setRemoving(client)}
                  disabled={pending}
                  aria-label={`${t("ws.clients.remove")}: ${client.name ?? client.ref}`}
                >
                  {t("ws.clients.remove")}
                </Button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
      {canEdit ? (
        options.length === 0 ? (
          <p className="text-sm text-muted-foreground text-pretty">{t("ws.clients.noClients")}</p>
        ) : available.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("ws.clients.allLinked")}</p>
        ) : (
          <form
            className="flex flex-wrap items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              link();
            }}
          >
            <div className="flex min-w-0 flex-col gap-1">
              <Label htmlFor={`link-${machineId}`}>{t("ws.clients.addField")}</Label>
              <select id={`link-${machineId}`} className={SELECT_CLASS} value={chosen} onChange={(e) => setChosen(e.target.value)} disabled={pending}>
                <option value="">—</option>
                {available.map((o) => (
                  <option key={o.ref} value={o.ref}>
                    {o.name}
                  </option>
                ))}
              </select>
            </div>
            <Button type="submit" variant="outline" size="sm" disabled={!chosen || pending} aria-busy={pending}>
              {t("ws.clients.add")}
            </Button>
            <p className="basis-full text-xs text-muted-foreground text-pretty">{t("ws.clients.addHelp")}</p>
          </form>
        )
      ) : null}
      <ConfirmDialog
        open={removing !== null}
        onOpenChange={(o) => !o && setRemoving(null)}
        title={t("ws.clients.removeTitle", { name: removing?.name ?? removing?.ref ?? "" })}
        description={t("ws.clients.removeBody")}
        confirmLabel={t("ws.clients.remove")}
        onConfirm={() => {
          if (removing) unlink(removing);
        }}
      />
    </div>
  );
}
