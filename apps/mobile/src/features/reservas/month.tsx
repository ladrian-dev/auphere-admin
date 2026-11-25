import { Pressable, StyleSheet, View } from "react-native";

import type { DayOccupancy } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { monthGrid, type LocalDate } from "@/lib/reservas-model";
import { haptics } from "@/motion/haptics";
import { CARD_RADIUS, RADII, useTheme } from "@/theme/theme";
import { Text } from "@/ui/text";

import { dayNumber, dayTitle } from "./format";

/** Dots shown under a day, at most (design §4.7). */
const DOTS = 3;

/**
 * Mes (spec 044 R3.3; spec 069 R13.5, design §4.7): the month's grid, Monday
 * first, a dot per booking under each day (up to three), today in turquoise
 * without a ring, the chosen day in ink, and «Cerrado» where the business
 * does not open. Each day says its whole name and how many bookings it has to
 * the screen reader; a day takes you to it. The same in both modes.
 */
export function MonthGrid({
  month,
  days,
  counts = {},
  today,
  selected = null,
  onDay,
  t,
  locale,
}: {
  month: LocalDate;
  /** Which days are closed (`occupancy`). */
  days: DayOccupancy[];
  /** Bookings that are not cancelled, per day. */
  counts?: Record<LocalDate, number>;
  today: LocalDate;
  selected?: LocalDate | null;
  onDay: (d: LocalDate) => void;
  t: T;
  locale: Locale;
}) {
  const { colors } = useTheme();
  const weeks = monthGrid(month);
  const letters = t("reservas.weekdays").split(",");
  return (
    <View style={styles.stack}>
      <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border, borderRadius: CARD_RADIUS }]}>
        <View style={styles.row} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
          {letters.map((l, i) => (
            <Text key={i} variant="caption" tone="mutedForeground" style={styles.letter}>
              {l}
            </Text>
          ))}
        </View>
        {weeks.map((week, w) => (
          <View key={w} style={styles.row}>
            {week.map((d, i) => {
              if (!d) return <View key={i} style={styles.cell} />;
              const closed = days.find((x) => x.date === d)?.closed ?? false;
              const n = counts[d] ?? 0;
              const on = d === selected;
              const isToday = d === today;
              const label = closed && n === 0
                ? t("reservas.month.cell.closed", { day: dayTitle(d, locale) })
                : n === 0
                  ? t("reservas.month.cell.none", { day: dayTitle(d, locale) })
                  : n === 1
                    ? t("reservas.month.cell.one", { day: dayTitle(d, locale) })
                    : t("reservas.month.cell.many", { day: dayTitle(d, locale), n });
              return (
                <Pressable
                  key={d}
                  accessibilityRole="button"
                  accessibilityLabel={label}
                  accessibilityState={{ selected: on }}
                  onPress={() => {
                    haptics.select();
                    onDay(d);
                  }}
                  style={({ pressed }) => [
                    styles.cell,
                    styles.day,
                    { backgroundColor: on ? colors.selection : pressed ? colors.muted : "transparent", transform: [{ scale: pressed ? 0.95 : 1 }] },
                  ]}
                >
                  <Text variant="subhead" tone={on ? "onSelection" : isToday ? "highlightInk" : closed ? "mutedForeground" : "foreground"} style={styles.num} maxFontSizeMultiplier={1.3}>
                    {dayNumber(d)}
                  </Text>
                  {closed && n === 0 ? (
                    // A seventh of a phone: the word shrinks to fit rather than end in «…».
                    <Text variant="caption" tone={on ? "onSelection" : "mutedForeground"} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7} maxFontSizeMultiplier={1.2}>
                      {t("reservas.month.closed")}
                    </Text>
                  ) : (
                    <View style={styles.dots} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
                      {Array.from({ length: Math.min(DOTS, n) }, (_, k) => (
                        <View key={k} style={[styles.dot, { backgroundColor: on ? colors.onSelection : colors.highlightInk }]} />
                      ))}
                    </View>
                  )}
                </Pressable>
              );
            })}
          </View>
        ))}
      </View>
      <Text variant="footnote" tone="mutedForeground" style={styles.legend}>
        {t("reservas.month.legend")}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 8 },
  card: { borderWidth: StyleSheet.hairlineWidth * 2, paddingVertical: 10, paddingHorizontal: 8, gap: 2 },
  row: { flexDirection: "row", gap: 2 },
  letter: { flex: 1, textAlign: "center", paddingVertical: 6 },
  cell: { flex: 1, minWidth: 0 },
  day: { alignItems: "center", justifyContent: "center", gap: 3, minHeight: 46, paddingVertical: 4, borderRadius: RADII.md + 2 },
  num: { fontVariant: ["tabular-nums"] },
  dots: { flexDirection: "row", gap: 2, height: 5 },
  dot: { width: 5, height: 5, borderRadius: 3 },
  legend: { textAlign: "center" },
});
