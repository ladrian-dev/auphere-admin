import ClientLinks from "../_sections/client-links";
import ClientUsage from "../_sections/client-usage";

/** Spec 031 (R4.5): the partner's clients — usage first, then the mappings. */
export default function PartnerClientsPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <div className="grid gap-6">
      <ClientUsage params={params} />
      <ClientLinks params={params} />
    </div>
  );
}
