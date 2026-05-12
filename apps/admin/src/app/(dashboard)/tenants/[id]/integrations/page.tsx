import { redirect } from "next/navigation";

/**
 * Block L migration — ``/tenants/[id]/integrations`` was split into the
 * unified ``/connectors`` view per ADR-011. This page stays as a redirect
 * shim for one release so any bookmarked URL keeps working.
 *
 * Phase 2: delete the route. The original ``actions.ts``,
 * ``agendapro-actions.tsx`` and ``whatsapp-actions.tsx`` are still
 * imported by tests; they stay until the connectors page replicates
 * every operator action they exposed.
 */
export default async function IntegrationsRedirect({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  redirect(`/tenants/${id}/connectors`);
}
