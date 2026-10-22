import { Pressable, StyleSheet, View } from "react-native";

import type { DayOccupancy } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { monthGrid, type LocalDate } from "@/lib/reservas-model";
import { CARD_RADIUS, useTheme } from "@/theme/theme";
import { Text } from "@/ui/text";

import { dayNumber, dayTitle } from "./format";

/**
 * Mes (spec 044, R3.3, research D10): the month's grid, Monday first, each day
 * with a bar of how full it is and «N %» or «Cerrado»; a day takes you to it.
 * The same in both modes: in Servicios the % is hours booked over hours open,
 * in Aforo the mean occupancy of its open slots — the API says which.
 */
export function MonthGrid({
  month,
  days,
  today,
  onDay,
  t,
  locale,
}: {
  month: LocalDate;
  days: DayOccupancy[];
  today: LocalDate;
  onDay: (d: LocalDate) => void;
  t: T;
  locale: Locale;
}) {
  const { colors, radius } = useTheme();
  const weeks = monthGrid(month);
  const letters = t("reservas.weekdays").split(",");
  return (
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
            const o = days.find((x) => x.date === d);
            const closed = o?.closed ?? false;
            const pct = o?.pct ?? null;
            return (
              <Pressable
                key={d}
                accessibilityRole="button"
                accessibilityLabel={
                  closed ? t("reservas.month.cell.closed", { day: dayTitle(d, locale) }) : t("reservas.month.cell", { day: dayTitle(d, locale), pct: pct ?? 0 })
                }
                onPress={() => onDay(d)}
                style={({ pressed }) => [
                  styles.cell,
                  styles.day,
                  { borderRadius: radius.md, backgroundColor: pressed ? colors.muted : "transparent", borderColor: d === today ? colors.primaryText : "transparent" },
                ]}
              >
                <Text variant="subhead" tone={closed ? "mutedForeground" : "foreground"} maxFontSizeMultiplier={1.3}>
                  {dayNumber(d)}
                </Text>
                <View style={[styles.track, { backgroundColor: colors.muted, borderRadius: radius.sm }]}>
                  {!closed && pct ? <View style={[styles.fill, { width: `${Math.min(100, pct)}%`, backgroundColor: pct >= 85 ? colors.warningSolid : colors.positive }]} /> : null}
                </View>
                {/* A seventh of a phone: the word shrinks to fit rather than end in «…». */}
                <Text variant="caption" tone="mutedForeground" numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7} maxFontSizeMultiplier={1.2}>
                  {closed ? t("reservas.month.closed") : pct !== null ? t("reservas.month.pct", { pct }) : ""}
                </Text>
              </Pressable>
            );
          })}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: StyleSheet.hairlineWidth * 2, padding: 8, gap: 4 },
  row: { flexDirection: "row", gap: 2 },
  letter: { flex: 1, textAlign: "center", paddingVertical: 4 },
  cell: { flex: 1, minWidth: 0 },
  day: { alignItems: "center", gap: 3, paddingVertical: 6, minHeight: 56, borderWidth: 2 },
  track: { width: "70%", height: 4, overflow: "hidden" },
  fill: { height: "100%" },
});
