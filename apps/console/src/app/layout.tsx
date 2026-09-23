import type { Metadata, Viewport } from "next";
import { Inter_Tight, JetBrains_Mono } from "next/font/google";
import { headers } from "next/headers";

import { ThemeProvider, Toaster, UiCopyProvider } from "@nexus/ui";

import { LocaleProvider } from "@/i18n/client";
import { t } from "@/i18n/messages";
import { getLocale } from "@/i18n/server";
import { resolvePrincipal } from "@/lib/principal";

import "./globals.css";

const interTight = Inter_Tight({ subsets: ["latin"], variable: "--font-inter-tight", display: "swap" });
const jetbrainsMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains-mono", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Consola · Auphere", template: "%s · Consola Auphere" },
  description: "Consola de partners de Auphere.",
  applicationName: "Auphere Console",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = {
  // The <meta name="theme-color"> tag cannot reference a CSS variable; these
  // are --color-anti-flash and --color-dark-green from @nexus/ui tokens.
  themeColor: [
    // eslint-disable-next-line nexus-ui/no-raw-colors
    { media: "(prefers-color-scheme: light)", color: "oklch(0.971 0.006 185.3)" },
    // eslint-disable-next-line nexus-ui/no-raw-colors
    { media: "(prefers-color-scheme: dark)", color: "oklch(0.185 0.012 170)" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Locale precedence: explicit cookie → account → Accept-Language. The
  // principal read is one API call, memoised per request by React.cache,
  // and shared with every page that calls requirePrincipal().
  const resolution = await resolvePrincipal().catch(() => null);
  const locale = await getLocale(resolution?.kind === "ok" ? resolution.principal.locale : undefined);
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  // The design system's own words (Cancel, Close, Retry…) in the reader's
  // language. One object here instead of a label at every call site.
  const uiCopy = {
    confirm: t(locale, "ui.confirm"),
    cancel: t(locale, "ui.cancel"),
    close: t(locale, "ui.close"),
    more: t(locale, "ui.more"),
    loading: t(locale, "ui.loading"),
    retry: t(locale, "ui.retry"),
    nothingHere: t(locale, "ui.nothingHere"),
    toggleSidebar: t(locale, "ui.toggleSidebar"),
    typeToConfirm: t(locale, "ui.typeToConfirm"),
  };
  return (
    <html
      lang={locale}
      className={`${interTight.variable} ${jetbrainsMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full">
        <ThemeProvider nonce={nonce}>
          <UiCopyProvider copy={uiCopy}>
          <LocaleProvider locale={locale}>
            {children}
            <Toaster position="top-right" richColors closeButton />
          </LocaleProvider>
          </UiCopyProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
