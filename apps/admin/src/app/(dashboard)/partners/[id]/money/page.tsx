import BillingCard from "../_sections/billing-card";
import PartnerPayments from "../_sections/partner-payments";
import Receipts from "../_sections/receipts";
import Wallet from "../_sections/wallet";

/** Spec 031: the partner's money — balance and ledger, the card and its charges, then receipts. */
export default async function PartnerMoneyPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ invoice?: string }>;
}) {
  // Back from «Ver factura» without an invoice to show.
  const invoiceMissing = (await searchParams).invoice === "missing";
  return (
    <div className="grid gap-6">
      <Wallet params={params} />
      {/* Spec 041: the card, automatic charges and the postpaid line. */}
      <BillingCard params={params} invoiceMissing={invoiceMissing} />
      {/* Owner, 2026-10-20: the partner pays Auphere; its payments live here and credit its balance. */}
      <PartnerPayments params={params} />
      <Receipts params={params} />
    </div>
  );
}
