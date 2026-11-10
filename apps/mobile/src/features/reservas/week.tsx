import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import type { Reservation, ResConfig, Slot } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { addDays, isClosed, occupancyLevel, slotsOfDay, type LocalDate } from "@/lib/reservas-model";
import { CARD_RADIUS, useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";
import { Group } from "@/ui/group";
import { Text } from "@/ui/text";

import { ListCard, ServicesRow } from "./day-services";
import { dayShort, dayTitle, hhmm } from "./format";

/**
 * Servicios · Semana (spec 044, R3.1): a card per day — «N reservas» or
 * «Cerrado» — with its rows, no grid. The title of each day takes you to it.
 */
export function WeekServices({
  config,
  items,
  from,
  onOpen,
  onDay,
  t,
  locale,
}: {
  config: ResConfig;
  items: Reservation[];
  from: LocalDate;
  onOpen: (r: Reservation) => void;
  onDay: (d: LocalDate) => void;
  t: T;
  locale: Locale;
}) {
  const { colors } = useTheme();
  const days = Array.from({ length: 7 }, (_, i) => addDays(from, i));
  return (
    <View style={styles.stack}>
      {days.map((d) => {
        const list = items.filter((r) => r.date === d).sort((a, b) => a.start - b.start);
        const live = list.filter((r) => r.state !== "cancelled").length;
        const closed = isClosed(config, d) && list.length === 0;
        const title = closed
          ? t("reservas.week.closed", { day: dayTitle(d, locale) })
          : live === 1
            ? t("reservas.week.day.one", { day: dayTitle(d, locale) })
            : t("reservas.week.day", { day: dayTitle(d, locale), n: live });
        return (
          <View key={d} style={styles.day}>
            <Pressable accessibilityRole="button" onPress={() => onDay(d)} hitSlop={6} style={styles.dayHead}>
              <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
                {title}
              </Text>
            </Pressable>
            {list.length > 0 ? (
              <ListCard>
                {list.map((r, i) => (
                  <ServicesRow key={r.id} r={r} past={false} first={i === 0} config={config} t={t} locale={locale} onOpen={onOpen} />
                ))}
              </ListCard>
            ) : !closed ? (
              <View style={[styles.empty, { borderColor: colors.border, borderRadius: CARD_RADIUS }]}>
                <Text variant="footnote" tone="mutedForeground">
                  {t("reservas.week.empty")}
                </Text>
              </View>
            ) : null}
          </View>
        );
      })}
    </View>
  );
}

const LEVEL: Record<0 | 1 | 2 | 3 | "full", { bg: keyof Palette; fg: keyof Palette }> = {
  0: { bg: "muted", fg: "foreground" },
  1: { bg: "positiveBg", fg: "foreground" },
  2: { bg: "accentSoft", fg: "accentDeep" },
  3: { bg: "positive", fg: "primaryForeground" },
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
                    const level = LEVEL[occupancyLevel(s.inside, s.capacity)];
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
  stack: { gap: 16 },
  day: { gap: 8 },
  dayHead: { minHeight: 32, justifyContent: "center" },
  empty: { borderWidth: StyleSheet.hairlineWidth * 2, borderStyle: "dashed", padding: 12 },
  heatWrap: { padding: 12, gap: 12 },
  heatRow: { flexDirection: "row", alignItems: "center", gap: 4, marginBottom: 4 },
  heatDay: { width: 52 },
  heatHead: { width: 40, textAlign: "center" },
  cell: { width: 40, height: 36, alignItems: "center", justifyContent: "center" },
  num: { fontVariant: ["tabular-nums"] },
});
