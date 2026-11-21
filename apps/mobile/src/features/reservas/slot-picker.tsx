import { Pressable, StyleSheet, View } from "react-native";
import Animated from "react-native-reanimated";

import type { FreeSlot, ResConfig } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { hhmm, isBefore, openSpans, type LocalDate, type Minutes, type WallTime } from "@/lib/reservas-model";
import { haptics } from "@/motion/haptics";
import { contentFade, DrawCheck } from "@/motion/micro";
import { RADII, TOUCH, useTheme } from "@/theme/theme";
import { Button } from "@/ui/button";
import { Icon, icons, type IconName } from "@/ui/icon";
import { Skeleton } from "@/ui/states";
import { Text } from "@/ui/text";

import { dayNumber, dayTitle, firstName, stripWeekday } from "./format";

/**
 * The day and the time of «Nueva reserva» and «Mover la reserva» (spec 069,
 * R15.1, R14.3; design §6.1–§6.2): the next open days as a strip, and the
 * times in two groups — morning and afternoon in Servicios, the shifts in
 * Aforo — with how many are free. What is not free stays in its place, struck
 * through and not choosable (never colour alone); the chosen one is ink with a
 * check that draws itself (micro 2). Times before the agent's minimum notice
 * are not offered at all (R15.2).
 */
export type SlotCell = {
  time: Minutes;
  state: "free" | "taken";
  /** Who would do it, when the API says (Servicios). */
  pro: { id: string; name: string } | null;
  /** Aforo: what is left at that time. */
  left: number | null;
};

export type SlotGroup = { key: string; label: string; icon: IconName; cells: SlotCell[] };

const NOON = 14 * 60;

/**
 * The cells of a day. Servicios: every step of the open hours that fits the
 * service, free when the API returned it; Aforo: the API's arrival times, full
 * ones struck. `earliest` drops what comes before it; `skip` drops one time
 * (the current time of a reservation being moved).
 */
export function slotCells(
  config: ResConfig,
  date: LocalDate,
  slots: FreeSlot[],
  durationMin: number,
  earliest: WallTime | null,
  skip: Minutes | null = null,
): SlotCell[] {
  const free = new Map(slots.filter((s) => !s.full).map((s) => [s.time, s] as const));
  const shown = (time: Minutes) => (earliest ? !isBefore(date, time, earliest) : true) && time !== skip;
  if (config.mode === "capacity") {
    return slots
      .filter((s) => shown(s.time))
      .map((s): SlotCell => ({ time: s.time, state: s.full ? "taken" : "free", pro: null, left: s.left }))
      .sort((a, b) => a.time - b.time);
  }
  const step = config.services?.stepMin ?? 30;
  const times = new Set<Minutes>();
  for (const span of openSpans(config, date)) for (let t = span.open; t + durationMin <= span.close; t += step) times.add(t);
  for (const t of free.keys()) times.add(t);
  return [...times]
    .filter(shown)
    .sort((a, b) => a - b)
    .map((time): SlotCell => {
      const s = free.get(time);
      return { time, state: s ? "free" : "taken", pro: s?.pro ?? null, left: null };
    });
}

/** Morning and afternoon in Servicios; each shift in Aforo. Groups with nothing are left out. */
export function slotGroups(config: ResConfig, cells: SlotCell[], t: T): SlotGroup[] {
  const shifts = config.mode === "capacity" ? (config.capacity?.shifts ?? []) : [];
  const groups: SlotGroup[] =
    shifts.length > 0
      ? shifts.map((s) => ({ key: s.name, label: s.name, icon: s.from >= 18 * 60 ? icons.moon : icons.sun, cells: cells.filter((c) => c.time >= s.from && c.time <= s.to) }))
      : [
          { key: "morning", label: t("reservas.form.morning"), icon: icons.sun, cells: cells.filter((c) => c.time < NOON) },
          { key: "afternoon", label: t("reservas.form.afternoon"), icon: icons.moon, cells: cells.filter((c) => c.time >= NOON) },
        ];
  // A time outside every shift still shows, in a last group of its own.
  const placed = new Set(groups.flatMap((g) => g.cells.map((c) => c.time)));
  const rest = cells.filter((c) => !placed.has(c.time));
  if (rest.length) groups.push({ key: "other", label: t("reservas.new.time"), icon: icons.clock, cells: rest });
  return groups.filter((g) => g.cells.length > 0);
}

