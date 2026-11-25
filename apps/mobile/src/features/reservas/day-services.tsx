import { Fragment } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";
import Animated from "react-native-reanimated";

import type { Reservation, ResConfig } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { daySummary, isClosed, isPast, nextOpenDays, addDays, type LocalDate, type WallTime } from "@/lib/reservas-model";
import { useArrival } from "@/motion/micro";
import { CARD_RADIUS, useTheme } from "@/theme/theme";
import { Chip } from "@/ui/chip";
import { Icon, icons } from "@/ui/icon";
import { ConflictPill, pillOf } from "@/ui/pill";
import { EmptyState } from "@/ui/states";
import { Text } from "@/ui/text";

import { dayShort, durationShort, firstName, hhmm, nameOf, spoken } from "./format";
import { StatePill } from "./res-pill";

/**
 * Servicios · Día · Lista (spec 044, R2.4, R2.5, R2.10; spec 069, R13.2,
 * design §4.4): the summary of the day, a chip per team member, and one card
 * per reservation — time and length, the customer, «service · person» and the
 * state in words in a pill — with the soft colour of its state (unconfirmed
 * warm, cancelled sunken and struck through), the «Ahora» line between cards
 * today in the brand's green («el rojo es para errores»), and the past ones in
 * a quieter ink (never a drop in opacity). An empty day offers to book it (if
 * it is not past); a closed one, the next open day.
 */
export function DayServices({
  config,
  items,
  now,
  date,
  pro,
  onPro,
  onOpen,
  onNew,
  onDay,
  arrivedId = null,
  t,
  locale,
}: {
  config: ResConfig;
  items: Reservation[];
  now: WallTime;
  date: LocalDate;
  pro: string | null;
  onPro: (id: string | null) => void;
  onOpen: (r: Reservation) => void;
  /** «Reservar este día» on an empty day (spec 069; never on a past one). */
  onNew?: (date: LocalDate) => void;
  /** «Ver el …» on a closed day. */
  onDay?: (date: LocalDate) => void;
  /** The booking just saved: it enters animated (micro 3). */
  arrivedId?: string | null;
  t: T;
  locale: Locale;
}) {
  const team = config.services?.team ?? [];
  const day = items.filter((r) => r.date === date && (pro === null || r.pro?.id === pro)).sort((a, b) => a.start - b.start);
  const sum = daySummary(day);
  const closed = isClosed(config, date);
  const nowIndex = date === now.date ? day.findIndex((r) => r.start >= now.minutes) : -2;
  const past = date < now.date;
  const nextOpen = closed ? nextOpenDays(config, addDays(date, 1), 1)[0] : undefined;

  return (
    <View style={styles.stack}>
      {team.length > 1 ? <TeamChips team={team} pro={pro} onPro={onPro} t={t} /> : null}

      {closed && day.length === 0 ? (
        <EmptyState
          icon={icons.moon}
          title={t("reservas.day.closed")}
          action={onDay && nextOpen ? { label: t("reservas.day.closed.see", { day: dayShort(nextOpen, locale) }), onPress: () => onDay(nextOpen) } : undefined}
        />
      ) : day.length === 0 && pro !== null ? (
        // Filtered: the person has nothing, not the day (gate review).
        <EmptyState
          icon={icons.calendar}
          title={t("reservas.day.empty.pro", { name: team.find((p) => p.id === pro)?.name ?? "" })}
          action={{ label: t("reservas.team.allAction"), onPress: () => onPro(null) }}
        />
      ) : day.length === 0 ? (
        <EmptyState
          icon={icons.calendarAdd}
          title={t("reservas.day.empty")}
          body={past ? undefined : t("reservas.day.empty.body")}
          action={onNew && !past ? { label: t("reservas.day.empty.book"), onPress: () => onNew(date) } : undefined}
        />
      ) : (
        <>
          <Text variant="subhead" tone="mutedForeground">
            {/* No bare zero (spec 069): with all of them confirmed, the total alone. */}
            {sum.unconfirmed === 0
              ? sum.total === 1
                ? t("v13.reservas.summary.total.one")
                : t("v13.reservas.summary.total", { total: sum.total })
              : sum.total === 1
                ? t("reservas.summary.one", { unconfirmed: sum.unconfirmed })
                : t("reservas.summary", { total: sum.total, unconfirmed: sum.unconfirmed })}
          </Text>
          <ListCard>
            {day.map((r, i) => (
              <Fragment key={r.id}>
                {i === nowIndex ? <NowLine now={now} t={t} /> : null}
                <ServicesRow r={r} past={isPast(r, now)} first={i === 0 && i !== nowIndex} config={config} t={t} locale={locale} onOpen={onOpen} arrives={r.id === arrivedId} />
              </Fragment>
            ))}
            {nowIndex === -1 ? <NowLine now={now} t={t} /> : null}
          </ListCard>
        </>
      )}
    </View>
  );
}

