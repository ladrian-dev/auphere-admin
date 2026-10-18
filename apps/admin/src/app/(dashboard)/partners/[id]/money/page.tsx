import Receipts from "../_sections/receipts";
import Wallet from "../_sections/wallet";

/** Spec 031: the partner's money — balance and ledger, then receipts. */
export default function PartnerMoneyPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <div className="grid gap-6">
      <Wallet params={params} />
      <Receipts params={params} />
    </div>
  );
}
