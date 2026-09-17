import Link from "next/link";

import { AppShell } from "@/components/layout/AppShell";

export default function NotFound() {
  return (
    <AppShell>
      <div className="py-16 text-center">
        <h1 className="font-display text-3xl font-bold text-ink">Esta página no existe</h1>
        <p className="mt-2 text-ink-muted">Quizá el enlace del QR se copió mal. Puedes empezar el diagnóstico desde el inicio.</p>
        <Link href="/" className="mt-6 inline-flex h-12 items-center rounded-md bg-primary px-5 font-display font-semibold text-primary-contrast">
          Ir al inicio
        </Link>
      </div>
    </AppShell>
  );
}
