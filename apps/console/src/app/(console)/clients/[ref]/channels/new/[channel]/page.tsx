import Link from "next/link";
import { redirect } from "next/navigation";

import { Button, Callout } from "@nexus/ui";

import { connectChoice, metaSignupConfig } from "@/components/channels/connect-choice";
import { PendingSignupLinks } from "@/components/channels/pending-signup-links";
import { f2ChannelCounter, f2VisibleChannels } from "@/components/channels/visible-channels";
import { WhatsAppConnectByAuphere } from "@/components/channels/whatsapp-connect-by-auphere";
import { ConnectWhatsAppStep } from "@/components/channels/wizard/connect-whatsapp-step";
import { wizardPaths } from "@/components/channels/wizard/steps";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { env } from "@/lib/env";
import { requirePartnerPrincipal } from "@/lib/principal";
import { isDesktopShell } from "@/lib/shell";

/**
 * Spec 046, step 2: connect the chosen channel with the flows the console
 * already has (Meta's window, the link to the owner). A channel that cannot
 * start has no step 2: back to the catalog.
 */
export default async function ConnectChannelPage({ params }: { params: Promise<{ ref: string; channel: string }> }) {
  const { ref, channel } = await params;
  const principal = await requirePartnerPrincipal();
  const { t } = await getT(principal.locale);
  const api = backendFor(principal);
  const paths = wizardPaths(ref);

  const [catalog, overview, links] = await Promise.all([
    api.channelCatalog().catch(() => []),
    api.channelsOverview(ref),
    api.whatsappSignupLinks(ref).catch(() => []),
  ]);
  const entry = catalog.find((c) => c.key === channel);
  if (!entry || entry.availability !== "available" || channel !== "whatsapp") redirect(paths.choose);

  const meta = metaSignupConfig(env());
  const choice = connectChoice({ manage: true, meta });
  const linkModes = [
    ...(meta.configIdCoexistence ? (["coexistence"] as const) : []),
    ...(meta.configIdCloudApi ? (["cloud_api"] as const) : []),
  ];
  const connected = f2VisibleChannels(overview.channels).filter((c) => c.status !== "disconnected");
  const firstConnected = connected[0];
  const { n, m } = f2ChannelCounter(overview.channels);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h2 className="text-lg font-semibold text-balance">{t("chw.connect.title", { name: entry.name })}</h2>
        <p className="text-sm text-pretty text-muted-foreground">{t("chw.connect.body")}</p>
      </div>

      {firstConnected ? (
        <Callout
          tone="positive"
          action={
            <Button nativeButton={false} size="sm" render={<Link href={paths.agent(channel, firstConnected.id)} />}>
              {t("chw.connect.next")}
            </Button>
          }
        >
          {t("chw.connect.connected", { count: connected.length })}
          {overview.can_connect ? null : ` ${t("ch.quota.full", { used: n, max: m })}`}
        </Callout>
      ) : null}

      {choice === "by_auphere" ? (
        <WhatsAppConnectByAuphere />
      ) : (
        <ConnectWhatsAppStep
          refId={ref}
          meta={meta}
          linkModes={linkModes}
          canConnect={overview.can_connect}
          used={n}
          max={m}
          hasLiveLink={links.some((l) => l.state === "valid")}
          desktop={await isDesktopShell()}
        />
      )}

      <PendingSignupLinks refId={ref} links={links} manage />

      <div>
        <Button nativeButton={false} variant="ghost" render={<Link href={paths.choose} />}>
          {t("chw.back")}
        </Button>
      </div>
    </div>
  );
}
