import { api, call } from "./client";
import type { components } from "./schema.gen";

/**
 * Spec 069, R17.2: the Bandeja's inactivity close, the same routes the web's
 * «Ajustes de la Bandeja» uses (spec 064, R5): `GET` and `PATCH
 * /console/lite/inbox/settings`. Typed from the API's own OpenAPI; the client
 * is the request's (`lite_scope("inbox")`), never a field of the body.
 */
export type InboxSettings = components["schemas"]["InboxSettingsOut"];

/** The only values the API takes (`inbox_lifecycle.AUTOCLOSE_HOURS`); `null` is «Nunca», the starting one. */
export const AUTOCLOSE_HOURS = [24, 72, 168, 720] as const;
export type Autoclose = (typeof AUTOCLOSE_HOURS)[number] | null;

export function isAutoclose(v: unknown): v is Autoclose {
  return v === null || (AUTOCLOSE_HOURS as readonly unknown[]).includes(v);
}

export const ajustesApi = {
  inboxSettings: () => call(api.GET("/console/lite/inbox/settings")) as Promise<InboxSettings>,
  setInboxSettings: (autoclose: Autoclose) =>
    call(api.PATCH("/console/lite/inbox/settings", { body: { autoclose_hours: autoclose } })) as Promise<InboxSettings>,
};
