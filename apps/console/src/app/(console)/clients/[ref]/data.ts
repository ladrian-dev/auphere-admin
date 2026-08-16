import "server-only";

import { cache } from "react";

import { backendFor } from "@/lib/backend";
import type { Principal } from "@/lib/principal";

/** One fetch per request for layout + metadata + page. */
export const getClientCached = cache(async (principal: Principal, ref: string) => backendFor(principal).getClient(ref));
