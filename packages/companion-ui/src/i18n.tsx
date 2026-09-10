"use client";

/**
 * Los textos del Companion, con un solo dueño: este paquete. La consola y la
 * aplicación de escritorio montan `CompanionLocaleProvider` con su idioma y,
 * si quieren que un enlace sea navegación de cliente (Next) o una orden a la
 * cáscara (Electron), pasan `renderLink`. Sin él, un `<a>` normal.
 *
 * La regla del §1.4 del contrato no cambia: el backend emite identificadores
 * estables y aquí se pone la palabra. `optionalKey` devuelve `null` para un
 * identificador que no conocemos, y el llamante pinta lo que llegó.
 */
import * as React from "react";

import { type CompanionMessageKey, type Locale, companionMessages, formatMessage } from "./messages";

export type LinkProps = { href: string; className?: string; children: React.ReactNode };
export type RenderLink = (props: LinkProps) => React.ReactNode;

type Ctx = { locale: Locale; renderLink: RenderLink };

const defaultLink: RenderLink = ({ href, className, children }) => (
  <a href={href} className={className}>
    {children}
  </a>
);

const CompanionContext = React.createContext<Ctx>({ locale: "es", renderLink: defaultLink });

export function CompanionLocaleProvider({
  locale,
  renderLink,
  children,
}: {
  locale: Locale;
  renderLink?: RenderLink;
  children: React.ReactNode;
}) {
  const value = React.useMemo(() => ({ locale, renderLink: renderLink ?? defaultLink }), [locale, renderLink]);
  return <CompanionContext.Provider value={value}>{children}</CompanionContext.Provider>;
}

export function useLocale(): Locale {
  return React.useContext(CompanionContext).locale;
}

export function useT() {
  const locale = useLocale();
  return React.useCallback(
    (key: CompanionMessageKey, vars?: Record<string, string | number>) => formatMessage(locale, key, vars),
    [locale],
  );
}

export function useRenderLink(): RenderLink {
  return React.useContext(CompanionContext).renderLink;
}

export function optionalKey(candidate: string): CompanionMessageKey | null {
  return candidate in companionMessages ? (candidate as CompanionMessageKey) : null;
}

export type { CompanionMessageKey as MessageKey };
