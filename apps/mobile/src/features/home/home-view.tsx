import { StyleSheet, View } from "react-native";

import type { Home, Me } from "@/api/endpoints";
import type { Locale, T } from "@/i18n/t";
import { formatMoney, formatMoneyCompact, formatNumber, shortDay } from "@/lib/format";
import { creditRunway, trendDelta } from "@/lib/panel-model";
import { Meter, RowButton } from "@/ui/bits";
import { Card } from "@/ui/card";
import { Group, Row } from "@/ui/group";
import { icons } from "@/ui/icon";
import { ErrorState, PartialNotice } from "@/ui/states";
import { Text } from "@/ui/text";

import { AgentsGroup, type AgentsRead } from "../agents/agents-group";
import { DayBars } from "../charts/day-bars";
import { Attention } from "./attention";
import { TodayCard, unconfirmedToday, type TodayReservas } from "./today-reservas";

/**
 * Inicio (spec 031, R4.1; spec 042, R5): the Panel of the console, laid out for
 * a thumb, saying each thing once. Three blocks, in this order: what needs a
 * person (or one calm line), the money as one grouped list, and the week's
 * conversations as one figure with its bars. Pure — every state is testable
 * without a request. `home === null` is the whole read failing; `errors`
 * lists blocks that did not load (partial). A block whose data is absent is
 * absent: no balance, no money group; no Consumo module, no way into it.
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
  onInbox,
  reservas = null,
  onReservas,
  agents = null,
  onAgent,
  onBusiness,
  businessHint = null,
}: {
  me: Pick<Me, "client" | "nav" | "balance_contact">;
  home: Home | null;
  t: T;
  locale: Locale;
  now?: Date;
  onRetry: () => void;
  onAttend: (conversationId: string | null) => void;
  onUsage: () => void;
  /** Spec 044, R9.3: the conversations block leads to the Bandeja. */
  onInbox?: () => void;
  /** Spec 044, R9.1, R9.4: today in Reservas; `null` without the module (R1.2). */
  reservas?: TodayReservas | null;
  onReservas?: () => void;
  /** Spec 047 (50.1): the agents with their state; `null` without the module. */
  agents?: AgentsRead | null;
  onAgent?: (id: string) => void;
  /** Spec 047 (50.1): the way into Negocio; absent without the module. */
  onBusiness?: () => void;
  /** «Así lo dirá el agente» of the hours, under the way into Negocio, when it is known. */
  businessHint?: string | null;
}) {
  const n = (v: number) => formatNumber(v, locale);
  if (home === null) return <ErrorState body={t("common.error.backend")} onRetry={onRetry} />;

  const modules = me.nav;
  const hasUsage = modules.includes("usage");
  const conv = home.conversations ?? null;
  const delta = conv ? trendDelta(conv.last_7d, conv.prev_7d ?? null) : null;
  const balance = home.balance ?? null;
  const runway = balance?.assigned ? creditRunway(balance.remaining_cents ?? null, balance.days_left ?? null, now) : null;
  const out = balance?.assigned === true && (balance.remaining_cents ?? 0) <= 0;
  const spend = home.spend_month ?? null;
  // One way into Consumo per screen (R6): when the attention block already offers it
  // next to the balance that needs attention, the money group does not repeat it.
  const attentionOffersUsage = hasUsage && home.attention.some((a) => a.kind !== "waiting");

  return (
    <View style={styles.stack}>
      {home.errors.length > 0 ? <PartialNotice text={t("lite.panel.partial")} /> : null}
      <Attention
        home={home}
        contact={me.balance_contact}
        modules={modules}
        reservasUnconfirmed={unconfirmedToday(reservas)}
        t={t}
        n={n}
        onAttend={onAttend}
        onUsage={onUsage}
        onReservas={onReservas}
      />
      {agents && onAgent ? <AgentsGroup read={agents} onAgent={onAgent} t={t} /> : null}
      {balance ? (
        <Group testID="home-money">
          <Row
            label={t("lite.kpi.balance")}
            value={balance.assigned && balance.remaining_cents != null ? formatMoneyCompact(balance.remaining_cents, locale, balance.currency) : "—"}
            valueTone={out ? "dangerText" : "foreground"}
            hint={
              !balance.assigned
                ? t("lite.kpi.balance.unassigned")
                : out
                  ? t("lite.kpi.balance.out")
                  : runway
                    ? undefined
                    : t("lite.kpi.balance.noSpend")
            }
          />
          {runway ? (
            <Row label={t("lite.kpi.balance.runway", { days: n(runway.days), left: n(runway.monthLeft) })}>
              <Meter value={runway.days} max={runway.monthLeft} tone={runway.tone} label={t("lite.kpi.balance.runway.aria")} />
            </Row>
          ) : null}
          {spend ? <Row label={t("lite.spend.title")} value={formatMoney(spend.total_cents, locale)} /> : null}
          {hasUsage && !attentionOffersUsage ? <Row label={t("lite.spend.see")} tone="primaryText" kind="push" onPress={onUsage} /> : null}
        </Group>
      ) : null}
      {reservas && onReservas ? <TodayCard today={reservas} onReservas={onReservas} t={t} /> : null}
      {conv ? (
        <Card>
          <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
            {t("lite.kpi.conversations")}
          </Text>
          <Text variant="figure">{n(conv.last_7d)}</Text>
          {delta ? (
            <Text variant="footnote" tone="mutedForeground">
              {delta.kind === "none" ? t("hu.home.kpi.delta.none") : t(`hu.home.kpi.delta.${delta.kind}`, { pct: n(delta.pct) })}
            </Text>
          ) : null}
          {conv.daily.length > 0 ? (
            <DayBars
              values={conv.daily.map((d) => d.count)}
              labels={conv.daily.map((d) => shortDay(d.day, locale))}
              summary={`${t("hu.home.kpi.conversations.trend")}: ${conv.daily.map((d) => t("app.chart.day", { day: shortDay(d.day, locale), value: n(d.count) })).join(", ")}`}
            />
          ) : null}
          {modules.includes("inbox") && onInbox ? (
            <View style={styles.bleed}>
              <RowButton title={t("app.home.inbox.see")} tone="primaryText" kind="push" onPress={onInbox} />
            </View>
          ) : null}
        </Card>
      ) : null}
      {onBusiness ? (
        <Group title={t("negocio.title")} testID="home-business">
          <RowButton title={t("negocio.open")} subtitle={businessHint ?? t("negocio.open.hint")} icon={icons.business} onPress={onBusiness} />
        </Group>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 16 },
  // The row's press tint reaches the card's edges, past the card's own padding.
  bleed: { marginHorizontal: -16, marginBottom: -8 },
});
