"use client";

import * as React from "react";

import { type Locale, type MessageKey, t } from "./messages";

const LocaleContext = React.createContext<Locale>("es");

export function LocaleProvider({ locale, children }: { locale: Locale; children: React.ReactNode }) {
  return <LocaleContext.Provider value={locale}>{children}</LocaleContext.Provider>;
}

export function useLocale(): Locale {
  return React.useContext(LocaleContext);
}

export function useT() {
  const locale = useLocale();
  return React.useCallback(
    (key: MessageKey, vars?: Record<string, string | number>) => t(locale, key, vars),
    [locale],
  );
}
