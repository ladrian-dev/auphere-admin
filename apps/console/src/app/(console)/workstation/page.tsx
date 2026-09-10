import { redirect } from "next/navigation";

import { PageHeader } from "@nexus/ui";

import { MachinesList } from "@/components/workstation/machines-list";
import { PresenceRefresh } from "@/components/workstation/presence-refresh";
import { WorkstationSetupCard } from "@/components/workstation/workstation-setup-card";
import { getT } from "@/i18n/server";
import { BackendError, backendFor } from "@/lib/backend";
import type { MachineOut, SetupOut } from "@/lib/backend/workstation";
import { can, requirePrincipal } from "@/lib/principal";

export const metadata = { title: "Puesto de trabajo" };

/**
 * El puesto de trabajo a nivel de partner (spec 002).
 *
 * Mis máquinas —o todas, con dueña, si gestiono—, a qué clientes sirve cada
 * una y si el directorio está declarado. **Estado parcial deliberado**: si
 * las máquinas no cargan, la puesta en marcha y la cabecera se pintan igual y
 * el bloque dice que falta él (§V). Los ejecutables no están aquí: son del
 * cliente y viven en su página.
 */
export default async function WorkstationPage() {
  const principal = await requirePrincipal("/workstation");
  if (!can(principal.role, "workstation:read")) redirect("/");
  const canPair = can(principal.role, "workstation:pair");
  const { t } = await getT(principal.locale);
  const api = backendFor(principal);

  const [machinesRes, clients, setup] = await Promise.all([
    api.listMachines(true).then(
      (machines) => ({ machines, failed: false }),
      (err: unknown) => {
        if (err instanceof BackendError) return { machines: [] as MachineOut[], failed: true };
        throw err;
      },
    ),
    can(principal.role, "clients:read")
      ? api.listClients({ limit: 100 }).then((page) => page.items.map((c) => ({ ref: c.external_client_ref, name: c.name })), () => [])
      : Promise.resolve([]),
    canPair ? api.workstationSetup().catch((): SetupOut | null => null) : Promise.resolve<SetupOut | null>(null),
  ]);

  return (
    <>
      <PageHeader eyebrow={principal.partnerName} title={t("ws.title")} description={t("ws.description")} />
      <PresenceRefresh />
      {canPair ? <WorkstationSetupCard setup={setup} /> : null}
      <MachinesList
        machines={machinesRes.machines}
        failed={machinesRes.failed}
        clients={clients}
        canPair={canPair}
        manager={can(principal.role, "workstation:write")}
        currentUserId={principal.userId}
      />
    </>
  );
}
