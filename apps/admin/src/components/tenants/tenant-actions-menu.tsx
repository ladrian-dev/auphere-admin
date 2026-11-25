"use client";

/**
 * Tenant lifecycle action menu — Block M.1.
 *
 * Two surfaces use this:
 * - The `/tenants` table (one menu per row, compact icon trigger).
 * - The `/tenants/[id]/...` header (a fuller trigger with the label).
 *
 * Behaviour matrix:
 * - active   → Pausar, Archivar
 * - paused   → Reanudar, Archivar
 * - archived → Reanudar (returns to active), Eliminar (destructive)
 *
 * Pause / Resume happen on click with no confirm (reversible, fast, with
 * undo toast). Archive confirms with a dialog. Delete requires the
 * operator to type the slug — speedbump, not a server check.
 */

import { MoreHorizontal } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import {
  Button,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
  Label,
} from "@nexus/ui";
import type { TenantStatus } from "@/lib/backend";

import {
  archiveTenantAction,
  deleteTenantAction,
  setSendOnlyAction,
  setTenantPausedAction,
} from "@/app/(dashboard)/tenants/actions";

type Variant = "icon" | "labelled";

export function TenantActionsMenu({
  tenantId,
  slug,
  name,
  status,
  variant = "icon",
  /** Where to land after a successful hard-delete. From the per-tenant
   *  page this should be "/tenants" so the operator doesn't sit on a 404;
   *  from the table row it stays where it is (the row revalidates away). */
  redirectAfterDeleteTo,
  sendOnly,
}: {
  tenantId: string;
  slug: string;
  name: string;
  status: TenantStatus;
  variant?: Variant;
  redirectAfterDeleteTo?: string;
  /** Spec 077 (1.5): given (the client's page), the menu offers to mark or unmark it. */
  sendOnly?: boolean;
}) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [typedSlug, setTypedSlug] = useState("");
  const [sendOnlyOpen, setSendOnlyOpen] = useState(false);
  const [sendOnlyError, setSendOnlyError] = useState<string | null>(null);

  async function onSendOnly() {
    setSendOnlyError(null);
    const next = !sendOnly;
    const res = await setSendOnlyAction(tenantId, next);
    if (!res.ok) {
      setSendOnlyError(res.error);
      return;
    }
    setSendOnlyOpen(false);
    toast.success(next ? `${name} es ahora de solo envío` : `${name} ya no es de solo envío`);
    router.refresh();
  }

  function changeStatus(
    next: TenantStatus,
    {
      successMessage,
      undoTo,
    }: { successMessage: string; undoTo?: TenantStatus } = {
      successMessage: "Tenant actualizado",
    },
  ) {
    start(async () => {
      // Spec 079 (2.4): archiving is its own action, with its own permission.
      const res =
        next === "archived"
          ? await archiveTenantAction(tenantId)
          : next === "active" || next === "paused"
            ? await setTenantPausedAction(tenantId, next)
            : ({ ok: false, error: `estado no admitido: ${next}` } as const);
      if (!res.ok) {
        toast.error(`No se pudo actualizar: ${res.error}`);
        return;
      }
      if (undoTo) {
        toast.success(successMessage, {
          action: {
            label: "Deshacer",
            onClick: () => changeStatus(undoTo, { successMessage: `${name} reanudado` }),
          },
        });
      } else {
        toast.success(successMessage);
      }
    });
  }

  function onPause() {
    changeStatus("paused", {
      successMessage: `${name} pausado — agente silenciado`,
      undoTo: "active",
    });
  }
  function onResume() {
    changeStatus("active", {
      successMessage: `${name} reanudado — agente vuelve a responder`,
    });
  }
  function onArchive() {
    setArchiveOpen(false);
    changeStatus("archived", {
      successMessage: `${name} archivado`,
      undoTo: status === "paused" ? "paused" : "active",
    });
  }
  function onDelete() {
    start(async () => {
      const res = await deleteTenantAction(tenantId);
      if (!res.ok) {
        toast.error(`No se pudo eliminar: ${res.error}`);
        return;
      }
      setDeleteOpen(false);
      toast.success(`${name} eliminado permanentemente`);
      if (redirectAfterDeleteTo) router.push(redirectAfterDeleteTo);
      else router.refresh();
    });
  }

  const slugMatches = typedSlug.trim() === slug;

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            variant === "icon" ? (
              <Button
                variant="ghost"
                size="sm"
                className="size-8 p-0"
                aria-label={`Acciones para ${name}`}
                disabled={pending}
                onClick={(e) => e.stopPropagation()}
              >
                <MoreHorizontal className="size-4" />
              </Button>
            ) : (
              <Button
                variant="outline"
                size="sm"
                disabled={pending}
                onClick={(e) => e.stopPropagation()}
              >
                {pending ? "Procesando…" : "Acciones"}
              </Button>
            )
          }
        />
        <DropdownMenuContent align="end" className="min-w-48">
          {/*
            Base UI requires Menu.GroupLabel + the Items it labels to live
            inside the same Menu.Group, otherwise Menu.GroupLabel throws
            ``MenuGroupRootContext is missing`` at open-time and the
            global error boundary surfaces "This page couldn't load". The
            app-sidebar uses the same wrapper for the same reason.
          */}
          <DropdownMenuGroup>
            <DropdownMenuLabel className="text-xs uppercase tracking-wider text-muted-foreground">
              Ciclo de vida
            </DropdownMenuLabel>

            {status === "active" ? (
              <DropdownMenuItem disabled={pending} onClick={onPause}>
                Pausar agente
              </DropdownMenuItem>
            ) : null}

            {status === "paused" ? (
              <DropdownMenuItem disabled={pending} onClick={onResume}>
                Reanudar agente
              </DropdownMenuItem>
            ) : null}

            {status === "archived" ? (
              <DropdownMenuItem disabled={pending} onClick={onResume}>
                Restaurar (volver a activo)
              </DropdownMenuItem>
            ) : null}

            {(status === "active" || status === "paused" || status === "provisioning") ? (
              <DropdownMenuItem
                disabled={pending}
                onClick={() => setArchiveOpen(true)}
              >
                Archivar…
              </DropdownMenuItem>
            ) : null}

            {status === "archived" ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  variant="destructive"
                  disabled={pending}
                  onClick={() => setDeleteOpen(true)}
                >
                  Eliminar permanentemente…
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuGroup>
          {sendOnly !== undefined ? (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                <DropdownMenuLabel className="text-xs uppercase tracking-wider text-muted-foreground">
                  Tipo de cliente
                </DropdownMenuLabel>
                <DropdownMenuItem disabled={pending} onClick={() => setSendOnlyOpen(true)}>
                  {sendOnly ? "Quitar solo envío…" : "Marcar como solo envío…"}
                </DropdownMenuItem>
              </DropdownMenuGroup>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>

      {sendOnly !== undefined ? (
        <ConfirmDialog
          open={sendOnlyOpen}
          onOpenChange={(open) => {
            setSendOnlyOpen(open);
            if (!open) setSendOnlyError(null);
          }}
          title={sendOnly ? `¿Quitar solo envío a ${name}?` : `¿Marcar ${name} como solo envío?`}
          description={
            sendOnly
              ? "La ficha vuelve a mostrar Agente, Habilidades, Playground y Canal del dueño. Sus números siguen sin agente: para que responda uno, publícalo y asígnalo en Canales. Queda en Auditoría con tu nombre."
              : "Sus números de WhatsApp dejan de responder: quedan sin agente, solo como línea de avisos. La ficha oculta Agente, Habilidades, Playground y Canal del dueño, y muestra «Envío por API». Queda en Auditoría con tu nombre."
          }
          confirmLabel={sendOnly ? "Quitar solo envío" : "Marcar como solo envío"}
          // Marking it silences the client's numbers; unmarking changes nothing they answer.
          destructive={!sendOnly}
          onConfirm={onSendOnly}
          error={sendOnlyError ?? undefined}
        />
      ) : null}

      <Dialog open={archiveOpen} onOpenChange={setArchiveOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Archivar {name}</DialogTitle>
            <DialogDescription>
              El agente deja de responder y el tenant se oculta del flujo
              operativo, pero todos los datos (conversaciones, audit log,
              versiones del agente) se preservan. Podés restaurarlo después
              o eliminarlo permanentemente desde acá mismo.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setArchiveOpen(false)}
              disabled={pending}
            >
              Cancelar
            </Button>
            <Button size="sm" onClick={onArchive} disabled={pending}>
              {pending ? "Archivando…" : "Archivar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={deleteOpen}
        onOpenChange={(o) => {
          if (!pending) setDeleteOpen(o);
          if (!o) setTypedSlug("");
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Eliminar {name} permanentemente</DialogTitle>
            <DialogDescription>
              Esto borra el tenant y <strong>todas</strong> sus
              conversaciones, mensajes, versiones del agente, connectors
              instalados y registros de auditoría. No se puede deshacer.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="confirm-slug" className="text-sm">
              Para confirmar, escribí{" "}
              <code className="font-mono text-foreground">{slug}</code>:
            </Label>
            <Input
              id="confirm-slug"
              value={typedSlug}
              onChange={(e) => setTypedSlug(e.target.value)}
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck={false}
              disabled={pending}
              className="font-mono"
            />
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setDeleteOpen(false)}
              disabled={pending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={onDelete}
              disabled={pending || !slugMatches}
            >
              {pending ? "Eliminando…" : "Eliminar para siempre"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
