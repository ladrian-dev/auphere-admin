"use server";

import { revalidatePath } from "next/cache";

import { toFailure, type Result } from "@/lib/action-result";
import { loginBetaBackend, type LoginBetaCountry } from "@/lib/backend-whatsapp-beta";
import { requireOperator } from "@/lib/session";

import { ERRORS } from "./countries";

/**
 * Spec 047 (T117, 31.5, 54.7): turn the beta on or off in a country, with who
 * and why. The API refuses the EU and the EEA (`eu_country_not_allowed`).
 */
export async function setLoginBetaCountryAction(
  country: string,
  body: { enabled: boolean; reason: string },
): Promise<Result<LoginBetaCountry[]>> {
  const operator = await requireOperator();
  try {
    const data = await loginBetaBackend.setCountry(country, body, operator.id);
    revalidatePath("/channels/whatsapp-login");
    return { ok: true, data: data ?? [] };
  } catch (err) {
    return toFailure(err, ERRORS);
  }
}
