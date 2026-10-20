import { StyleSheet, View } from "react-native";

import type { Spend, UsageSummary } from "@/api/endpoints";
import type { Locale, T } from "@/i18n/t";
import { formatMoney, formatNumber, shortDay } from "@/lib/format";
import { creditRunway } from "@/lib/panel-model";
import { Divider, Meter, Segmented } from "@/ui/bits";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { icons } from "@/ui/icon";
import { ErrorState, PartialNotice } from "@/ui/states";
import { Text } from "@/ui/text";

import { DayBars } from "../charts/day-bars";
import { Metric } from "../home/metric";

export const PERIODS = [7, 30, 90] as const;
export type Period = (typeof PERIODS)[number];

/**
 * Consumo (spec 031, R4.2–R4.5): read-only. The balance and how long it lasts,
 * the month's spend and its projection, spend per day and per agent — the same
 * cents as the console (R4.3). No buy, no top-up, no link to one (R4.4); the
 * technical detail and its export stay on the web (R4.5).
 */
export function UsageView({
  summary,
  spend,
  spendFailed,
  days,
  onDays,
  agents,
  agent,
  onAgent,
  t,
  locale,
  now = new Date(),
  onRetry,
  onWeb,
}: {
  summary: UsageSummary | null;
  spend: Spend | null;
  spendFailed: boolean;
  days: Period;
  onDays: (d: Period) => void;
  agents: { id: string; name: string }[];
  agent: string | null;
  onAgent: () => void;
  t: T;
  locale: Locale;
  now?: Date;
  onRetry: () => void;
  onWeb: () => void;
}) {
  const n = (v: number) => formatNumber(v, locale);
  const money = (c: number) => formatMoney(c, locale);
  if (summary === null) return <ErrorState body={t("common.error.backend")} onRetry={onRetry} />;

  const balance = summary.balance ?? null;
  const month = summary.month ?? null;
  const runway = balance?.assigned ? creditRunway(balance.remaining_cents ?? null, balance.days_left ?? null, now) : null;
  const out = balance?.assigned === true && (balance.remaining_cents ?? 0) <= 0;
  const byAgent = summary.by_agent && summary.by_agent.length > 1 ? summary.by_agent : null;
  const agentName = agent ? agents.find((a) => a.id === agent)?.name ?? null : null;
  const every = days === 7 ? 1 : days === 30 ? 5 : 15;

  return (
    <View style={styles.stack}>
      <Text variant="callout" tone="mutedForeground">
        {byAgent ? t("lite.usage.intro.agents") : t("lite.usage.intro")}
      </Text>
      {summary.errors.length > 0 ? <PartialNotice text={t("lite.usage.partial")} /> : null}
      <View style={styles.grid} accessibilityLabel={t("lite.usage.cards")}>
        <Metric
          icon={icons.wallet}
          label={t("lite.kpi.balance")}
          value={balance?.assigned && balance.remaining_cents != null ? money(balance.remaining_cents) : "—"}
          tone={out ? "danger" : undefined}
          hint={
            balance === null
              ? t("lite.usage.unreadable")
              : !balance.assigned
                ? t("lite.kpi.balance.unassigned")
                : out
                  ? t("lite.kpi.balance.out")
                  : runway
                    ? t("lite.usage.balance.runway", { days: n(runway.days) })
                    : t("lite.kpi.balance.noSpend")
          }
        >
          {runway ? <Meter value={runway.days} max={runway.monthLeft} tone={runway.tone} label={t("lite.kpi.balance.runway.aria")} /> : null}
        </Metric>
        <Metric
          icon={icons.money}
          label={t("lite.spend.title")}
          value={month ? money(month.spent_cents) : "—"}
          hint={
            month === null
              ? t("lite.usage.unreadable")
              : month.projection_cents != null && month.spent_cents > 0
                ? t("lite.usage.month.projection", { amount: money(month.projection_cents) })
                : t("lite.usage.month.none")
          }
        />
        <Metric
          icon={icons.chat}
          label={t("lite.usage.conversations")}
          value={month?.conversations != null ? n(month.conversations) : "—"}
          hint={
            month?.avg_per_conversation_cents != null
              ? t("lite.usage.conversations.avg", { amount: money(month.avg_per_conversation_cents) })
              : month === null
                ? t("lite.usage.unreadable")
                : undefined
          }
        />
      </View>

      <Card>
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
          {t("hu.usage.spend.title")}
        </Text>
        <Segmented
          label={t("app.usage.days")}
          value={days}
          onChange={onDays}
          options={PERIODS.map((d) => ({ value: d, label: t("app.usage.days.n", { days: d }) }))}
        />
        {agents.length > 1 ? (
          <Button
            label={agentName ? t("app.inbox.agentFilter.value", { name: agentName }) : t("lite.usage.agent.all")}
            variant="secondary"
            compact
            icon={icons.bot}
            onPress={onAgent}
            accessibilityHint={t("lite.usage.agent")}
          />
        ) : null}
        {spend ? (
          spend.series_cents.some((c) => c > 0) ? (
            <DayBars
              values={spend.series_cents}
              labels={spend.days.map((d) => shortDay(d, locale))}
              every={every}
              summary={`${t("hu.usage.spend.aria")}: ${spend.days
                .map((d, i) => t("hu.usage.spend.bar", { day: shortDay(d, locale), amount: money(spend.series_cents[i] ?? 0) }))
                .join(", ")}`}
            />
          ) : (
            <Text variant="callout" tone="mutedForeground">
              {t("hu.usage.spend.empty")}
            </Text>
          )
        ) : spendFailed ? (
          <Text variant="callout" tone="mutedForeground">
            {t("lite.usage.unreadable")}
          </Text>
        ) : null}
      </Card>

      {byAgent ? (
        <Card>
          <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
            {t("lite.usage.byAgent.title")}
          </Text>
          {byAgent.map((a, i) => (
            <View
              key={a.agent_id}
              style={styles.agent}
              accessible
              accessibilityLabel={`${a.name}: ${money(a.spent_cents)}, ${n(a.share_pct)} %, ${n(a.conversations)} ${t("lite.usage.conversations")}`}
            >
              {i > 0 ? <Divider /> : null}
              <View style={styles.agentRow}>
                <Text variant="bodyStrong" style={styles.flex}>
                  {a.name}
                </Text>
                <Text variant="bodyStrong" style={styles.num}>
                  {money(a.spent_cents)}
                </Text>
              </View>
              <Meter value={a.share_pct} max={100} tone="positive" label={t("lite.usage.byAgent.share")} />
              <Text variant="footnote" tone="mutedForeground">
                {`${n(a.share_pct)} % · ${n(a.conversations)} ${t("lite.usage.conversations").toLowerCase()}`}
              </Text>
            </View>
          ))}
        </Card>
      ) : null}

      <Button label={t("app.usage.web")} variant="ghost" icon={icons.external} onPress={onWeb} />
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 16 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  agent: { gap: 6 },
  agentRow: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  flex: { flex: 1, minWidth: 0 },
  num: { fontVariant: ["tabular-nums"] },
});
