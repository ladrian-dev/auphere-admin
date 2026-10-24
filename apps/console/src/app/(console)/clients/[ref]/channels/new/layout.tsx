import { redirect } from "next/navigation";

import { WizardSteps } from "@/components/channels/wizard/wizard-steps";
import { can, requirePartnerPrincipal } from "@/lib/principal";

/**
 * Spec 046: the «Añadir canal» wizard, the same four steps as the operator
 * panel's (spec 035). Wide screens get the rail of steps on the left;
 * narrower ones a single row on top. Only who can connect a channel enters.
 */
export default async function NewChannelLayout({ params, children }: { params: Promise<{ ref: string }>; children: React.ReactNode }) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal();
  if (!can(principal.role, "channels:write")) redirect(`/clients/${encodeURIComponent(ref)}/channels`);
  return (
    <div className="grid min-w-0 overflow-hidden rounded-md ring-1 ring-foreground/10 xl:grid-cols-[16rem_minmax(0,1fr)]">
      <aside className="hidden border-r border-border bg-muted/20 p-6 xl:block">
        <WizardSteps />
      </aside>
      <div className="border-b border-border px-5 py-4 xl:hidden">
        <WizardSteps compact />
      </div>
      <div className="min-w-0 p-5 sm:p-6">{children}</div>
    </div>
  );
}
