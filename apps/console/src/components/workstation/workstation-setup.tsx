import { backendFor } from "@/lib/backend";
import type { Principal } from "@/lib/principal";
import { can } from "@/lib/principal";

import { WorkstationSetupCard } from "./workstation-setup-card";

/**
 * Envoltorio de servidor de la tarjeta de puesta en marcha para la home
 * (Requisito 6). Solo para quien puede emparejar (6.5): a los demás no se
 * les muestra ni apagada ni explicada.
 */
export async function WorkstationSetup({ principal }: { principal: Principal }) {
  if (!can(principal.role, "workstation:pair")) return null;
  const setup = await backendFor(principal).workstationSetup().catch(() => null);
  return <WorkstationSetupCard setup={setup} />;
}
