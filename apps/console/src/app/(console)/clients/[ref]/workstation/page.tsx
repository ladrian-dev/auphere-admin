import { redirect } from "next/navigation";

import { WorkstationPanel } from "@/components/workstation/workstation-panel";
import { BackendError, backendFor } from "@/lib/backend";
import type { DeviceOut } from "@/lib/backend/workstation";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * El puesto de trabajo del cliente (spec 001, superficie 3a).
 *
 * **Estado parcial deliberado**: la lista blanca es la página; las máquinas son
 * un añadido. Si las máquinas no cargan, la lista se pinta igual y el bloque de
 * abajo dice que falta él —no que falle todo—. Es el mismo reparto que hace la
 * pestaña de herramientas con los conectores, y lo que §V llama `parcial`:
 * acotar el alcance de lo que se afirma en vez de mentir en bloque.
 */
export default async function WorkstationPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  if (!can(principal.role, "workstation:read")) redirect(`/clients/${ref}`);
  const api = backendFor(principal);
  const [executables, devicesRes] = await Promise.all([
    api.listExecutables(ref),
    api.listDevices(ref).then(
      (devices) => ({ devices, failed: false }),
      (err: unknown) => {
        if (err instanceof BackendError) return { devices: [] as DeviceOut[], failed: true };
        throw err;
      },
    ),
  ]);
  return (
    <WorkstationPanel
      clientRef={ref}
      executables={executables}
      devices={devicesRes.devices}
      devicesFailed={devicesRes.failed}
      manage={can(principal.role, "workstation:write")}
    />
  );
}
