import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import type { ClientPrincipal } from "@/lib/principal";

import { LiteUsageView } from "./lite-usage-view";

type Search = { days?: string; agent?: string };

const PERIODS = new Set([7, 30, 90]);

/**
 * Spec 030 (US4): the Consumo of one client. Each read degrades on its own.
 * `?agent=` narrows the spend chart to one agent — only for a client with
 * more than one, and only to one of theirs (anything else is ignored).
 */
export async function LiteUsage({ principal, searchParams }: { principal: ClientPrincipal; searchParams: Search }) {
  const { t, locale } = await getT(principal.locale);
  const requested = Number(searchParams.days ?? 30);
  const days = PERIODS.has(requested) ? requested : 30;
  const api = backendFor(principal);
  const agents = await api
    .liteMe()
    .then((me) => (me.agents.length > 1 ? me.agents : []))
    .catch(() => []);
  const agent = agents.some((a) => a.id === searchParams.agent) ? searchParams.agent : undefined;
  const [summary, spend, detail] = await Promise.all([
    api.liteUsageSummary().catch(() => null),
    api.liteUsageSpend(days, agent).catch(() => null),
    api.liteUsageDetail(days).catch(() => null),
  ]);
  return (
    <LiteUsageView
      clientName={principal.clientName}
      summary={summary}
      spend={spend}
      detail={detail}
      days={days}
      agent={agent ?? ""}
      agents={agents}
      t={t}
      locale={locale}
    />
  );
}
