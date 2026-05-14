import type { Metadata, Viewport } from "next";
import { Inter_Tight, JetBrains_Mono } from "next/font/google";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";

// Brand-system fallback: Helvena requires licensing; Inter Tight is the
// approved Google Fonts substitute (see Work/Auphere/brand/brand-system.md).
const interTight = Inter_Tight({
  subsets: ["latin"],
  variable: "--font-inter-tight",
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "Nexus · Auphere",
    template: "%s · Nexus",
  },
  description: "Panel interno de operaciones de la agent factory de Auphere.",
  applicationName: "Nexus",
  robots: { index: false, follow: false },
  manifest: "/site.webmanifest",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/favicon-16x16.png", type: "image/png", sizes: "16x16" },
      { url: "/favicon-32x32.png", type: "image/png", sizes: "32x32" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180" }],
  },
};

// Brand-system: surfaces are bone on light / dark-green on dark. The browser
// chrome (mobile address bar, PWA frame) follows the same rule so the panel
// reads as one continuous surface from the OS into the app.
export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F1F7F6" },
    { media: "(prefers-color-scheme: dark)", color: "#032221" },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="es"
      className={`${interTight.variable} ${jetbrainsMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full">
        {children}
        <Toaster position="top-right" richColors closeButton />
      </body>
    </html>
  );
}
