import { notFound } from "next/navigation";

import {
  EmptyState,
  ErrorState,
  Section,
  StatusBadge,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@nexus/ui";

import { backend } from "@/lib/backend";
import { relativeTime } from "@/lib/format";

export const dynamic = "force-dynamic";

const ROLE: Record<string, string> = {
  owner: "Propietario",
  admin: "Administrador",
  builder: "Constructor",
  analyst: "Analista",
  billing: "Facturación",
};

/** Spec 031 (R4.6): who works in the partner's console, and who is invited. */
export default async function PartnerTeamPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const partner = await backend.getPartner(id);
  if (!partner) notFound();
  const team = await backend.getPartnerMembers(id).catch(() => null);
  if (!team) {
    return <ErrorState title="No se pudo leer el equipo" description="La API no respondió. Vuelve a intentarlo en un momento." />;
  }
  return (
    <div className="grid gap-6">
      <Section title="Personas" description="Quién entra en la consola de este partner y con qué rol." padded={team.members.length === 0}>
        {team.members.length === 0 ? (
          <EmptyState title="Nadie ha entrado todavía" description="Cuando el partner acepte su invitación aparecerá aquí." readonly />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Persona</TableHead>
                  <TableHead>Rol</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead className="hidden md:table-cell text-right">Último acceso</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {team.members.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell>
                      <div className="font-medium">{m.display_name ?? m.email}</div>
                      <div className="text-xs text-muted-foreground">{m.email}</div>
                    </TableCell>
                    <TableCell>{ROLE[m.role] ?? m.role}</TableCell>
                    <TableCell>
                      <StatusBadge tone={m.status === "active" ? "positive" : "muted"}>
                        {m.status === "active" ? "Activa" : "Suspendida"}
                      </StatusBadge>
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-right text-muted-foreground tabular-nums">
                      {m.last_login_at ? relativeTime(m.last_login_at) : "Nunca"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Section>
      {team.invitations.length > 0 ? (
        <Section title="Invitaciones pendientes" description="Enlaces enviados que todavía nadie ha aceptado." padded={false}>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Correo</TableHead>
                  <TableHead>Rol</TableHead>
                  <TableHead className="text-right">Caduca</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {team.invitations.map((i) => (
                  <TableRow key={i.id}>
                    <TableCell>
                      <span className="font-medium">{i.email}</span>{" "}
                      <StatusBadge tone="info">Invitación pendiente</StatusBadge>
                    </TableCell>
                    <TableCell>{ROLE[i.role] ?? i.role}</TableCell>
                    <TableCell className="text-right text-muted-foreground tabular-nums">{relativeTime(i.expires_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </Section>
      ) : null}
    </div>
  );
}
