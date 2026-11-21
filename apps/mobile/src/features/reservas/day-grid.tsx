import { Fragment } from "react";
import { Pressable, StyleSheet, useWindowDimensions, View } from "react-native";
import Animated from "react-native-reanimated";

import type { Reservation, ResConfig } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { earliestFrom, freeBands, isClosed, openSpans, sideBySide, type LocalDate, type Minutes, type WallTime } from "@/lib/reservas-model";
import { haptics } from "@/motion/haptics";
import { useArrival } from "@/motion/micro";
import { RADII, slopFor, useTheme } from "@/theme/theme";
import { Button } from "@/ui/button";
import { Icon, icons } from "@/ui/icon";
import { pillOf } from "@/ui/pill";
import { EmptyState } from "@/ui/states";
import { Text } from "@/ui/text";

import { TeamChips } from "./day-services";
import { firstName, hhmm, nameOf, spoken } from "./format";

/** Past this text size the grid says the list reads better (research D8). */
const LARGE = 1.5;
/** The hours' column (design §4.5: 50). */
const GUTTER = 50;
/** One hour, at the default text size (design §4.5: 72). */
const HOUR = 72;
/** Shorter than this a block has one line; shorter than `MID_MIN`, two (design `.sm` 30 min, `.md` 45 min). */
const SMALL_MIN = 40;
const MID_MIN = 60;

/**
 * Servicios · Día · Cuadrícula (spec 044 R2.6; spec 069 R13.2–R13.4, design
 * §4.5): only the hours the business opens, each a track with its hour lines,
 * the break between them said in words, each reservation as tall as it lasts,
 * the ones at the same time side by side, and the line of «ahora» in the
 * brand's green. The free time is a dashed band that books it: a tap opens
 * «Nueva reserva» at that day and time (R13.3) — never in the past or inside
 * the agent's notice (R13.4). With one person chosen, it is their day. A view
 * of the whole day, not the one that tells everything: each block is a button
 * with the same sentence as its card, and with very large text it offers the
 * list.
 */
