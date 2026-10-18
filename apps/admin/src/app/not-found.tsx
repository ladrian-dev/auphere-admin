import Link from "next/link";

import { BrandLockup, Button } from "@nexus/ui";

export const metadata = { title: "Página no encontrada" };

/**
 * Top-level not-found page. Next falls back to its dark default if
 * this file is absent, which broke the brand on a typo URL. Render the
 * wordmark + a single CTA back to the tenants list — Nexus has no
 * homepage that isn't ``/tenants`` anyway.
 */
export default function NotFound() {
  return (
    <main className="grid min-h-dvh place-items-center bg-background px-6">
      <div className="flex flex-col items-center gap-6 text-center max-w-md">
        <BrandLockup />
        <div className="flex flex-col gap-2">
          <h1
            className="text-3xl font-semibold leading-tight tracking-tight"
          >
            Página no encontrada
          </h1>
          <p className="text-sm text-muted-foreground">
            Esta ruta no existe o se movió. Si llegaste acá desde un link
            interno, contanos en{" "}
            <span className="font-mono text-foreground">#nexus-ops</span> para
            arreglarlo.
          </p>
        </div>
        <Button render={<Link href="/tenants" />}>Volver a Tenants</Button>
      </div>
    </main>
  );
}
