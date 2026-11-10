import { useLocales } from "expo-localization";
import { useCallback } from "react";

import { appEn } from "./app.en";
import { appEs, type AppKey } from "./app.es";
import { liteMessages } from "./lite.gen";

/**
 * The console's `t(locale, key, vars)`, on the phone (spec 031, D16): one
 * function, two sources — the Consola Lite's words generated from the
 * console, and the app's own. `{name}` placeholders, never concatenation.
 */
export type Locale = "es" | "en";
export type LiteKey = keyof typeof liteMessages;
export type MessageKey = LiteKey | AppKey;
export type Vars = Record<string, string | number>;
export type T = (key: MessageKey, vars?: Vars) => string;

function fill(text: string, vars?: Vars): string {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (all, name: string) => (name in vars ? String(vars[name]) : all));
}

export function t(locale: Locale, key: MessageKey, vars?: Vars): string {
  if (key in liteMessages) return fill(liteMessages[key as LiteKey][locale], vars);
  const own = locale === "en" ? appEn : appEs;
  return fill(own[key as AppKey], vars);
}

/** The phone's language: English when it says so, Spanish otherwise (the console's default). */
export function localeOf(languageCode: string | null | undefined): Locale {
  return languageCode === "en" ? "en" : "es";
}

/** Follows the phone's language, re-read when it changes (R14.6). */
export function useLocale(): Locale {
  const locales = useLocales();
  return localeOf(locales[0]?.languageCode);
}

export function useT(): T {
  const locale = useLocale();
  return useCallback((key: MessageKey, vars?: Vars) => t(locale, key, vars), [locale]);
}