export function DayGrid({
  config,
  items,
  now,
  date,
  onOpen,
  onList,
  pro = null,
  onPro,
  onFree,
  arrivedId = null,
  t,
}: {
  config: ResConfig;
  items: Reservation[];
  now: WallTime;
  date: LocalDate;
  onOpen: (r: Reservation) => void;
  onList: () => void;
  /** The team member shown, or everyone. */
  pro?: string | null;
  onPro?: (id: string | null) => void;
  /** A free band was tapped: book at that time (with that person, when one is chosen). */
  onFree?: (date: LocalDate, time: Minutes, proId: string | null) => void;
  arrivedId?: string | null;
  t: T;
  /** Kept for the callers of spec 044. */
  locale?: Locale;
}) {
  const { colors } = useTheme();
  const { fontScale } = useWindowDimensions();
  const team = config.services?.team ?? [];
  const spans = openSpans(config, date);
  const chips = team.length > 1 ? <TeamChips team={team} pro={pro} onPro={onPro ?? (() => undefined)} t={t} /> : null;
  if (spans.length === 0 || isClosed(config, date)) {
    return (
      <View style={styles.stack}>
        {chips}
        <EmptyState icon={icons.moon} title={t("reservas.day.closed")} />
      </View>
    );
  }

  const hour = HOUR * Math.min(Math.max(fontScale, 1), 1.6);
  const shown = items.filter((r) => r.date === date && r.state !== "cancelled" && (pro === null || r.pro?.id === pro));
  const earliest = earliestFrom(now, config.agent?.minNoticeMin ?? 60);
  const bands = onFree ? freeBands(spans, shown, config.services?.stepMin ?? 30, date, earliest) : [];
  const today = date === now.date;

  return (
    <View style={styles.stack}>
      {chips}
      {fontScale >= LARGE ? (
        <View style={styles.large}>
          <Text variant="callout" tone="mutedForeground" style={styles.flex}>
            {t("reservas.grid.large")}
          </Text>
          <Button label={t("reservas.grid.toList")} variant="secondary" compact onPress={onList} />
        </View>
      ) : null}
      {spans.map((span, i) => {
        const open = span.open;
        const y = (m: Minutes) => ((m - open) / 60) * hour;
        const height = y(span.close);
        const hours: Minutes[] = [];
        for (let m = Math.ceil(open / 60) * 60; m <= span.close; m += 60) hours.push(m);
        const halves: Minutes[] = [];
        for (let m = Math.ceil(open / 30) * 30; m < span.close; m += 30) if (m % 60 !== 0) halves.push(m);
        const inside = shown.filter((r) => r.start < span.close && r.end > open);
        const prev = spans[i - 1];
        return (
          <Fragment key={span.open}>
            {prev ? (
              <View style={[styles.break, { backgroundColor: colors.muted }]} accessibilityRole="text">
                <Icon name={icons.clock} size={15} tone="mutedForeground" />
                <Text variant="footnote" tone="mutedForeground" style={styles.flex}>
                  {t("reservas.grid.break", { from: hhmm(prev.close), to: hhmm(span.open) })}
                </Text>
              </View>
            ) : null}
            <View style={[styles.track, { height }]} testID={`grid-span-${hhmm(span.open)}`}>
              {hours.map((m) => (
                <Fragment key={`h${m}`}>
                  <View style={[styles.rule, { top: y(m), backgroundColor: colors.border }]} />
                  <Text
                    variant="caption"
                    tone="mutedForeground"
                    style={[styles.hour, { top: y(m) - 8 }]}
                    maxFontSizeMultiplier={1.4}
                    importantForAccessibility="no"
                    accessibilityElementsHidden
                  >
                    {hhmm(m)}
                  </Text>
                </Fragment>
              ))}
              {halves.map((m) => (
                <View key={`m${m}`} style={[styles.rule, { top: y(m), backgroundColor: colors.borderSoft }]} />
              ))}
              {bands
                .filter((b) => b.from >= open && b.to <= span.close)
                .map((b) => (
                  <FreeBand key={b.from} from={b.from} to={b.to} top={y(b.from) + 2} height={Math.max(32, y(b.to) - y(b.from) - 4)} onPress={() => onFree?.(date, b.from, pro)} t={t} />
                ))}
              {sideBySide(inside).map(({ r, column, columns }) => (
                <Block
                  key={r.id}
                  r={r}
                  top={y(Math.max(r.start, open)) + 2}
                  height={Math.max(32, ((Math.min(r.end, span.close) - Math.max(r.start, open)) / 60) * hour - 4)}
                  column={column}
                  columns={columns}
                  arrives={r.id === arrivedId}
                  t={t}
                  onOpen={onOpen}
                />
              ))}
              {today && now.minutes >= open && now.minutes <= span.close ? (
                <View pointerEvents="none" importantForAccessibility="no-hide-descendants" accessibilityElementsHidden style={[styles.now, { top: y(now.minutes) - 1 }]}>
                  <View style={[styles.nowPill, { backgroundColor: colors.highlight }]}>
                    <Text variant="caption" tone="onHighlight" style={styles.num} maxFontSizeMultiplier={1.2}>
                      {hhmm(now.minutes)}
                    </Text>
                  </View>
                  <View style={[styles.nowRule, { backgroundColor: colors.highlight }]} />
                </View>
              ) : null}
            </View>
          </Fragment>
        );
      })}
    </View>
  );
}

function FreeBand({ from, to, top, height, onPress, t }: { from: Minutes; to: Minutes; top: number; height: number; onPress: () => void; t: T }) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={t("reservas.grid.free.a11y", { from: hhmm(from), to: hhmm(to) })}
      onPress={() => {
        haptics.light();
        onPress();
      }}
      // A half hour is 32 pt tall: the slop takes it to 44 pt on iOS and 48 dp on Android (R3.3).
      hitSlop={slopFor(height)}
      testID={`free-${hhmm(from)}`}
      style={({ pressed }) => [styles.free, { top, height, borderColor: colors.controlBorder, backgroundColor: pressed ? colors.muted : "transparent" }]}
    >
      <Icon name={icons.plus} size={16} tone="highlightInk" />
      <Text variant="footnote" tone="primaryText" style={[styles.num, styles.flex]} numberOfLines={1} maxFontSizeMultiplier={1.3}>
        {t("reservas.grid.free", { from: hhmm(from), to: hhmm(to) })}
      </Text>
    </Pressable>
  );
}

