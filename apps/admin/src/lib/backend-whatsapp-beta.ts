/**
 * Spec 047 (T117, 31.5, 54.7): the «WhatsApp login» beta by country
 * (`api/admin/whatsapp_login_beta.py`). Same `call`, same token; the write
 * names the operator (`X-Operator-Id`) and carries its reason, which go to
 * the platform audit. Server-side only.
 */

import "server-only";

import { call } from "@/lib/backend";

export type LoginBetaCountry = {
  /** ISO 3166-1 alpha-2, upper case. */
  country: string;
  enabled_at: string;
  /** `operator:{id}`. */
  enabled_by: string;
};

export const loginBetaBackend = {
  countries: () => call<LoginBetaCountry[]>("/admin/whatsapp/login-beta/countries"),
  /** Answers the whole list after the change. */
  setCountry: (iso2: string, body: { enabled: boolean; reason: string }, operatorId: string) =>
    call<LoginBetaCountry[]>(`/admin/whatsapp/login-beta/countries/${encodeURIComponent(iso2)}`, {
      method: "PUT",
      body,
      headers: { "X-Operator-Id": operatorId },
    }),
};
