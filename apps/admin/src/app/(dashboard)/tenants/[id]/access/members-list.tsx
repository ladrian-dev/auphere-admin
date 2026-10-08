"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ClientMemberOut } from "@/lib/backend";

import { resendAction, revokeAction } from "./actions";

const STATUS: Record<string, { label: string; variant: "default" | "secondary" | "outline" | "destructive" }> = {
  active: { label: "Activa", variant: "default" },
  pending: { label: "Invitación pendiente", variant: "secondary" },
  expired: { label: "Invitación caducada", variant: "outline" },
  revoked: { label: "Revocada", variant: "outline" },
};

/**
 * Spec 030 (R1.6, R1.7, R1.9): who has access to the client console. A
 * person can be revoked (their sessions close); an invitation can be resent
 * (the old link dies) or revoked.
 */
export function MembersList({ tenantId, members }: { tenantId: string; members: ClientMemberOut[] }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [revoking, setRevoking] = useState<ClientMemberOut | null>(null);
  const [lastLink, setLastLink] = useState<string | null>(null);

  if (members.length === 0) {
    return <p className="text-sm text-muted-foreground">Nadie tiene acceso todavía.</p>;
  }

  function resend(m: ClientMemberOut) {
    startTransition(async () => {
      const res = await resendAction(tenantId, m.id);
      if (!res.ok) {
        toast.error("No se pudo reenviar", { description: res.error });
        return;
      }
      setLastLink(res.data.accept_path);
      toast.success(res.data.email_sent ? `Invitación reenviada a ${m.email}` : "Enlace nuevo creado (el correo no salió)");
      router.refresh();
    });
  }

  function revoke() {
    const m = revoking;
    if (!m) return;
    startTransition(async () => {
      const res = await revokeAction(tenantId, m.id);
      setRevoking(null);
      if (!res.ok) {
        toast.error("No se pudo revocar", { description: res.error });
        return;
      }
      toast.success(m.kind === "member" ? `${m.email} ya no tiene acceso` : "Invitación revocada");
      router.refresh();
    });
  }

  return (
    <div className="grid gap-3">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Persona</TableHead>
            <TableHead>Estado</TableHead>
            <TableHead className="text-right">Acciones</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {members.map((m) => {
            const status = STATUS[m.status] ?? { label: m.status, variant: "outline" as const };
            const canResend = m.kind === "invitation" && m.status !== "revoked";
            const canRevoke = m.status === "active" || m.status === "pending";
            return (
              <TableRow key={m.id}>
                <TableCell className="min-w-0">
                  <span className="block truncate font-medium">{m.name || m.email}</span>
                  {m.name ? <span className="block truncate text-xs text-muted-foreground">{m.email}</span> : null}
                </TableCell>
                <TableCell>
                  <Badge variant={status.variant}>{status.label}</Badge>
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    {canResend || m.status === "expired" ? (
                      <Button size="sm" variant="outline" disabled={pending} onClick={() => resend(m)} aria-label={`Reenviar a ${m.email}`}>
                        Reenviar
                      </Button>
                    ) : null}
                    {canRevoke ? (
                      <Button size="sm" variant="ghost" disabled={pending} onClick={() => setRevoking(m)} aria-label={`Revocar a ${m.email}`}>
                        Revocar
                      </Button>
                    ) : null}
                  </div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      {lastLink ? (
        <p className="text-xs text-muted-foreground">
          Enlace nuevo, por si el correo no llega: <code className="break-all">{lastLink}</code>
        </p>
      ) : null}
      <Dialog open={revoking !== null} onOpenChange={(open) => (open ? undefined : setRevoking(null))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{revoking?.kind === "member" ? "Retirar el acceso" : "Revocar la invitación"}</DialogTitle>
            <DialogDescription>
              {revoking?.kind === "member"
                ? `${revoking?.email} deja de entrar en la consola y se cierran sus sesiones abiertas.`
                : `El enlace enviado a ${revoking?.email ?? ""} deja de servir.`}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRevoking(null)}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={revoke} disabled={pending}>
              {revoking?.kind === "member" ? "Retirar acceso" : "Revocar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
