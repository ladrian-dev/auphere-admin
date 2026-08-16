import { redirect } from "next/navigation";

import { ToolsCatalog } from "@/components/agent-tools/tools-catalog";
import { getT } from "@/i18n/server";
import { BackendError, backendFor } from "@/lib/backend";
import type { ConnectorOut } from "@/lib/backend/agent-tools";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Tools + connectors (CP-13). The catalogue is the page; connectors are a
 * partial state — if they fail to load, the whitelist still renders and the
 * connector strip shows an inline error.
 */
export default async function ToolsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  if (!can(principal.role, "agents:read")) redirect(`/clients/${ref}`);
  const { t } = await getT(principal.locale);
  const api = backendFor(principal);
  const [catalog, connectorsRes] = await Promise.all([
    api.listTools(ref),
    api.listConnectors(ref).then(
      (c) => ({ connectors: c, error: null as string | null }),
      (err: unknown) => {
        if (err instanceof BackendError) return { connectors: [] as ConnectorOut[], error: err.detail };
        throw err;
      },
    ),
  ]);
  return (
    <section className="flex min-w-0 flex-col gap-4" aria-label={t("tools.title")}>
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="text-base font-medium text-balance">{t("tools.title")}</h1>
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("tools.description")}</p>
      </div>
      <ToolsCatalog refId={ref} catalog={catalog} connectors={connectorsRes.connectors} connectorsError={connectorsRes.error} canWrite={can(principal.role, "agents:write")} />
    </section>
  );
}
