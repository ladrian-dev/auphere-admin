import { StyleSheet, View } from "react-native";

import type { Home, Me } from "@/api/endpoints";
import type { Locale, T } from "@/i18n/t";
import { formatMoneyCompact, formatNumber, shortDay } from "@/lib/format";
import { creditRunway, trendDelta } from "@/lib/panel-model";
import { Meter } from "@/ui/bits";
import { Card } from "@/ui/card";
import { icons } from "@/ui/icon";
import { ErrorState, PartialNotice } from "@/ui/states";
import { Text } from "@/ui/text";

import { DayBars } from "../charts/day-bars";
import { Attention } from "./attention";
import { Metric } from "./metric";
import { SpendCard } from "./spend-card";

/**
 * Inicio (spec 031, R4.1): the Panel of the console, laid out for a thumb.
 * Pure — every state is testable without a request. `home === null` is the
 * whole read failing; `errors` lists blocks that did not load (partial). A
 * block whose data is absent is absent: no inbox, no «waiting» card.
 */
export function HomeView({
  me,
  home,
  t,
  locale,
  now = new Date(),
  onRetry,
  onAttend,
  onUsage,
}: {
  me: Pick<Me, "client" | "nav" | "balance_contact">;
  home: Home | null;
  t: T;
  locale: Locale;
  now?: Date;
  onRetry: () => void;
  onAttend: (conversationId: string | null) => void;
  onUsage: () => void;
}) {
  const n = (v: number) => formatNumber(v, locale);
  if (home === null) return <ErrorState body={t("common.error.backend")} onRetry={onRetry} />;

  const modules = me.nav;
  const hasUsage = modules.includes("usage");
  const hasInbox = modules.includes("inbox");
  const conv = home.conversations ?? null;
  const delta = conv ? trendDelta(conv.last_7d, conv.prev_7d ?? null) : null;
  const balance = home.balance ?? null;
  const runway = balance?.assigned ? creditRunway(balance.remaining_cents ?? null, balance.days_left ?? null, now) : null;
  const out = balance?.assigned === true && (balance.remaining_cents ?? 0) <= 0;

  return (
    <View style={styles.stack}>
      {home.errors.length > 0 ? <PartialNotice text={t("lite.panel.partial")} /> : null}
      <Attention
        home={home}
        contact={me.balance_contact}
        modules={modules}
        t={t}
        n={n}
        onAttend={onAttend}
        onUsage={onUsage}
      />
      <View style={styles.grid} accessibilityLabel={t("lite.panel.kpis")}>
        {conv && delta ? (
          <Metric
            icon={icons.chat}
            label={t("lite.kpi.conversations")}
            value={n(conv.last_7d)}
            hint={delta.kind === "none" ? t("hu.home.kpi.delta.none") : t(`hu.home.kpi.delta.${delta.kind}`, { pct: n(delta.pct) })}
            onPress={hasInbox ? () => onAttend(null) : undefined}
          />
        ) : null}
        {home.waiting ? (
          <Metric
            icon={icons.hand}
            label={t("lite.kpi.waiting")}
            value={n(home.waiting.count)}
            hint={t("lite.kpi.waiting.hint")}
            tone={home.waiting.count > 0 ? "warning" : undefined}
            onPress={hasInbox ? () => onAttend(home.waiting?.first_conversation_id ?? null) : undefined}
          />
        ) : null}
        {balance ? (
          <Metric
            icon={icons.wallet}
            label={t("lite.kpi.balance")}
            value={balance.assigned && balance.remaining_cents != null ? formatMoneyCompact(balance.remaining_cents, locale) : "—"}
            tone={out ? "danger" : undefined}
            hint={
              !balance.assigned
                ? t("lite.kpi.balance.unassigned")
                : out
                  ? t("lite.kpi.balance.out")
                  : runway
                    ? t("lite.kpi.balance.runway", { days: n(runway.days), left: n(runway.monthLeft) })
                    : t("lite.kpi.balance.noSpend")
            }
            onPress={hasUsage ? onUsage : undefined}
          >
            {runway ? <Meter value={runway.days} max={runway.monthLeft} tone={runway.tone} label={t("lite.kpi.balance.runway.aria")} /> : null}
          </Metric>
        ) : null}
      </View>
      {home.spend_month ? <SpendCard spend={home.spend_month} t={t} locale={locale} onUsage={hasUsage ? onUsage : undefined} /> : null}
      {conv && conv.daily.length > 0 ? (
        <Card>
          <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
            {t("hu.home.chart.title")}
          </Text>
          <DayBars
            values={conv.daily.map((d) => d.count)}
            labels={conv.daily.map((d) => shortDay(d.day, locale))}
            summary={`${t("hu.home.kpi.conversations.trend")}: ${conv.daily.map((d) => t("app.chart.day", { day: shortDay(d.day, locale), value: n(d.count) })).join(", ")}`}
          />
        </Card>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 16 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
});
