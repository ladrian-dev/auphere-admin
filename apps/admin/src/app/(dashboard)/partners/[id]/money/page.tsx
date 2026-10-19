import BillingCard from "../_sections/billing-card";
import Receipts from "../_sections/receipts";
import Wallet from "../_sections/wallet";

/** Spec 031: the partner's money — balance and ledger, the card and its charges, then receipts. */
export default function PartnerMoneyPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <div className="grid gap-6">
      <Wallet params={params} />
      {/* Spec 041: the card, automatic charges and the postpaid line. */}
      <BillingCard params={params} />
      <Receipts params={params} />
    </div>
  );
}
