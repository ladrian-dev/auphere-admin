import type { Metadata } from "next";

import { AppShell } from "@/components/layout/AppShell";
import { Wizard } from "@/components/wizard/Wizard";

export const metadata: Metadata = { title: "Diagnóstico", robots: { index: false, follow: true } };

export default function DiagnosticoPage() {
  return (
    <AppShell>
      <Wizard />
    </AppShell>
  );
}
