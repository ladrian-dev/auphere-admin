import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import type { DayOccupancy, Reservation, ResConfig, Slot } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { addDays, isClosed, occupancyLevel, slotsOfDay, type LocalDate } from "@/lib/reservas-model";
import { haptics } from "@/motion/haptics";
import { CARD_RADIUS, useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";
import { Group } from "@/ui/group";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import { dayNumber, dayShort, dayTitle, hhmm, weekdayShort } from "./format";

/** Cells of the week's meter: each is a tenth of the day's open hours. */
const METER = 10;

/**
 * Servicios · Semana (spec 044 R3.1; spec 069 R13.5, design §4.6): one row
 * per day — the day of the week and its number (today in turquoise, without a
 * circle), «N reservas» or «Cerrado», and a meter of how full it is (booked
 * hours over open hours, the API's figure; the share is also said in words).
 * A row takes you to that day.
 */
export function WeekServices({
  config,
  items,
  days: occupancy = [],
  from,
  today,
  onDay,
  t,
  locale,
}: {
  config: ResConfig;
  items: Reservation[];
  /** The occupancy of each day (`occupancy` of the week). */
  days?: DayOccupancy[];
  from: LocalDate;
  today?: LocalDate;
  /** Kept for the callers of spec 044: the week now leads to the day, where each booking opens. */
  onOpen?: (r: Reservation) => void;
  onDay: (d: LocalDate) => void;
  t: T;
  locale: Locale;
}) {
  const { colors } = useTheme();
  const days = Array.from({ length: 7 }, (_, i) => addDays(from, i));
  return (
    <View style={[styles.rows, { backgroundColor: colors.card, borderColor: colors.border }]}>
      {days.map((d, i) => {
        const live = items.filter((r) => r.date === d && r.state !== "cancelled").length;
        const closed = isClosed(config, d) && live === 0;
        const pct = occupancy.find((o) => o.date === d)?.pct ?? 0;
        const count = live === 1 ? t("reservas.day.count.one") : t("reservas.day.count", { n: live });
        const isToday = d === today;
        const filled = Math.min(METER, Math.round((pct / 100) * METER));
        return (
          <Pressable
            key={d}
            accessibilityRole="button"
            accessibilityLabel={closed ? t("reservas.week.row.closed", { day: dayTitle(d, locale) }) : t("reservas.week.row", { day: dayTitle(d, locale), count, pct })}
            onPress={() => {
              haptics.select();
              onDay(d);
            }}
            android_ripple={{ color: colors.muted }}
            testID={`week-${d}`}
            style={({ pressed }) => [styles.weekRow, i > 0 ? { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border } : null, pressed ? { backgroundColor: colors.muted } : null]}
          >
            <View style={styles.dn}>
              <Text variant="caption" tone={isToday ? "highlightInk" : "mutedForeground"} maxFontSizeMultiplier={1.4} numberOfLines={1}>
                {isToday ? t("reservas.today").toLocaleLowerCase(locale) : weekdayShort(d, locale)}
              </Text>
              <Text variant="headline" tone={isToday ? "highlightInk" : closed ? "mutedForeground" : "foreground"} style={styles.num} maxFontSizeMultiplier={1.4}>
                {dayNumber(d)}
              </Text>
            </View>
            <View style={styles.flex}>
              <Text variant="subhead" tone={closed ? "mutedForeground" : "foreground"}>
                {closed ? t("reservas.month.closed") : count}
              </Text>
              {!closed ? (
                <View style={styles.meter} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
                  {Array.from({ length: METER }, (_, k) => (
                    <View key={k} style={[styles.cellMeter, { backgroundColor: k < filled ? colors.primary : colors.muted }]} />
                  ))}
                </View>
              ) : null}
            </View>
            <Icon name={icons.chevron} size={18} tone="subtle" />
          </Pressable>
        );
      })}
    </View>
  );
}

/** Each step of occupancy and the ink of its number: 4.5:1 or more in both themes (test). */
export const WEEK_LEVELS: Record<0 | 1 | 2 | 3 | "full", { bg: keyof Palette; fg: keyof Palette }> = {
  0: { bg: "muted", fg: "foreground" },
  1: { bg: "positiveBg", fg: "foreground" },
  2: { bg: "accentSoft", fg: "accentDeep" },
  3: { bg: "positive", fg: "onHighlight" }, // 7.4:1; the light ink was 2.1 in light (review H04)
  full: { bg: "accentDeep", fg: "accentSoft" }, // 5:1; on primaryDeep it was 4.2 (gate review)
};

/**
 * Aforo · Semana (spec 044, R3.2, research D9): a heat map of days by arrival
 * times. Each cell says how many are inside, in five steps of occupancy (and
 * the number always, never the colour alone); blocked ones are striped. A
 * cell takes you to its day with that slot filtered.
 */
export function WeekHeat({
  config,
  slots,
  from,
  onCell,
  t,
  locale,
}: {
  config: ResConfig;
  slots: Slot[];
  from: LocalDate;
  onCell: (d: LocalDate, time: number) => void;
  t: T;
  locale: Locale;
}) {
  const { colors, radius } = useTheme();
  const days = Array.from({ length: 7 }, (_, i) => addDays(from, i));
  const times = [...new Set((config.capacity?.shifts ?? []).flatMap((s) => {
    const out: number[] = [];
    for (let m = s.from; m <= s.to; m += s.everyMin) out.push(m);
    return out;
  }))].sort((a, b) => a - b);

  return (
    <Group>
      <View style={styles.heatWrap}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View>
            <View style={styles.heatRow}>
              <View style={styles.heatDay} />
              {times.map((m) => (
                <Text key={m} variant="caption" tone="mutedForeground" style={styles.heatHead} maxFontSizeMultiplier={1.3} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7}>
                  {hhmm(m)}
                </Text>
              ))}
            </View>
            {days.map((d) => {
              const open = new Set(slotsOfDay(config, d).map((s) => s.time));
              return (
                <View key={d} style={styles.heatRow}>
                  <Text variant="caption" tone="mutedForeground" style={styles.heatDay} maxFontSizeMultiplier={1.3}>
                    {dayShort(d, locale)}
                  </Text>
                  {times.map((m) => {
                    const s = slots.find((x) => x.date === d && x.time === m);
                    if (!open.has(m) || !s) {
                      return (
                        <View key={m} style={[styles.cell, { borderRadius: radius.sm }]} importantForAccessibility="no" accessibilityElementsHidden>
                          <Text variant="caption" tone="subtle">
                            –
                          </Text>
                        </View>
                      );
                    }
                    const level = WEEK_LEVELS[occupancyLevel(s.inside, s.capacity)];
                    return (
                      <Pressable
                        key={m}
                        accessibilityRole="button"
                        accessibilityLabel={
                          s.blocked
                            ? t("reservas.heat.cell.blocked", { day: dayTitle(d, locale), time: hhmm(m) })
                            : t("reservas.heat.cell", { day: dayTitle(d, locale), time: hhmm(m), inside: s.inside, capacity: s.capacity })
                        }
                        onPress={() => onCell(d, m)}
                        style={({ pressed }) => [
                          styles.cell,
                          {
                            borderRadius: radius.sm,
                            backgroundColor: s.blocked ? colors.card : pressed ? colors.muted : colors[level.bg],
                            borderWidth: s.blocked ? 2 : 0,
                            borderStyle: "dashed",
                            borderColor: colors.subtle,
                          },
                        ]}
                      >
                        <Text variant="caption" tone={s.blocked ? "mutedForeground" : level.fg} style={styles.num} maxFontSizeMultiplier={1.3}>
                          {s.blocked ? "×" : String(s.inside)}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              );
            })}
          </View>
        </ScrollView>
        <Text variant="footnote" tone="mutedForeground">
          {t("reservas.heat.legend")}
        </Text>
      </View>
    </Group>
  );
}

const styles = StyleSheet.create({
  rows: { borderWidth: StyleSheet.hairlineWidth * 2, borderRadius: CARD_RADIUS, overflow: "hidden" },
  weekRow: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 14, paddingVertical: 12, minHeight: 56 },
  dn: { width: 44, alignItems: "center" },
  flex: { flex: 1, minWidth: 0 },
  meter: { flexDirection: "row", gap: 3, marginTop: 6 },
  cellMeter: { width: 14, height: 6, borderRadius: 3 },
  heatWrap: { padding: 12, gap: 12 },
  heatRow: { flexDirection: "row", alignItems: "center", gap: 4, marginBottom: 4 },
  heatDay: { width: 52 },
  heatHead: { width: 40, textAlign: "center" },
  cell: { width: 40, height: 36, alignItems: "center", justifyContent: "center" },
  num: { fontVariant: ["tabular-nums"] },
});
