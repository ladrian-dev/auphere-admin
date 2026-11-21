import { StyleSheet, View } from "react-native";
import Animated from "react-native-reanimated";

import type { Me, Spend, UsageSummary } from "@/api/endpoints";
import type { Locale, T } from "@/i18n/t";
import { formatMoney, formatNumber, shortDay } from "@/lib/format";
import { creditRunway, localToday, untilDay } from "@/lib/panel-model";
import { runsOutOn } from "@/lib/reservas-model";
import { haptics } from "@/motion/haptics";
import { contentFade } from "@/motion/micro";
import { Divider, Meter, RowButton, Segmented } from "@/ui/bits";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Group, Row } from "@/ui/group";
import { Icon, icons } from "@/ui/icon";
import { ErrorState, PartialNotice } from "@/ui/states";
import { Text } from "@/ui/text";

import { SpendBars, weekly, type Bar } from "../charts/day-bars";
import { lasting, lastingText } from "../home/model";
import { CountUpMoney } from "./count-up";

export const PERIODS = [7, 30, 90] as const;
export type Period = (typeof PERIODS)[number];

/**
 * Consumo (spec 031, R4.2–R4.5; spec 042, R9; spec 044, R13; spec 069, R18):
 * read-only, the client's own money in its bag's currency.
 *
 * - The balance card: the figure that runs to its value (micro 4), the day it
 *   runs out («Te alcanza hasta el sábado 17», 044 R13.1) and for how long at
 *   the 7-day pace («para unos N días / meses», 069 R18.1). With no spend, no
 *   balance assigned or nothing left it says that instead and invents no date.
 * - Whom to ask for more is a sentence — «Pídeselo a {partner}» — never a
 *   button nor a link (R18.2; 3.1.3(f) of Apple's guide). The bag's own
 *   warning (047, 50.6) says it once, above.
 * - The month's spend with its projection and the month's conversations with
 *   the average, as rows of one group.
 * - The spend of 7, 30 or 90 days as bars (90 as 13 weeks), the period's
 *   total running to its value; offered only when the widest series has
 *   something in it (042 R9.2). By agent, with its filter.
 * - The technical detail and its export stay on the web (R4.5), behind one row
 *   that says it leaves the app (R20: «Ver en la web»).
 */
export function UsageView({
  summary,
  spend,
  spendFailed,
  anySpend,
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
  contact = null,
}: {
  summary: UsageSummary | null;
  /** The series for `days`. */
  spend: Spend | null;
  spendFailed: boolean;
  /** Whether the 90-day series has any spend: `null` while unknown. */
  anySpend: boolean | null;
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
  /** Who manages the balance (`/me.balance_contact`): whom to talk to for more (R13.1). */
  contact?: Me["balance_contact"] | null;
}) {
  const n = (v: number) => formatNumber(v, locale);
  if (summary === null) return <ErrorState body={t("common.error.backend")} onRetry={onRetry} />;

  const balance = summary.balance ?? null;
  // Spec 047: the bag in its own currency; the spend in the report's (both the bag's unless a partner changes it).
  const bagMoney = (c: number) => formatMoney(c, locale, balance?.currency ?? "USD");
  const money = (c: number) => formatMoney(c, locale, spend?.currency ?? summary.month?.currency ?? balance?.currency ?? "USD");
  const month = summary.month ?? null;
  const out = balance?.assigned === true && (balance.remaining_cents ?? 0) <= 0;
  const runway = balance?.assigned ? creditRunway(balance.remaining_cents ?? null, balance.days_left ?? null, now) : null;
  const byAgent = summary.by_agent && summary.by_agent.length > 1 ? summary.by_agent : null;
  const agentName = agent ? agents.find((a) => a.id === agent)?.name ?? null : null;
  const periodCents = spend ? spend.series_cents.reduce((a, b) => a + b, 0) : null;
  const today = localToday(now);
  const apiDate = balance?.runs_out_on ?? null;
  const lastsUntil = balance?.assigned && !out ? (apiDate ?? (balance.days_left != null ? runsOutOn(balance.days_left, today) : null)) : null;
  // Spec 047 (50.6, `events.md` §1.4): «Queda poco», «No llega a fin de mes» or «Agotada», and whom to ask — no button.
  const bag = summary.bag_state === "low" || summary.bag_state === "not_enough" || summary.bag_state === "empty" ? summary.bag_state : null;
  const partner = summary.partner_name || contact?.name || null;
  const pace =
    balance?.assigned && !out && balance.days_left != null
      ? lastingText(
          lasting(balance.days_left),
          { months: "v13.usage.lasts.months", days: "v13.usage.lasts.days", day: "v13.usage.lasts.day", lessThanDay: "v13.usage.lasts.lessThanDay" },
          t,
          n,
        )
      : null;
  const hint =
    balance === null
      ? t("lite.usage.unreadable")
      : !balance.assigned
        ? t("lite.kpi.balance.unassigned")
        : out
          ? t("lite.kpi.balance.out")
          : runway
            ? null
            : t("lite.kpi.balance.noSpend");
  const balanceText = balance?.assigned && balance.remaining_cents != null ? bagMoney(balance.remaining_cents) : "—";

  return (
    <View style={styles.stack}>
      {summary.errors.length > 0 ? <PartialNotice text={t("lite.usage.partial")} /> : null}
      {bag ? (
        <Card tone={bag === "empty" ? "danger" : "warning"} testID="usage-bag">
          <View style={styles.row} accessible accessibilityRole="alert">
            <Icon name={icons.warning} size={18} tone={bag === "empty" ? "dangerText" : "warningText"} />
            <Text variant="headline" style={styles.flex}>
              {t(`consumo.bag.${bag}`)}
            </Text>
          </View>
          <Text variant="callout">
            {bag === "empty" ? t("panel.bag.empty") : summary.days_left != null ? t("panel.bag.days", { days: n(summary.days_left) }) : t("panel.bag.noEstimate")}
          </Text>
          {partner ? (
            <Text variant="callout" tone="mutedForeground">
              {t("consumo.bag.ask", { partner })}
            </Text>
          ) : null}
        </Card>
      ) : null}

      <Card testID="usage-balance">
        <View accessible accessibilityLabel={`${t("lite.kpi.balance")}: ${balanceText}`} style={styles.figure}>
          <View style={styles.row}>
            <Icon name={icons.wallet} size={15} tone="mutedForeground" />
            <Text variant="subhead" tone="mutedForeground" style={styles.flex}>
              {t("lite.kpi.balance")}
            </Text>
          </View>
          {balance?.assigned && balance.remaining_cents != null ? (
            <CountUpMoney cents={balance.remaining_cents} format={bagMoney} tone={out ? "dangerText" : "foreground"} accessible={false} />
          ) : (
            <Text variant="figureLarge" tone="mutedForeground">
              —
            </Text>
          )}
        </View>
        {hint ? (
          <Text variant="footnote" tone={out ? "dangerText" : "mutedForeground"}>
            {hint}
          </Text>
        ) : null}
        {lastsUntil ? (
          <View style={styles.answer} testID="usage-answer">
            <Text variant="title">{t("app.usage.runsOut", { date: untilDay(lastsUntil, today, locale) })}</Text>
            {runway ? <Meter value={runway.days} max={runway.monthLeft} tone={runway.tone} label={t("lite.kpi.balance.runway.aria")} /> : null}
            {/* The bag's warning already says the days: once is enough. */}
            {pace && !bag ? (
              <Text variant="footnote" tone="mutedForeground">
                {pace}
              </Text>
            ) : null}
          </View>
        ) : null}
        {balance && partner && !bag ? (
          <Text variant="footnote" tone="mutedForeground">
            {t("v13.usage.ask", { partner })}
          </Text>
        ) : null}
      </Card>

      <Group testID="usage-figures">
        <Row
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
        <Row
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
      </Group>

      <Card testID="usage-chart">
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
          {t("app.usage.spend.title", { days })}
        </Text>
        {anySpend === false ? (
          <Text variant="callout" tone="mutedForeground">
            {t("app.usage.empty")}
          </Text>
        ) : (
          <>
            {periodCents != null ? <CountUpMoney cents={periodCents} format={money} testID="usage-period-total" /> : null}
            {anySpend ? (
              <Segmented
                label={t("app.usage.days")}
                value={days}
                onChange={(d) => {
                  // A choice changed: the map's «select» (R2.6).
                  haptics.select();
                  onDays(d);
                }}
                options={PERIODS.map((d) => ({ value: d, label: t("app.usage.days.n", { days: d }) }))}
              />
            ) : null}
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
                <Animated.View key={days} entering={contentFade}>
                  <Chart spend={spend} money={money} t={t} locale={locale} />
                </Animated.View>
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
          </>
        )}
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

      <Group testID="usage-web">
        <RowButton title={t("app.web")} subtitle={t("app.usage.web")} kind="external" tone="primaryText" onPress={onWeb} />
      </Group>
    </View>
  );
}

