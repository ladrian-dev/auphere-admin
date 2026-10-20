import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";

import { ThemeProvider, Toaster, UiCopyProvider } from "@nexus/ui";

import "./globals.css";

// Spec 031: the same family as the console (owner, 2026-09-26). The tokens
// read `--font-inter` for sans, display and mono; nothing else is loaded.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });

export const metadata: Metadata = {
  title: {
    // The product is Auphere; «Nexus» is the codebase's name, not the team's.
    default: "Admin · Auphere",
    template: "%s · Admin Auphere",
  },
  description: "Panel interno de operaciones de la agent factory de Auphere.",
  applicationName: "Auphere Admin",
  robots: { index: false, follow: false },
  manifest: "/site.webmanifest",
  icons: {
    // The mark on Auphere's dark green, edge to edge (no rounded corners: they
    // read as white on a light tab bar). SVG where supported, PNG/ICO elsewhere.
    // The 16/32 px files draw the strokes thicker so the mark reads that small.
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/favicon.ico", sizes: "any" },
      { url: "/favicon-16x16.png", type: "image/png", sizes: "16x16" },
      { url: "/favicon-32x32.png", type: "image/png", sizes: "32x32" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
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

// The design system's own words, in Spanish: the panel is Spanish-only.
const UI_COPY = {
  confirm: "Confirmar",
  cancel: "Cancelar",
  close: "Cerrar",
  more: "Más",
  loading: "Cargando",
  retry: "Reintentar",
  nothingHere: "Todavía no hay nada aquí",
  toggleSidebar: "Mostrar u ocultar el menú",
  typeToConfirm: "Escribe {word} para confirmar",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" className={`${inter.variable} h-full antialiased`} suppressHydrationWarning>
      <body className="min-h-full">
        <ThemeProvider>
          <UiCopyProvider copy={UI_COPY}>
            {children}
            <Toaster position="top-right" richColors closeButton />
          </UiCopyProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
