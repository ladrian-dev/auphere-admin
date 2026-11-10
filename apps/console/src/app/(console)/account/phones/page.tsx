import { PageHeader } from "@nexus/ui";

import { LitePhonesView } from "@/components/lite/lite-phones-view";
import { getT } from "@/i18n/server";
import { pageTitle } from "@/i18n/metadata";
import { run } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { requireClientAccount } from "@/lib/principal";

import { closePhoneAction } from "./actions";

export const generateMetadata = () => pageTitle("lite.phones.title");

/**
 * Spec 031 (R7.3, R7.5): «Tus teléfonos». The phones where this person is
 * signed in to Auphere Customers, each one closable from here. A failed read
 * shows an error with retry — never an empty list, which would read as «no
 * phone can get in» when one still can.
 */
export default async function PhonesPage() {
  const principal = await requireClientAccount("/account/phones");
  const { t } = await getT(principal.locale);
  const res = await run(() => backendFor(principal).litePhones());
  return (
    <>
      <PageHeader eyebrow={principal.clientName} title={t("lite.phones.title")} description={t("lite.phones.subtitle")} />
      <LitePhonesView
        phones={res.ok ? res.data : null}
        now={new Date().toISOString()}
        closePhone={closePhoneAction}
      />
    </>
  );
}
