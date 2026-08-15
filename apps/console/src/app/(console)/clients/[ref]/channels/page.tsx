import { redirect } from "next/navigation";

import { EmptyState, StatusBadge, formatDateTime } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

const TONE = { active: "positive", paused: "warning", degraded: "warning", disconnected: "danger" } as const;

export default async function ChannelsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:read")) redirect(`/clients/${ref}`);
  const { t, locale } = await getT(principal.locale);
  const channels = await backendFor(principal).listChannels(ref);
  if (channels.length === 0) return <EmptyState title={t("clients.channels.empty")} readonly />;
  return (
    <ul className="grid gap-3 md:grid-cols-2" aria-label={t("clients.tabs.channels")}>
      {channels.map((ch) => (
        <li key={ch.id} className="flex min-w-0 flex-col gap-2 rounded-md bg-card p-4 ring-1 ring-foreground/10">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium capitalize">{ch.type}</span>
            <StatusBadge tone={TONE[ch.status as keyof typeof TONE] ?? "muted"}>{t(`status.${ch.status}` as "status.active")}</StatusBadge>
          </div>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
            <dt className="text-muted-foreground">{t("clients.channels.number")}</dt>
            <dd className="min-w-0 truncate font-mono" title={ch.provider_identifier}>
              {ch.provider_identifier}
            </dd>
            <dt className="text-muted-foreground">{t("clients.channels.role")}</dt>
            <dd className="font-mono">{ch.role ?? "—"}</dd>
            <dt className="text-muted-foreground">{t("common.created")}</dt>
            <dd className="tabular-nums">{formatDateTime(ch.created_at, locale)}</dd>
          </dl>
        </li>
      ))}
    </ul>
  );
}
