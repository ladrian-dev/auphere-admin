import "server-only";

import { cache } from "react";

import { backendFor } from "@/lib/backend";
import type { Principal } from "@/lib/principal";

/** One fetch per request for layout + metadata + page. */
export const getClientCached = cache(async (principal: Principal, ref: string) => backendFor(principal).getClient(ref));

/** Spec 017 (R3.1): el layout necesita saber si hay borrador y en qué
 *  pantallas, para el punto de la pestaña y para la barra. Una lectura por
 *  petición, compartida por el layout y por la pestaña que la vuelva a
 *  pedir. Falla en silencio: un borrador que no se puede leer no debe
 *  tumbar la ficha entera. */
export const getAgentBundleCached = cache(async (principal: Principal, ref: string) =>
  backendFor(principal)
    .getAgent(ref)
    .catch(() => null),
);
