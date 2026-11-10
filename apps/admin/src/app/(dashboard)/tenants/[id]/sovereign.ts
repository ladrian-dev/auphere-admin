/**
 * Spec 047 (T172, 54.6): the words of a client's sovereign restriction. Pure,
 * so it is tested on its own; the API keeps the rule (`api/admin/client_controls.py`).
 */
import type { SovereignState } from "@/lib/backend-levers";

/** What the restriction does, the same sentence everywhere. */
export const SOVEREIGN_WHAT =
  "Solo proveedores europeos y modelos de pesos abiertos. El router no usa otros para este cliente. El partner la ve como insignia del cliente y no la puede cambiar.";

export const SOVEREIGN_ERRORS: Record<string, string> = {
  no_business_profile:
    "Este cliente todavía no tiene ficha del negocio, y la restricción se guarda en ella. Créala desde la consola del partner (o espera a que el constructor la cree) y vuelve.",
  unknown_client: "Ese cliente no existe.",
};

export type SovereignCopy = {
  badge: string;
  tone: "positive" | "muted";
  action: string;
  title: string;
  description: string;
  done: string;
};

/** The badge, the button and the dialog for the state the client is in. */
export function sovereignCopy(state: Pick<SovereignState, "enabled">, clientName: string): SovereignCopy {
  if (state.enabled) {
    return {
      badge: "Activada",
      tone: "positive",
      action: "Quitar la restricción",
      title: `Quitar la restricción soberana de ${clientName}`,
      description: "Desde el siguiente turno el router vuelve a elegir entre todos los modelos permitidos al partner.",
      done: `${clientName} ya no tiene la restricción soberana`,
    };
  }
  return {
    badge: "Desactivada",
    tone: "muted",
    action: "Activar la restricción",
    title: `Activar la restricción soberana para ${clientName}`,
    description:
      "Desde el siguiente turno el router solo elige proveedores europeos y modelos de pesos abiertos. Mira en la vista previa del router qué elegiría para su agente.",
    done: `${clientName} ya tiene la restricción soberana`,
  };
}
