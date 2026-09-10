"use client";

import { Laptop } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Alert,
  AlertDescription,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  EmptyState,
  Input,
  Label,
  StatusBadge,
  formatRelative,
} from "@nexus/ui";

import { archiveMachineAction, renameMachineAction } from "@/app/(console)/workstation/actions";
import { useLocale, useT } from "@/i18n/client";
import type { MachineOut } from "@/lib/backend/workstation";

import { MachineClients, type ClientOption } from "./machine-clients";
import { PairingDialog } from "./pairing-dialog";

/**
 * Mis máquinas — Requisitos 5.2, 8.1 y 11 (spec 002).
 *
 * Qué máquinas se ven lo decidió la RLS antes de llegar aquí: las mías, o
 * todas con su dueña si gestiono. Cinco estados: cargando (skeleton en la
 * página), vacío (la ausencia se diseña: sin botón apagado), error (parcial:
 * el resto de la página sigue), parcial (archivadas plegadas) e ideal.
 * Ninguna presencia se pinta como error: una máquina desconectada es lo normal.
 */
export function MachinesList({
  machines,
  failed,
  clients,
  canPair,
  manager,
  currentUserId,
}: {
  machines: MachineOut[];
  failed: boolean;
  clients: ClientOption[];
  canPair: boolean;
  manager: boolean;
  currentUserId: string;
}) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const [pending, startTransition] = React.useTransition();
  const [renaming, setRenaming] = React.useState<MachineOut | null>(null);
  const [name, setName] = React.useState("");
  const [archiving, setArchiving] = React.useState<MachineOut | null>(null);
  const [showArchived, setShowArchived] = React.useState(false);

  const active = machines.filter((m) => m.archived_at === null);
  const archived = machines.filter((m) => m.archived_at !== null);

  function rename() {
    if (!renaming) return;
    startTransition(async () => {
      const res = await renameMachineAction({ id: renaming.id, display_name: name });
      if (!res.ok) {
        // El diálogo se queda abierto con lo escrito: un error no borra el formulario.
        toast.error(res.message);
        return;
      }
      setRenaming(null);
      toast.success(t("ws.machines.renamed"));
      router.refresh();
    });
  }

  function archive(machine: MachineOut) {
    startTransition(async () => {
      const res = await archiveMachineAction({ id: machine.id });
      setArchiving(null);
      if (!res.ok) {
        toast.error(res.message);
        return;
      }
      toast.success(t("ws.machines.archived"));
      router.refresh();
    });
  }

  const canEdit = (m: MachineOut) => canPair && (m.mine || manager) && m.archived_at === null;

  return (
    <section aria-labelledby="ws-machines" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="ws-machines" className="text-lg font-semibold">
          {t("ws.machines.title")}
        </h2>
        {canPair && active.length > 0 ? <PairingDialog variant="outline" /> : null}
      </div>

      {failed ? (
        <Alert role="status">
          <AlertDescription>{t("ws.machines.unavailable")}</AlertDescription>
        </Alert>
      ) : active.length === 0 ? (
        <EmptyState
          icon={Laptop}
          title={t("ws.machines.empty.title")}
          description={canPair ? t("ws.machines.empty.body") : t("ws.machines.empty.readonly")}
          action={canPair ? <PairingDialog /> : undefined}
          readonly={!canPair}
        />
      ) : (
        <ul className="flex flex-col gap-4">
          {active.map((m) => (
            <li key={m.id}>
              <Card>
                <CardHeader className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <CardTitle className="flex min-w-0 flex-wrap items-center gap-2">
                      <span className="min-w-0 truncate" title={m.display_name}>
                        {m.display_name}
                      </span>
                      <StatusBadge tone={m.presence === "presente" ? "positive" : "muted"}>
                        {m.presence === "presente"
                          ? t("workstation.devices.present")
                          : m.last_heartbeat_at
                            ? t("workstation.devices.absentSince", { when: formatRelative(m.last_heartbeat_at, locale) })
                            : t("workstation.devices.never")}
                      </StatusBadge>
                    </CardTitle>
                    <p className="mt-1 min-w-0 break-all font-mono text-xs text-muted-foreground">
                      {t("ws.machines.hostname")}: {m.hostname}
                      {" · "}
                      {m.owner_user_id === currentUserId
                        ? t("ws.machines.mine")
                        : t("ws.machines.owner", { name: m.owner_display_name ?? m.owner_user_id })}
                    </p>
                  </div>
                  {canEdit(m) ? (
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => {
                          setName(m.display_name);
                          setRenaming(m);
                        }}
                        aria-label={`${t("ws.machines.rename")}: ${m.display_name}`}
                      >
                        {t("ws.machines.rename")}
                      </Button>
                      <Button type="button" variant="ghost" size="sm" onClick={() => setArchiving(m)} aria-label={`${t("ws.machines.archive")}: ${m.display_name}`}>
                        {t("ws.machines.archive")}
                      </Button>
                    </div>
                  ) : null}
                </CardHeader>
                <CardContent>
                  <MachineClients machineId={m.id} clients={m.clients} options={clients} canEdit={canEdit(m)} />
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      )}

      {archived.length > 0 ? (
        <div className="flex flex-col gap-2">
          <Button type="button" variant="ghost" size="sm" className="self-start" onClick={() => setShowArchived((v) => !v)} aria-expanded={showArchived}>
            {showArchived ? t("ws.machines.hideArchived") : t("ws.machines.showArchived")} ({archived.length})
          </Button>
          {showArchived ? (
            <ul className="divide-y divide-border rounded-md ring-1 ring-foreground/10">
              {archived.map((m) => (
                <li key={m.id} className="flex min-w-0 flex-wrap items-center gap-3 px-4 py-3 text-sm text-muted-foreground">
                  <span className="min-w-0 truncate" title={m.display_name}>
                    {m.display_name}
                  </span>
                  <span>{t("ws.machines.archivedSince", { when: formatRelative(m.archived_at!, locale) })}</span>
                  {m.archived_reason ? <span>· {t(`ws.machines.reason.${m.archived_reason}` as "ws.machines.reason.archivada_consola")}</span> : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      <Dialog open={renaming !== null} onOpenChange={(o) => !o && setRenaming(null)}>
        <DialogContent>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              rename();
            }}
            className="flex flex-col gap-4"
          >
            <DialogHeader>
              <DialogTitle>{t("ws.machines.renameTitle")}</DialogTitle>
              <DialogDescription>{renaming?.hostname}</DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-1">
              <Label htmlFor="machine-name">{t("ws.machines.renameField")}</Label>
              <Input id="machine-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} required />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setRenaming(null)} disabled={pending}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={pending || name.trim().length === 0} aria-busy={pending}>
                {t("ws.machines.rename")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={archiving !== null}
        onOpenChange={(o) => !o && setArchiving(null)}
        title={t("ws.machines.archiveTitle", { name: archiving?.display_name ?? "" })}
        description={t("ws.machines.archiveBody")}
        confirmLabel={t("ws.machines.archive")}
        onConfirm={() => {
          if (archiving) archive(archiving);
        }}
      />
    </section>
  );
}
