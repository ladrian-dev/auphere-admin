import type { Metadata, Viewport } from "next";
import { Inter, Inter_Tight, Outfit } from "next/font/google";

import { Analytics } from "@/components/layout/Analytics";

import "@/styles/globals.css";

const outfit = Outfit({ subsets: ["latin"], variable: "--font-outfit", display: "swap", weight: ["500", "600", "700"] });
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
const interTight = Inter_Tight({ subsets: ["latin"], variable: "--font-inter-tight", display: "swap", weight: ["600", "700"] });

/** Aplica el tema guardado antes de pintar para evitar el parpadeo. */
/** Modo claro por defecto (no sigue el sistema); solo cambia si la persona lo eligió. */
const themeScript = `(function(){var t="light";try{var s=localStorage.getItem("amacrux-theme");if(s==="dark"||s==="light"){t=s;}}catch(e){}document.documentElement.setAttribute("data-theme",t);})();`;

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3120";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: { default: "Diagnóstico IA · Amacrux", template: "%s · Amacrux" },
  description:
    "Descubre dónde puede aportar más valor la IA en tu empresa. Responde 12 preguntas y recibe recomendaciones prácticas de automatización, IA e integración.",
  applicationName: "Diagnóstico IA Amacrux",
  openGraph: {
    type: "website",
    locale: "es_ES",
    siteName: "Amacrux",
    title: "Diagnóstico IA · Amacrux",
    description: "Recomendaciones prácticas de automatización e IA para tu empresa en 2–4 minutos.",
  },
  twitter: { card: "summary_large_image" },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#01103f" },
    { media: "(prefers-color-scheme: dark)", color: "#050b26" },
  ],
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es" data-theme="light" className={`${outfit.variable} ${inter.variable} ${interTight.variable}`} suppressHydrationWarning>
      <body>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
        {children}
        <Analytics />
      </body>
    </html>
  );
}
