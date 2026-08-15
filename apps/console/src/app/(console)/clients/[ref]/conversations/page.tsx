import { redirect } from "next/navigation";

import { EmptyState, Metric, formatDuration, formatLatency, formatNumber, formatRelative } from "@nexus/ui";

import { ClientStatusBadge } from "@/components/clients/status-badge";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

import { ConversationFilters } from "./filters";

type Search = { escalated?: string; with_errors?: string; page?: string };

export default async function ConversationsPage({ params, searchParams }: { params: Promise<{ ref: string }>; searchParams: Promise<Search> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  if (!can(principal.role, "conversations:read")) redirect(`/clients/${ref}`);
  const { t, locale } = await getT(principal.locale);
  const sp = await searchParams;
  const limit = 50;
  const page = Math.max(1, Number(sp.page ?? 1) || 1);
  const api = backendFor(principal);
  const [data, stats] = await Promise.all([
    api.listConversations(ref, {
      escalated: sp.escalated === "true" ? true : undefined,
      with_errors: sp.with_errors === "true" ? true : undefined,
      limit,
      offset: (page - 1) * limit,
    }),
    api.conversationStats(ref, 30).catch(() => null),
  ]);
  return (
    <section className="flex min-w-0 flex-col gap-4" aria-label={t("conv.title")}>
      <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("conv.description")}</p>
      {stats ? (
        <div className="grid gap-4 md:grid-cols-4">
          <Metric label={t("conv.stats.total")} value={formatNumber(stats.conversations, locale)} />
          <Metric label={t("conv.stats.escalated")} value={formatNumber(stats.escalated, locale)} />
          <Metric label={t("conv.stats.failed")} value={formatNumber(stats.failed_messages, locale)} />
          <Metric label={t("conv.latency")} value={formatLatency(stats.avg_latency_ms, locale)} />
        </div>
      ) : null}
      <ConversationFilters escalated={sp.escalated === "true"} withErrors={sp.with_errors === "true"} />
      {data.total === 0 ? (
        <EmptyState title={t("conv.empty")} description={t("conv.privacy")} readonly />
      ) : (
        <div className="min-w-0 overflow-x-auto rounded-md ring-1 ring-foreground/10">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="h-10 px-2 font-medium">{t("common.status")}</th>
                <th className="h-10 px-2 font-medium">{t("conv.channel")}</th>
                <th className="h-10 px-2 text-right font-medium">{t("conv.turns")}</th>
                <th className="h-10 px-2 text-right font-medium">{t("conv.failed")}</th>
                <th className="h-10 px-2 text-right font-medium">{t("conv.latency")}</th>
                <th className="h-10 px-2 text-right font-medium">{t("conv.duration")}</th>
                <th className="h-10 px-2 font-medium">{t("conv.last")}</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((c) => (
                <tr key={c.id} className="border-b last:border-0">
                  <td className="p-2">
                    <ClientStatusBadge status={c.status} locale={locale} />
                  </td>
                  <td className="p-2 capitalize">{c.channel_type ?? "—"}</td>
                  <td className="p-2 text-right tabular-nums">{formatNumber(c.turns, locale)}</td>
                  <td className="p-2 text-right tabular-nums">{c.failed_messages ? formatNumber(c.failed_messages, locale) : "—"}</td>
                  <td className="p-2 text-right tabular-nums">{formatLatency(c.avg_latency_ms, locale)}</td>
                  <td className="p-2 text-right tabular-nums">{formatDuration(c.duration_seconds, locale)}</td>
                  <td className="p-2 tabular-nums">{formatRelative(c.last_activity_at, locale)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-muted-foreground">{t("conv.privacy")}</p>
    </section>
  );
}