function Block({
  r,
  top,
  height,
  column,
  columns,
  arrives,
  t,
  onOpen,
}: {
  r: Reservation;
  top: number;
  height: number;
  column: number;
  columns: number;
  arrives: boolean;
  t: T;
  onOpen: (r: Reservation) => void;
}) {
  const { colors } = useTheme();
  const arrival = useArrival();
  const look = pillOf(r, "services", null, t);
  const pending = r.state === "pending";
  const muted = r.state === "done" || r.state === "noshow";
  const time = pending ? "warningText" : muted ? "mutedForeground" : "foreground";
  // By length, as the design sizes them (30 min one line, 45 min two): the hour grows with the text, so do they.
  const minutes = r.end - r.start;
  const size = minutes < SMALL_MIN ? "sm" : minutes < MID_MIN ? "md" : "lg";
  const width = `${100 / columns}%` as const;
  const left = `${(100 / columns) * column}%` as const;
  const what = [r.service?.name, r.pro ? firstName(r.pro.name) : null].filter(Boolean).join(" · ");
  return (
    <Animated.View entering={arrives ? arrival.entering : undefined} style={[styles.blockSlot, { top, height, left, width }]}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={spoken(r, look.label, t, "")}
        onPress={() => onOpen(r)}
        hitSlop={slopFor(height)}
        testID={`block-${r.id}`}
        style={({ pressed }) => [
          styles.block,
          size === "sm" ? styles.blockSm : null,
          {
            backgroundColor: pressed ? colors.muted : pending ? colors.warningBg : colors.card,
            borderColor: pending ? colors.warningSolid : colors.controlBorder,
            borderStyle: pending ? "dashed" : "solid",
            transform: [{ scale: pressed ? 0.98 : 1 }],
          },
        ]}
      >
        {size === "sm" ? (
          // A half hour has room for one line: the time and who (first iOS pass); a pending one also shows its clock.
          <View style={styles.line}>
            {pending ? <Icon name={icons.clock} size={12} tone="warningText" /> : null}
            <Text variant="caption" tone={time} numberOfLines={1} maxFontSizeMultiplier={1.3} style={styles.flex}>
              {`${hhmm(r.start)} · ${firstName(nameOf(r, t))}`}
            </Text>
          </View>
        ) : (
          <>
            <View style={styles.line}>
              {pending ? <Icon name={icons.clock} size={12} tone="warningText" /> : null}
              <Text variant="caption" tone={time} style={styles.num} numberOfLines={1} maxFontSizeMultiplier={1.3}>
                {`${hhmm(r.start)}–${hhmm(r.end)}`}
              </Text>
            </View>
            <Text variant="footnote" tone={muted ? "mutedForeground" : "foreground"} numberOfLines={1} maxFontSizeMultiplier={1.3} style={styles.name}>
              {nameOf(r, t)}
            </Text>
            {size === "lg" ? (
              <Text variant="caption" tone="mutedForeground" numberOfLines={1} maxFontSizeMultiplier={1.3}>
                {pending ? `${look.label} · ${what}` : what}
              </Text>
            ) : null}
          </>
        )}
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 12 },
  flex: { flex: 1, minWidth: 0 },
  num: { fontVariant: ["tabular-nums"] },
  large: { flexDirection: "row", alignItems: "center", gap: 12, flexWrap: "wrap" },
  track: { marginLeft: GUTTER, marginTop: 8 },
  rule: { position: "absolute", left: 0, right: 0, height: StyleSheet.hairlineWidth },
  hour: { position: "absolute", left: -GUTTER, width: GUTTER - 10, textAlign: "right" },
  break: { flexDirection: "row", alignItems: "center", gap: 8, marginLeft: GUTTER + 6, paddingHorizontal: 12, paddingVertical: 9, borderRadius: RADII.md },
  free: {
    position: "absolute",
    left: 6,
    right: 0,
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 6,
    paddingHorizontal: 12,
    paddingTop: 8,
    borderWidth: 1.5,
    borderStyle: "dashed",
    borderRadius: RADII.md,
  },
  blockSlot: { position: "absolute", paddingLeft: 6, zIndex: 1 },
  block: { flex: 1, borderRadius: RADII.md, borderWidth: 1, paddingLeft: 10, paddingRight: 8, paddingVertical: 4, overflow: "hidden", justifyContent: "center", gap: 1 },
  blockSm: { paddingVertical: 0 },
  line: { flexDirection: "row", alignItems: "center", gap: 4 },
  name: { fontWeight: "600" },
  now: { position: "absolute", left: -GUTTER + 2, right: 0, flexDirection: "row", alignItems: "center", zIndex: 3 },
  nowPill: { borderRadius: RADII.sm, paddingHorizontal: 6, marginRight: 2 },
  nowRule: { flex: 1, height: 2, borderRadius: 1 },
});
