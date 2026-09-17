import Script from "next/script";

import { analyticsProvider, plausibleDomain } from "@/lib/env";

/** Carga el script de Plausible solo si está configurado. Sin proveedor no se carga nada. */
export function Analytics() {
  if (analyticsProvider() !== "plausible") return null;
  const domain = plausibleDomain();
  if (!domain) return null;
  return <Script defer data-domain={domain} src="https://plausible.io/js/script.manual.js" strategy="afterInteractive" />;
}
