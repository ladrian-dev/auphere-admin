import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Auphere",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body className="font-sans text-ink antialiased">{children}</body>
    </html>
  );
}
