import Keys from "../_sections/keys";
import Limits from "../_sections/limits";
import Models from "../_sections/models";
import { requireOperator } from "@/lib/session";

/** Spec 031: how the partner is configured — limits, models, keys and access. */
export default async function PartnerSettingsPage({ params }: { params: Promise<{ id: string }> }) {
  await requireOperator();
  return (
    <div className="grid gap-6">
      <Limits params={params} />
      <Models params={params} />
      <Keys params={params} />
    </div>
  );
}