export function TeamChips({ team, pro, onPro, t }: { team: { id: string; name: string }[]; pro: string | null; onPro: (id: string | null) => void; t: T }) {
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} accessibilityRole="radiogroup" accessibilityLabel={t("reservas.team.filter")}>
      <Chip label={t("reservas.team.all")} on={pro === null} onPress={() => onPro(null)} />
      {team.map((p) => (
        <Chip key={p.id} label={firstName(p.name)} accessibilityLabel={p.name} on={pro === p.id} onPress={() => onPro(p.id)} />
      ))}
    </ScrollView>
  );
}

/** The day's cards, one under the other (design §4.4: a column with 8 between). */
export function ListCard({ children }: { children: React.ReactNode }) {
  return <View style={styles.list}>{children}</View>;
}

/** «Ahora · 10:54», in the brand's green: red is for errors (design §4.5). */
export function NowLine({ now, t }: { now: WallTime; t: T }) {
  const { colors } = useTheme();
  return (
    <View style={styles.now} accessibilityRole="text">
      <View style={[styles.nowDot, { backgroundColor: colors.highlight }]} />
      <Text variant="caption" tone="highlightInk">
        {t("reservas.now", { time: hhmm(now.minutes) })}
      </Text>
      <View style={[styles.nowRule, { backgroundColor: colors.highlight }]} />
    </View>
  );
}

export function ServicesRow({
  r,
  past,
  config,
  t,
  onOpen,
  arrives = false,
}: {
  r: Reservation;
  past: boolean;
  /** Kept for the callers of spec 044; cards have no separators to skip. */
  first?: boolean;
  config: ResConfig;
  t: T;
  /** Kept for the callers of spec 044. */
  locale?: Locale;
  onOpen: (r: Reservation) => void;
  arrives?: boolean;
}) {
  const { colors } = useTheme();
  const arrival = useArrival();
  const look = pillOf(r, "services", null, t);
  const label = `${spoken(r, look.label, t, "")}${r.conflict ? `, ${t("reservas.state.conflict")}` : ""}${past ? `, ${t("reservas.row.past")}` : ""}`;
  const cancelled = r.state === "cancelled";
  const pending = r.state === "pending";
  const ink = past || cancelled ? "mutedForeground" : "foreground";
  return (
    <Animated.View entering={arrives ? arrival.entering : undefined}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={label}
        onPress={() => onOpen(r)}
        android_ripple={{ color: colors.muted }}
        testID={`res-${r.id}`}
        style={({ pressed }) => [
          styles.card,
          {
            backgroundColor: pressed ? colors.muted : cancelled ? colors.muted : pending ? colors.warningBg : colors.card,
            borderColor: cancelled ? "transparent" : colors.border,
            transform: [{ scale: pressed ? 0.985 : 1 }],
          },
        ]}
      >
        <View style={styles.time}>
          <Text variant="bodyStrong" tone={pending && !past ? "warningText" : ink} style={styles.num} numberOfLines={1}>
            {hhmm(r.start)}
          </Text>
          <Text variant="caption" tone="mutedForeground" numberOfLines={1}>
            {durationShort(r.service ? r.service.durationMin : r.end - r.start, t)}
          </Text>
        </View>
        <View style={styles.body}>
          <Text variant="bodyStrong" tone={ink} numberOfLines={1} style={cancelled ? styles.struck : undefined}>
            {nameOf(r, t)}
          </Text>
          {r.service && r.pro ? (
            <Text variant="footnote" tone="mutedForeground" numberOfLines={2}>
              {t("reservas.service.with", { service: r.service.name, pro: firstName(r.pro.name) })}
            </Text>
          ) : null}
          <View style={styles.pills}>
            <StatePill state={r.state} origin={r.origin} mode={config.mode} late={null} t={t} />
            {r.conflict && r.state !== "cancelled" ? <ConflictPill /> : null}
          </View>
        </View>
        <View style={styles.chevron} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
          <Icon name={icons.chevron} size={18} tone="subtle" />
        </View>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 12 },
  chips: { gap: 8, paddingVertical: 2 },
  list: { gap: 8 },
  card: { flexDirection: "row", gap: 12, paddingLeft: 14, paddingRight: 12, paddingVertical: 12, minHeight: 64, borderRadius: CARD_RADIUS - 2, borderWidth: StyleSheet.hairlineWidth * 2 },
  time: { minWidth: 52, gap: 2 }, // grows with large text rather than break the time (gate review)
  num: { fontVariant: ["tabular-nums"] },
  body: { flex: 1, minWidth: 0, gap: 3 },
  pills: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 2 },
  struck: { textDecorationLine: "line-through" },
  chevron: { justifyContent: "center" },
  now: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 4, paddingVertical: 2 },
  nowDot: { width: 8, height: 8, borderRadius: 4 },
  nowRule: { flex: 1, height: 2, borderRadius: 1 },
});
