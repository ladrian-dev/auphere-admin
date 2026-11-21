import type { InboxEvent } from "../sse";

import { CONVERSATION_IDS, nuriaSeed } from "./data";
import { DemoHttpError, latency, match, pause, readRequest, respond, type Route } from "./http";
import { reservasRoutes } from "./reservas";
import { appRoutes } from "./routes";
import { resetState, state } from "./state";

/**
 * The example API (spec 069, Requisito 23): a fictional business in memory,
 * with the same shapes as the API, for a development build that asks for it
 * (`EXPO_PUBLIC_DEMO=1`, `config.ts`). Nothing here is loaded outside
 * `__DEV__`: the caller requires it inside that branch.
 *
 * - `demoFetch` stands in for `fetch` under the typed clients, the renewal,
 *   Reservas and the uploads: same signature, same answers as the API.
 * - `demoEvents` stands in for the Bandeja's live line: 3.2 s after it is
 *   listened to, a new Instagram conversation arrives (Nuria), once.
 */

/** Every route the example answers: method and the schema's path. */
export const demoRoutes: readonly Route[] = [...appRoutes, ...reservasRoutes];

/** Ids of the example conversations by name (`lucia`, `sofia`, `nuria`…), for deep links and screenshots. */
export const demoIds = CONVERSATION_IDS;

export async function demoFetch(input: Request | string, init?: RequestInit): Promise<Response> {
  const req = await readRequest(input, init);
  const found = match(demoRoutes, req.method, req.path);
  if (!found) {
    console.warn(`[demo] no example for ${req.method} ${req.path}`);
    return respond(404, { detail: { code: "not_found" } });
  }
  if (found.route.wait) await pause(latency());
  try {
    return respond(found.route.status, await found.route.handle(req, found.params));
  } catch (e) {
    if (e instanceof DemoHttpError) return respond(e.status, e.body);
    console.warn(`[demo] ${req.method} ${req.path} failed`, e);
    return respond(500, { detail: { code: "demo_error" } });
  }
}

/** When the new conversation arrives after the line opens (inventory B §3.9). */
export const ARRIVAL_MS = 3200;

/**
 * The live line, in the shape `sse.ts` acts on (`InboxEvent`). The arrival
 * joins the example first, then is told; it happens once, however many times
 * the line opens again (foreground, remount). Returns the way to stop.
 */
export function demoEvents(onEvent: (e: InboxEvent) => void): () => void {
  const timer = setTimeout(() => {
    const now = Date.now();
    if (state().inbox.add(nuriaSeed(now), now)) onEvent({ event: "message.new", conversation_id: CONVERSATION_IDS.nuria });
  }, ARRIVAL_MS);
  return () => clearTimeout(timer);
}

/** Start the example again from its first state (tests; a fresh app start does it by itself). */
export function resetDemo(): void {
  resetState();
}
