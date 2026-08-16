import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Button } from "@nexus/ui";

import { DiagnosticsTable } from "@/components/channels/diagnostics-table";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

/** CP-19: every known failure of the WhatsApp channel as a green/red row + what to do. */
export default async function DiagnosticsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:read")) redirect(`/clients/${ref}`);
  const { t } = await getT(principal.locale);
  const data = await backendFor(principal).channelDiagnostics(ref);
  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <h1 className="text-base font-medium">{t("diag.title")}</h1>
          <p className="max-w-prose text-sm text-muted-foreground">{t("diag.description")}</p>
        </div>
        <Button nativeButton={false} render={<Link href={`/clients/${encodeURIComponent(ref)}/channels`} />} variant="ghost" size="sm">
          <ArrowLeft aria-hidden="true" />
          {t("ch.title")}
        </Button>
      </div>
      <DiagnosticsTable refId={ref} data={data} manage={can(principal.role, "channels:write")} />
    </div>
  );
}
