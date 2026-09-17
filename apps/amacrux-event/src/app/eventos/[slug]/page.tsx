import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { AppShell } from "@/components/layout/AppShell";
import { Welcome } from "@/components/welcome/Welcome";
import { CampaignSchema } from "@/domain/validation";

export const metadata: Metadata = { title: "Diagnóstico IA en el evento" };

export default async function EventPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const parsed = CampaignSchema.safeParse(slug.toLowerCase());
  if (!parsed.success) notFound();
  return (
    <AppShell tone="dark" themeToggle={false} sticker={false}>
      <Welcome slug={parsed.data} />
    </AppShell>
  );
}
