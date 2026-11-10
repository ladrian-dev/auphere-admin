import { StyleSheet, View } from "react-native";

import type { Me, Spend, UsageSummary } from "@/api/endpoints";
import type { Locale, T } from "@/i18n/t";
import { formatMoney, formatNumber, shortDay } from "@/lib/format";
import { creditRunway, localToday, untilDay } from "@/lib/panel-model";
import { runsOutOn } from "@/lib/reservas-model";
import { Divider, Meter, RowButton, Segmented } from "@/ui/bits";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Group, Row } from "@/ui/group";
import { Icon, icons } from "@/ui/icon";
import { ErrorState, PartialNotice } from "@/ui/states";
import { Text } from "@/ui/text";

import { DayBars } from "../charts/day-bars";

export const PERIODS = [7, 30, 90] as const;
export type Period = (typeof PERIODS)[number];

/**
 * Consumo (spec 031, R4.2–R4.5; spec 042, R9, R6.2): read-only. The figures as
 * rows of one group — the balance and how long it lasts, the month's spend and
 * its projection, the month's conversations — the same cents as the console
 * (R4.3). Spec 044 (R13): the group opens with the answer — «Te alcanza hasta
 * el sábado 17», at the 7-day pace, from the API's `runs_out_on` or worked out
 * from `days_left` — and says whom to talk to for more; with no spend, no
 * balance assigned or nothing left, it says that instead and invents no date. Then the spend per day as one figure with its bars; the period is
 * offered only when the widest series has something in it (R9.2), and an empty
 * chart says what will fill it. No buy, no top-up, no link to one (R4.4); the
 * technical detail and its export stay on the web (R4.5), behind one row that
 * says it leaves the app.
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
  // Spec 047: the bag in its own currency; the spend in the report's (both US$ until a partner changes it).
  const bagMoney = (c: number) => formatMoney(c, locale, balance?.currency ?? "USD");
  const money = (c: number) => formatMoney(c, locale, spend?.currency ?? balance?.currency ?? "USD");
  const month = summary.month ?? null;
  const runway = balance?.assigned ? creditRunway(balance.remaining_cents ?? null, balance.days_left ?? null, now) : null;
  const out = balance?.assigned === true && (balance.remaining_cents ?? 0) <= 0;
  const byAgent = summary.by_agent && summary.by_agent.length > 1 ? summary.by_agent : null;
  const agentName = agent ? agents.find((a) => a.id === agent)?.name ?? null : null;
  const every = days === 7 ? 1 : days === 30 ? 5 : 15;
  const periodCents = spend ? spend.series_cents.reduce((a, b) => a + b, 0) : null;
  const today = localToday(now);
  const apiDate = balance ? (balance as { runs_out_on?: string | null }).runs_out_on ?? null : null;
  const lastsUntil = balance?.assigned && !out ? (apiDate ?? (balance.days_left != null ? runsOutOn(balance.days_left, today) : null)) : null;
  const whom = contact ? (contact.kind === "auphere" ? t("app.usage.recharge.auphere") : t("app.usage.recharge.partner", { name: contact.name })) : null;
  // Spec 047 (50.6, `events.md` §1.4): «Queda poco», «No llega a fin de mes» or «Agotada», and whom to ask — no button.
  const bag = summary.bag_state === "low" || summary.bag_state === "not_enough" || summary.bag_state === "empty" ? summary.bag_state : null;
  const partner = summary.partner_name || (contact ? (contact.kind === "auphere" ? "Auphere" : contact.name) : null);

  return (
    <View style={styles.stack}>
      {summary.errors.length > 0 ? <PartialNotice text={t("lite.usage.partial")} /> : null}
      {bag ? (
        <Card tone={bag === "empty" ? "danger" : "warning"} testID="usage-bag">
          <View style={styles.bagTitle} accessible accessibilityRole="alert">
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
      <Group testID="usage-figures">
        <Row
          label={t("lite.kpi.balance")}
          value={balance?.assigned && balance.remaining_cents != null ? bagMoney(balance.remaining_cents) : "—"}
          valueTone={out ? "dangerText" : "foreground"}
          hint={
            balance === null
              ? t("lite.usage.unreadable")
              : !balance.assigned
                ? t("lite.kpi.balance.unassigned")
                : out
                  ? t("lite.kpi.balance.out")
                  : runway
                    ? undefined
                    : t("lite.kpi.balance.noSpend")
          }
        />
        {lastsUntil ? (
          <View style={styles.answer} testID="usage-answer">
            <Text variant="title">{t("app.usage.runsOut", { date: untilDay(lastsUntil, today, locale) })}</Text>
            {runway ? <Meter value={runway.days} max={runway.monthLeft} tone={runway.tone} label={t("lite.kpi.balance.runway.aria")} /> : null}
            <Text variant="footnote" tone="mutedForeground">
              {t("app.usage.runsOut.pace")}
            </Text>
          </View>
        ) : null}
        {balance && whom && !bag ? (
          <View style={styles.whom}>
            <Text variant="footnote" tone="mutedForeground">
              {whom}
            </Text>
          </View>
        ) : null}
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

      <Card>
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
          {t("app.usage.spend.title", { days })}
        </Text>
        {anySpend === false ? (
          <Text variant="callout" tone="mutedForeground">
            {t("app.usage.empty")}
          </Text>
        ) : (
          <>
            {periodCents != null ? <Text variant="figure">{money(periodCents)}</Text> : null}
            {anySpend ? (
              <Segmented
                label={t("app.usage.days")}
                value={days}
                onChange={onDays}
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

const styles = StyleSheet.create({
  stack: { gap: 16 },
  answer: { gap: 8, paddingHorizontal: 16, paddingVertical: 12 },
  whom: { paddingHorizontal: 16, paddingVertical: 12 },
  bagTitle: { flexDirection: "row", alignItems: "center", gap: 8 },
  agent: { gap: 6 },
  agentRow: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  flex: { flex: 1, minWidth: 0 },
  num: { fontVariant: ["tabular-nums"] },
});
