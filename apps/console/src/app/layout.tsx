import type { Metadata, Viewport } from "next";
import { Inter_Tight, JetBrains_Mono } from "next/font/google";
import { headers } from "next/headers";

import { ThemeProvider, Toaster } from "@nexus/ui";

import { LocaleProvider } from "@/i18n/client";
import { getLocale } from "@/i18n/server";
import { getSession } from "@/lib/session";

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
    { media: "(prefers-color-scheme: dark)", color: "oklch(0.229 0.036 191.9)" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  // Locale precedence: explicit cookie → account → Accept-Language. The
  // session read is cached by Better Auth's cookie cache.
  const session = await getSession().catch(() => null);
  const locale = await getLocale((session?.user as { locale?: string } | undefined)?.locale);
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  return (
    <html
      lang={locale}
      className={`${interTight.variable} ${jetbrainsMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full">
        <ThemeProvider nonce={nonce}>
          <LocaleProvider locale={locale}>
            {children}
            <Toaster position="top-right" richColors closeButton />
          </LocaleProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
