import "server-only";

import type { Metadata } from "next";

import { type MessageKey } from "./messages";
import { getT } from "./server";

/**
 * Localised ``<title>`` for a route. Pages used to export a fixed Spanish
 * ``metadata = { title }``, so an English account read "Consumo" in the tab
 * while the page said "Usage". The locale comes from the cookie or
 * Accept-Language (the account locale needs the principal, which metadata
 * does not have); that is the same order ``getLocale`` uses everywhere.
 */
export async function pageTitle(key: MessageKey): Promise<Metadata> {
  const { t } = await getT();
  return { title: t(key) };
}
