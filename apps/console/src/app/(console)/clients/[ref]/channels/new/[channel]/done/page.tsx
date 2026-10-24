import { CircleAlert, PartyPopper } from "lucide-react";
import Link from "next/link";

import { Button, Callout, cn } from "@nexus/ui";

import { missingItems } from "@/components/clients/health";
import { wizardPaths } from "@/components/channels/wizard/steps";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { getClientCached } from "../../../../data";

/**
 * Spec 046, step 4. «¡Listo!» only says «ya responde» when it does
 * (constitution §V): with anything still missing it names it, with its fix,
 * and a short audience says who it answers. Then the one test that proves
 * it — writing to the number from your own phone.
 */
export default async function ChannelDonePage({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string; channel: string }>;
  searchParams: Promise<{ channel?: string; role?: string }>;
}) {
  const { ref } = await params;
  const { channel: channelId, role } = await searchParams;
  const principal = await requirePartnerPrincipal();
  const { t } = await getT(principal.locale);
  const paths = wizardPaths(ref);
  const base = `/clients/${encodeURIComponent(ref)}`;

  const [client, overview] = await Promise.all([
    getClientCached(principal, ref).catch(() => null),
    backendFor(principal)
      .channelsOverview(ref)
      .catch(() => null),
  ]);
  const number = overview?.channels.find((c) => c.id === channelId) ?? null;
  const phone = number?.provider_identifier ?? client?.health.display_phone_number ?? null;
  const notices = role === "notifications";
  const missing = client ? missingItems(client.health, ref) : [];
  const ready = !!client && missing.length === 0;
  const audience = client?.audience?.mode === "list" ? client.audience.count : null;

  return (
    <div className="mx-auto flex max-w-xl flex-col items-center gap-5 py-8 text-center">
      <span
        className={cn(
          "grid size-14 place-items-center rounded-full",
          ready || notices ? "bg-primary/15 text-primary-text" : "bg-status-warning-bg text-status-warning-text",
        )}
      >
        {ready || notices ? <PartyPopper className="size-7" aria-hidden="true" /> : <CircleAlert className="size-7" aria-hidden="true" />}
      </span>
      <h2 className="text-xl font-semibold text-balance">{t("chw.done.title", { client: client?.name ?? ref })}</h2>

      {notices ? (
        <p className="text-sm text-pretty text-muted-foreground">{t("chw.done.notifications")}</p>
      ) : ready ? (
        <p className="text-base text-pretty">{phone ? t("chw.done.ready", { phone }) : t("chw.done.readyNoPhone")}</p>
      ) : (
        <div className="flex w-full flex-col gap-3 text-left">
          <p className="text-sm text-pretty">{t("chw.done.notReady")}</p>
          <ul className="flex flex-col gap-2">
            {missing.map((m) => (
              <li key={m.key} className="flex flex-wrap items-center justify-between gap-2 rounded-md p-3 ring-1 ring-foreground/10">
                <span className="text-sm font-medium first-letter:uppercase">{t(m.label)}</span>
                {can(principal.role, m.permission) ? (
                  <Button nativeButton={false} size="sm" variant="outline" render={<Link href={m.href ?? base} />}>
                    {t(m.fix)}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      )}

      {!notices && audience !== null ? (
        <Callout
          tone="warning"
          className="w-full text-left"
          action={
            can(principal.role, "agents:write") ? (
              <Button nativeButton={false} size="sm" variant="outline" render={<Link href={`${base}/agent/settings`} />}>
                {t("chw.done.audience.action")}
              </Button>
            ) : null
          }
        >
          {t("chw.done.audience", { count: audience })}
        </Callout>
      ) : null}

      <div className="flex flex-wrap justify-center gap-2 pt-2">
        <Button nativeButton={false} variant="outline" render={<Link href={paths.channels} />}>
          {t("chw.done.channels")}
        </Button>
        {ready && !notices ? (
          <Button nativeButton={false} variant="outline" render={<Link href={`${paths.channels}/diagnostics`} />}>
            {t("chw.done.test")}
          </Button>
        ) : null}
        <Button nativeButton={false} render={<Link href={base} />}>
          {t("chw.done.toClient")}
        </Button>
      </div>
    </div>
  );
}
