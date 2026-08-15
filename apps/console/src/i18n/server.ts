import "server-only";

import { cookies, headers } from "next/headers";

import { type Locale, type MessageKey, t } from "./messages";

export const LOCALE_COOKIE = "nexus-console.locale";

/** Cookie wins (explicit choice), then the account, then Accept-Language. */
export async function getLocale(accountLocale?: string | null): Promise<Locale> {
  const jar = await cookies();
  const fromCookie = jar.get(LOCALE_COOKIE)?.value;
  if (fromCookie === "es" || fromCookie === "en") return fromCookie;
  if (accountLocale === "en" || accountLocale === "es") return accountLocale;
  const accept = (await headers()).get("accept-language") ?? "";
  return accept.toLowerCase().startsWith("en") ? "en" : "es";
}

export async function getT(accountLocale?: string | null) {
  const locale = await getLocale(accountLocale);
  return { locale, t: (key: MessageKey, vars?: Record<string, string | number>) => t(locale, key, vars) };
}
