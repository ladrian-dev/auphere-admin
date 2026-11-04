import Link from "next/link";

import { StatusDot } from "@nexus/ui";

import type { PartnerMembersOut } from "@/lib/backend";
import { longDate, relativeTime } from "@/lib/format";

/**
 * Spec 052 (R3.12): en todas las pestañas de la ficha, si el partner no tiene
 * propietario activo. Si no se pudo leer el equipo no se afirma nada: esta línea
 * no puede decir que falta un propietario sin saberlo (constitución §V).
 */
export function OwnerNotice({ partnerId, team }: { partnerId: string; team: PartnerMembersOut | null }) {
  if (!team || team.owner.has_active_owner) return null;
  const live = team.invitations.filter((i) => i.from_auphere).at(-1);
  const { expired_email: expiredEmail, expired_at: expiredAt } = team.owner;

  let state: string | null = null;
  if (live) {
    state = live.last_sent_at
      ? `Invitación a ${live.email}, enviada ${relativeTime(live.last_sent_at)}.`
      : `Invitación a ${live.email}: no consta el envío.`;
  } else if (expiredEmail) {
    state = `La invitación a ${expiredEmail} caducó el ${longDate(expiredAt)}.`;
  }

  return (
    <p className="min-w-0 text-sm text-pretty wrap-anywhere">
      <StatusDot tone="warning" className="mr-2 align-middle" />
      <span className="font-medium">Sin propietario activo.</span>{" "}
      {state ? <span className="text-muted-foreground">{state}</span> : null}{" "}
      <Link
        href={`/partners/${partnerId}/team`}
        className="inline-flex min-h-6 items-center rounded-sm underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
      >
        Ver Equipo
      </Link>
    </p>
  );
}