export function freeCount(cells: SlotCell[], t: T): string {
  const n = cells.filter((c) => c.state === "free").length;
  return n === 0 ? t("reservas.form.free.none") : n === 1 ? t("reservas.form.free.one") : t("reservas.form.free", { n });
}

/** The strip of days of a form: day of the week and number, the chosen one ink, today in turquoise. */
export function OpenDays({
  days,
  value,
  today,
  onChange,
  t,
  locale,
}: {
  days: LocalDate[];
  value: LocalDate;
  today: LocalDate;
  onChange: (d: LocalDate) => void;
  t: T;
  locale: Locale;
}) {
  const { colors } = useTheme();
  return (
    <View style={[styles.days, { backgroundColor: colors.card, borderColor: colors.border }]} accessibilityRole="radiogroup" accessibilityLabel={t("reservas.new.day")}>
      {days.map((d) => {
        const on = d === value;
        const isToday = d === today;
        const ink = on ? "onSelection" : isToday ? "highlightInk" : "foreground";
        return (
          <Pressable
            key={d}
            accessibilityRole="radio"
            accessibilityState={{ checked: on }}
            accessibilityLabel={t(isToday ? "reservas.day.a11y.today" : "reservas.form.day.a11y", { day: dayTitle(d, locale) })}
            onPress={() => {
              if (!on) haptics.select();
              onChange(d);
            }}
            style={({ pressed }) => [styles.day, { backgroundColor: on ? colors.selection : pressed ? colors.muted : "transparent" }]}
            testID={`day-${d}`}
          >
            <Text variant="caption" tone={on ? "onSelection" : isToday ? "highlightInk" : "mutedForeground"} maxFontSizeMultiplier={1.4} numberOfLines={1}>
              {stripWeekday(d, isToday, t, locale)}
            </Text>
            <Text variant="bodyStrong" tone={ink} style={styles.num} maxFontSizeMultiplier={1.4}>
              {dayNumber(d)}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

/**
 * The groups of times. While the API answers, a skeleton the size of the
 * chips; then they fade in (micro 5). Unreadable says so with «Reintentar».
 */
export function SlotGroups({
  groups,
  value,
  onChange,
  loading,
  error,
  onRetry,
  empty,
  anyPro,
  t,
}: {
  groups: SlotGroup[];
  value: Minutes | null;
  onChange: (cell: SlotCell) => void;
  loading: boolean;
  error: boolean;
  onRetry?: () => void;
  /** What to say when nothing is left. */
  empty: string;
  /** «Cualquiera» is chosen: the screen reader says who would do each time. */
  anyPro: boolean;
  t: T;
}) {
  const { colors } = useTheme();
  if (loading) return <Skeleton rows={2} label={t("reservas.new.slots.loading")} />;
  if (error) {
    return (
      <View style={styles.error}>
        <Text variant="callout" tone="dangerText" accessibilityRole="alert">
          {t("reservas.new.slots.error")}
        </Text>
        {onRetry ? <Button label={t("app.retry")} variant="secondary" compact onPress={onRetry} /> : null}
      </View>
    );
  }
  if (!groups.some((g) => g.cells.some((c) => c.state === "free"))) {
    return (
      <Text variant="callout" tone="mutedForeground">
        {empty}
      </Text>
    );
  }
  return (
    <Animated.View entering={contentFade} style={styles.groups}>
      {groups.map((g) => (
        <View key={g.key} style={styles.group}>
          <View style={styles.groupHead}>
            <Icon name={g.icon} size={15} tone="mutedForeground" />
            <Text variant="footnote" tone="mutedForeground" accessibilityRole="header">
              {`${g.label} · ${freeCount(g.cells, t)}`}
            </Text>
          </View>
          <View style={styles.grid}>
            {g.cells.map((c) => {
              const on = value === c.time && c.state === "free";
              const taken = c.state === "taken";
              const label = taken
                ? c.left !== null
                  ? t("reservas.new.slot.a11y.full", { time: hhmm(c.time) })
                  : t("reservas.form.slot.taken", { time: hhmm(c.time) })
                : c.left !== null
                  ? t("reservas.new.slot.a11y.left", { time: hhmm(c.time), n: c.left })
                  : c.pro
                    ? t("reservas.new.slot.a11y", { time: hhmm(c.time), pro: c.pro.name })
                    : hhmm(c.time);
              return (
                <Pressable
                  key={c.time}
                  accessibilityRole="radio"
                  accessibilityLabel={label}
                  accessibilityState={{ checked: on, disabled: taken }}
                  onPress={() => {
                    if (taken) {
                      haptics.warning();
                      return;
                    }
                    if (!on) haptics.select();
                    onChange(c);
                  }}
                  hitSlop={{ top: 6, bottom: 6 }}
                  testID={`slot-${hhmm(c.time)}`}
                  style={({ pressed }) => [
                    styles.slot,
                    {
                      backgroundColor: on ? colors.selection : taken ? "transparent" : pressed ? colors.muted : colors.card,
                      borderColor: on ? colors.selection : taken ? "transparent" : colors.controlBorder,
                      transform: [{ scale: pressed && !taken ? 0.96 : 1 }],
                    },
                  ]}
                >
                  <View style={styles.slotLine}>
                    {on ? (
                      <View testID="slot-check">
                        <DrawCheck size={14} color={colors.onSelection} />
                      </View>
                    ) : null}
                    <Text
                      variant="subhead"
                      tone={on ? "onSelection" : taken ? "mutedForeground" : "foreground"}
                      style={[styles.num, taken ? styles.struck : null]}
                      maxFontSizeMultiplier={1.4}
                      numberOfLines={1}
                    >
                      {hhmm(c.time)}
                    </Text>
                  </View>
                  {c.left !== null ? (
                    <Text variant="caption" tone={on ? "onSelection" : "mutedForeground"} numberOfLines={1} maxFontSizeMultiplier={1.3}>
                      {taken ? t("reservas.new.full") : t("reservas.new.left", { n: c.left })}
                    </Text>
                  ) : anyPro && c.pro && !taken ? (
                    <Text variant="caption" tone={on ? "onSelection" : "mutedForeground"} numberOfLines={1} maxFontSizeMultiplier={1.3}>
                      {firstName(c.pro.name)}
                    </Text>
                  ) : null}
                </Pressable>
              );
            })}
            {/* Empty places to finish the last row of four, so its times are as wide as the others. */}
            {Array.from({ length: (4 - (g.cells.length % 4)) % 4 }, (_, i) => (
              <View key={`filler-${i}`} testID="slot-filler" style={[styles.slot, styles.filler]} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" pointerEvents="none" />
            ))}
          </View>
        </View>
      ))}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  days: { flexDirection: "row", gap: 2, padding: 6, borderRadius: RADII.lg, borderWidth: StyleSheet.hairlineWidth * 2 },
  day: { flex: 1, minWidth: 0, minHeight: 58, alignItems: "center", justifyContent: "center", gap: 2, borderRadius: RADII.lg, paddingVertical: 6 },
  num: { fontVariant: ["tabular-nums"] },
  groups: { gap: 16 },
  group: { gap: 8 },
  groupHead: { flexDirection: "row", alignItems: "center", gap: 6 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  slot: {
    flexBasis: "22%",
    flexGrow: 1,
    minHeight: Math.max(36, TOUCH - 8),
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderRadius: RADII.pill,
    paddingHorizontal: 6,
    paddingVertical: 4,
  },
  slotLine: { flexDirection: "row", alignItems: "center", gap: 4 },
  struck: { textDecorationLine: "line-through" },
  filler: { borderColor: "transparent" },
  error: { gap: 8, alignItems: "flex-start" },
});
