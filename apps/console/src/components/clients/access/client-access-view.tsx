"use client";

import * as React from "react";

import { reloadClientAccessAction } from "@/app/(console)/clients/[ref]/access/actions";
import type { ClientAccess } from "@/lib/backend/client-access";

import { ClientConsoleCard } from "./client-console-card";
import { ClientPeopleCard } from "./client-people-card";

/**
 * Spec 056 (Requisito 3, D4) — la pestaña «Acceso» de un cliente: dos tarjetas,
 * «Consola del cliente» y «Personas», sobre una sola lectura. Lo que guarda una
 * lo ve la otra (apagar la consola cierra la invitación; una invitación nueva
 * entra en la lista sin recargar).
 */
export function ClientAccessView({ refId, initial }: { refId: string; initial: ClientAccess | null }) {
  const [access, setAccess] = React.useState<ClientAccess | null>(initial);
  const [retrying, startRetry] = React.useTransition();

  function retry() {
    startRetry(async () => {
      const res = await reloadClientAccessAction({ ref: refId });
      if (res.ok) setAccess(res.data);
    });
  }

  return (
    <div className="grid min-w-0 gap-6 lg:grid-cols-2 lg:items-start" data-slot="client-access">
      <ClientConsoleCard refId={refId} access={access} onSaved={setAccess} onRetry={retry} retrying={retrying} />
      <ClientPeopleCard
        refId={refId}
        access={access}
        onMembers={(members) => setAccess((prev) => (prev ? { ...prev, members } : prev))}
        onRetry={retry}
        retrying={retrying}
      />
    </div>
  );
}