/** The bars of the period: a day each for 7 and 30, a week each for 90, with three dates and the unit under them. */
function Chart({ spend, money, t, locale }: { spend: Spend; money: (c: number) => string; t: T; locale: Locale }) {
  const d = (day: string) => shortDay(day, locale);
  // The shape follows the series on screen, not the period asked: while the new one loads, the old one keeps its own.
  const length = spend.days.length;
  if (length > 31) {
    const weeks = weekly(spend.days, spend.series_cents);
    const bars: Bar[] = weeks.map((w) => ({ value: w.cents, label: t("v13.usage.chart.week", { from: d(w.from), to: d(w.to) }) }));
    const mid = weeks[Math.floor((weeks.length - 1) / 2)];
    return (
      <>
        <SpendBars
          bars={bars}
          density="quarter"
          axis={[d(weeks[0]?.from ?? ""), d(mid?.from ?? ""), d(weeks.at(-1)?.to ?? "")]}
          summary={`${t("v13.usage.chart.aria.week")}: ${weeks.map((w, i) => t("hu.usage.spend.bar", { day: bars[i]!.label, amount: money(w.cents) })).join(", ")}`}
        />
        <Text variant="caption" tone="mutedForeground">
          {t("v13.usage.chart.unit.week")}
        </Text>
      </>
    );
  }
  const bars: Bar[] = spend.days.map((day, i) => ({ value: spend.series_cents[i] ?? 0, label: d(day) }));
  const mid = spend.days[Math.floor((spend.days.length - 1) / 2)] ?? "";
  return (
    <>
      <SpendBars
        bars={bars}
        density={length <= 7 ? "week" : "month"}
        axis={[d(spend.days[0] ?? ""), d(mid), d(spend.days.at(-1) ?? "")]}
        summary={`${t("v13.usage.chart.aria")}: ${bars.map((b) => t("hu.usage.spend.bar", { day: b.label, amount: money(b.value) })).join(", ")}`}
      />
      <Text variant="caption" tone="mutedForeground">
        {t("v13.usage.chart.unit.day")}
      </Text>
    </>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 16 },
  figure: { gap: 4 },
  answer: { gap: 4, paddingTop: 4 },
  row: { flexDirection: "row", alignItems: "center", gap: 8 },
  agent: { gap: 6 },
  agentRow: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  flex: { flex: 1, minWidth: 0 },
  num: { fontVariant: ["tabular-nums"] },
});
