import { Pressable, ScrollView, StyleSheet, useWindowDimensions, View } from "react-native";

import type { Reservation, ResConfig } from "@/api/reservas";
import { initialsOf } from "@/features/inbox/model";
import type { Locale, T } from "@/i18n/t";
import { isClosed, openSpan, type LocalDate, type WallTime } from "@/lib/reservas-model";
import { CARD_RADIUS, concentric, useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";
import { Avatar } from "@/ui/bits";
import { Button } from "@/ui/button";
import { icons } from "@/ui/icon";
import { pillOf } from "@/ui/pill";
import { EmptyState } from "@/ui/states";
import { Text } from "@/ui/text";

import { firstName, hhmm, nameOf, spoken } from "./format";

/** Past this text size the grid says the list reads better (research D8). */
const LARGE = 1.5;
const GUTTER = 44;
const MIN_COLUMN = 120;

/**
 * Servicios · Día · Cuadrícula (spec 044, R2.6, research D8): a column per
 * team member, the hours of the day down the side, each reservation as tall
 * as it lasts and the line of «ahora». A view of the whole day, not the one
 * that tells everything: each block is a button with the same sentence as its
 * row, and with very large text it offers the list.
 */
export function DayGrid({
  config,
  items,
  now,
  date,
  onOpen,
  onList,
  t,
  locale,
}: {
  config: ResConfig;
  items: Reservation[];
  now: WallTime;
  date: LocalDate;
  onOpen: (r: Reservation) => void;
  onList: () => void;
  t: T;
  locale: Locale;
}) {
  const { colors } = useTheme();
  const { width, fontScale } = useWindowDimensions();
  const team = config.services?.team ?? [];
  const span = openSpan(config, date);
  if (!span || isClosed(config, date)) return <EmptyState icon={icons.calendar} title={t("reservas.day.closed")} />;

  const hour = 52 * Math.min(Math.max(fontScale, 1), 1.6);
  const open = Math.floor(span.open / 60) * 60;
  const close = Math.ceil(span.close / 60) * 60;
  const height = ((close - open) / 60) * hour;
  const y = (m: number) => ((m - open) / 60) * hour;
  const columnWidth = Math.max(MIN_COLUMN, (width - 32 - GUTTER) / Math.max(1, team.length));
  const hours: number[] = [];
  for (let m = open; m < close; m += 60) hours.push(m);
  const today = date === now.date;

  return (
    <View style={styles.stack}>
      {fontScale >= LARGE ? (
        <View style={styles.large}>
          <Text variant="callout" tone="mutedForeground" style={styles.flex}>
            {t("reservas.grid.large")}
          </Text>
          <Button label={t("reservas.grid.toList")} variant="secondary" compact onPress={onList} />
        </View>
      ) : null}
      <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border, borderRadius: CARD_RADIUS }]}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View>
            <View style={[styles.heads, { paddingLeft: GUTTER }]}>
              {team.map((p) => (
                <View key={p.id} style={[styles.head, { width: columnWidth }]} accessibilityRole="header" accessibilityLabel={p.name}>
                  <Avatar initials={initialsOf(p.name)} size={28} />
                  <Text variant="subhead" numberOfLines={1} style={styles.flex}>
                    {firstName(p.name)}
                  </Text>
                </View>
              ))}
            </View>
            <View style={{ height, flexDirection: "row" }}>
              <View style={{ width: GUTTER }} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
                {hours.map((m) => (
                  <Text key={m} variant="caption" tone="mutedForeground" style={[styles.hour, { top: y(m) - 8 }]} maxFontSizeMultiplier={1.4}>
                    {hhmm(m)}
                  </Text>
                ))}
              </View>
              {team.map((p) => (
                <View key={p.id} style={[styles.column, { width: columnWidth, borderLeftColor: colors.border }]}>
                  {hours.map((m) => (
                    <View key={m} style={[styles.rule, { top: y(m), backgroundColor: colors.borderSoft }]} />
                  ))}
                  {items
                    .filter((r) => r.date === date && r.pro?.id === p.id && r.state !== "cancelled")
                    .map((r) => (
                      <Block key={r.id} r={r} top={y(r.start)} height={Math.max(((r.end - r.start) / 60) * hour - 2, 30)} now={now} t={t} locale={locale} onOpen={onOpen} />
                    ))}
                </View>
              ))}
              {today && now.minutes >= open && now.minutes <= close ? (
                <View pointerEvents="none" style={[styles.nowLine, { top: y(now.minutes), left: GUTTER - 4, backgroundColor: colors.danger }]} />
              ) : null}
            </View>
          </View>
        </ScrollView>
      </View>
    </View>
  );
}

function Block({
  r,
  top,
  height,
  now,
  t,
  locale,
  onOpen,
}: {
  r: Reservation;
  top: number;
  height: number;
  now: WallTime;
  t: T;
  locale: Locale;
  onOpen: (r: Reservation) => void;
}) {
  const { colors, radius } = useTheme();
  const running = r.date === now.date && r.start <= now.minutes && now.minutes < r.end && (r.state === "confirmed" || r.state === "pending");
  const look = pillOf(r, "services", null, t);
  const tone: { bg: keyof Palette; fg: keyof Palette; border?: keyof Palette } = running
    ? { bg: "accentDeep", fg: "accentSoft" }
    : r.state === "pending"
      ? { bg: "card", fg: "foreground", border: "warningSolid" }
      : r.state === "confirmed"
        ? { bg: "positiveBg", fg: "foreground" }
        : r.state === "noshow"
          ? { bg: "dangerBg", fg: "dangerText" }
          : { bg: "muted", fg: "mutedForeground" };
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={spoken(r, look.label, t, "")}
      onPress={() => onOpen(r)}
      style={({ pressed }) => [
        styles.block,
        {
          top,
          height,
          borderRadius: concentric(radius.md, 0),
          backgroundColor: pressed ? colors.muted : colors[tone.bg],
          borderColor: tone.border ? colors[tone.border] : "transparent",
          borderStyle: tone.border ? "dashed" : "solid",
        },
      ]}
    >
      {height >= 40 ? (
        <>
          <Text variant="caption" tone={tone.fg} numberOfLines={1} maxFontSizeMultiplier={1.3}>
            {hhmm(r.start)}
          </Text>
          <Text variant="footnote" tone={tone.fg} numberOfLines={height >= 64 ? 2 : 1} maxFontSizeMultiplier={1.3}>
            {nameOf(r, t)}
          </Text>
        </>
      ) : (
        // A half hour has room for one line: the time and who (first iOS pass).
        <Text variant="caption" tone={tone.fg} numberOfLines={1} maxFontSizeMultiplier={1.3}>
          {`${hhmm(r.start)} · ${firstName(nameOf(r, t))}`}
        </Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 12 },
  flex: { flex: 1, minWidth: 0 },
  large: { flexDirection: "row", alignItems: "center", gap: 12, flexWrap: "wrap" },
  card: { borderWidth: StyleSheet.hairlineWidth * 2, overflow: "hidden", paddingVertical: 12 },
  heads: { flexDirection: "row", paddingBottom: 8 },
  head: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 6 },
  hour: { position: "absolute", left: 6 },
  column: { borderLeftWidth: StyleSheet.hairlineWidth },
  rule: { position: "absolute", left: 0, right: 0, height: StyleSheet.hairlineWidth },
  block: { position: "absolute", left: 3, right: 3, paddingHorizontal: 6, paddingVertical: 3, borderWidth: 1, overflow: "hidden" },
  nowLine: { position: "absolute", right: 0, height: 2 },
});
