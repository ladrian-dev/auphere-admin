import { ErrorState } from "@nexus/ui";

import { ChannelTile } from "@/components/channels/wizard/channel-tile";
import { wizardPaths } from "@/components/channels/wizard/steps";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { requirePartnerPrincipal } from "@/lib/principal";

/** Spec 046, step 1: the catalog of channels, each with its state. */
export default async function ChooseChannelPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal();
  const { t } = await getT(principal.locale);
  const catalog = await backendFor(principal)
    .channelCatalog()
    .catch(() => null);
  const paths = wizardPaths(ref);
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold text-balance">{t("chw.choose.title")}</h2>
        <p className="text-sm text-pretty text-muted-foreground">{t("chw.choose.body")}</p>
      </div>
      {catalog === null ? (
        <ErrorState title={t("chw.choose.error.title")} description={t("chw.choose.error.body")} />
      ) : (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 2xl:grid-cols-3">
          {catalog.map((entry) => (
            <li key={entry.key}>
              <ChannelTile entry={entry} href={paths.connect(entry.key)} t={t} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
