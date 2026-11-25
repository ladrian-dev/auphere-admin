import { useMemo } from "react";
import { PanResponder, Pressable, StyleSheet, View } from "react-native";

import type { ResConfig } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { addDays, addMonths, isClosed, weekStart, type LocalDate } from "@/lib/reservas-model";
import { haptics } from "@/motion/haptics";
import { MIN_TARGET, RADII, slopFor, TOUCH, useTheme } from "@/theme/theme";
import { Segmented } from "@/ui/bits";
import { Button, IconButton } from "@/ui/button";
import { Icon, icons, type IconName } from "@/ui/icon";
import { Text } from "@/ui/text";

import { dayNumber, dayTitle, monthTitle, stripWeekday, weekRange } from "./format";

export type Period = "day" | "week" | "month";
export type DayView = "list" | "grid";

/**
 * The top of Reservas (spec 044, R2.2–R2.4, R3.4; spec 069, R13.1, design
 * §4.1, §4.3): the period (Día, Semana, Mes); in the day, the week of the
 * chosen day as a strip — the chosen one in ink, today in turquoise with no
 * circle (the design's third «hoy»), a dot under days with bookings, the
 * closed ones struck through — then the day's title with «Hoy» to go back and,
 * in Servicios, list or grid. A swipe on the strip changes the week; each day
 * also carries «Semana anterior» and «Semana siguiente» as actions for the
 * screen reader (R3.4). In the week and the month, the range and its arrows.
 */
export function DayHeader({
  period,
  onPeriod,
  date,
  today,
  onDate,
  config,
  view,
  onView,
  marks,
  t,
  locale,
}: {
  period: Period;
  onPeriod: (p: Period) => void;
  date: LocalDate;
  today: LocalDate;
  onDate: (d: LocalDate) => void;
  config: ResConfig;
  view: DayView;
  onView: (v: DayView) => void;
  /** Days with at least one booking that is not cancelled: their dot. */
  marks?: ReadonlySet<LocalDate>;
  t: T;
  locale: Locale;
}) {
  return (
    <View style={styles.stack}>
      <Segmented
        label={t("reservas.period")}
        value={period}
        onChange={(p) => {
          if (p !== period) haptics.select();
          onPeriod(p);
        }}
        options={[
          { value: "day", label: t("reservas.period.day") },
          { value: "week", label: t("reservas.period.week") },
          { value: "month", label: t("reservas.period.month") },
        ]}
      />
      {period === "day" ? (
        <>
          <WeekStrip date={date} today={today} onDate={onDate} config={config} marks={marks} t={t} locale={locale} />
          <View style={styles.titleRow}>
            <Text variant="headline" accessibilityRole="header" style={styles.flex}>
              {date === today ? t("reservas.day.today", { day: dayTitle(date, locale) }) : dayTitle(date, locale)}
            </Text>
            {date !== today ? (
              <Button
                label={t("reservas.today")}
                variant="secondary"
                compact
                icon={icons.google}
                accessibilityLabel={t("reservas.today.back")}
                onPress={() => {
                  haptics.light();
                  onDate(today);
                }}
              />
            ) : null}
            {config.mode === "services" ? <ViewToggle value={view} onChange={onView} t={t} /> : null}
          </View>
        </>
      ) : (
        <View style={styles.titleRow}>
          <IconButton
            icon={icons.back}
            label={t(period === "week" ? "reservas.prev.week" : "reservas.prev.month")}
            onPress={() => {
              haptics.select();
              onDate(period === "week" ? addDays(weekStart(date), -7) : addMonths(date, -1));
            }}
          />
          <View style={[styles.flex, styles.navTitle]}>
            <Text variant="headline" accessibilityRole="header" style={styles.center}>
              {period === "week" ? weekRange(weekStart(date), locale, t) : monthTitle(date, locale)}
            </Text>
            {(period === "week" ? weekStart(date) !== weekStart(today) : date.slice(0, 7) !== today.slice(0, 7)) ? (
              <Button
                label={t("reservas.today")}
                variant="secondary"
                compact
                accessibilityLabel={t("reservas.today.back")}
                onPress={() => {
                  haptics.light();
                  onDate(today);
                }}
              />
            ) : null}
          </View>
          <IconButton
            icon={icons.chevron}
            label={t(period === "week" ? "reservas.next.week" : "reservas.next.month")}
            onPress={() => {
              haptics.select();
              onDate(period === "week" ? addDays(weekStart(date), 7) : addMonths(date, 1));
            }}
          />
        </View>
      )}
    </View>
  );
}

/** List or grid (design §4.1 5b): two icons in a track, the chosen one raised; a radio group named «Vista». */
function ViewToggle({ value, onChange, t }: { value: DayView; onChange: (v: DayView) => void; t: T }) {
  const { colors } = useTheme();
  const options: { value: DayView; label: string; icon: IconName }[] = [
    { value: "list", label: t("reservas.view.list"), icon: icons.list },
    { value: "grid", label: t("reservas.view.grid"), icon: icons.grid },
  ];
  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={t("reservas.view")} style={[styles.toggle, { backgroundColor: colors.muted }]}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="radio"
            accessibilityLabel={o.label}
            accessibilityState={{ checked: on }}
            onPress={() => {
              if (!on) haptics.select();
              onChange(o.value);
            }}
            hitSlop={slopFor(36)}
            style={[styles.toggleButton, { backgroundColor: on ? colors.card : "transparent", borderColor: on ? colors.controlBorder : "transparent" }]}
          >
            <Icon name={o.icon} size={18} tone={on ? "foreground" : "mutedForeground"} />
          </Pressable>
        );
      })}
    </View>
  );
}

/** A swipe longer than this, and more across than down, changes the week. */
const SWIPE = 40;

function WeekStrip({
  date,
  today,
  onDate,
  config,
  marks,
  t,
  locale,
}: {
  date: LocalDate;
  today: LocalDate;
  onDate: (d: LocalDate) => void;
  config: ResConfig;
  marks?: ReadonlySet<LocalDate>;
  t: T;
  locale: Locale;
}) {
  const { colors } = useTheme();
  const from = weekStart(date);
  const days = Array.from({ length: 7 }, (_, i) => addDays(from, i));
  const shift = (n: number) => {
    haptics.select();
    onDate(addDays(date, n));
  };
  // Remade only when the day changes (after a swipe has ended), so no gesture is cut in two.
  // Its handlers run when the finger lifts, never during render.
  const pan = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dx) > 12 && Math.abs(g.dx) > Math.abs(g.dy) * 1.5,
        onPanResponderRelease: (_, g) => {
          if (Math.abs(g.dx) >= SWIPE) {
            haptics.select();
            onDate(addDays(date, g.dx < 0 ? 7 : -7));
          }
        },
      }),
    [date, onDate],
  );
  const actions = [
    { name: "previousWeek", label: t("reservas.prev.week") },
    { name: "nextWeek", label: t("reservas.next.week") },
  ];

  return (
    <View style={styles.strip} accessibilityLabel={t("reservas.days")} {...pan.panHandlers} testID="week-strip">
      {days.map((d) => {
        const on = d === date;
        const isToday = d === today;
        const closed = isClosed(config, d);
        const marked = marks?.has(d) ?? false;
        const said = t(isToday ? "reservas.day.a11y.today" : closed ? "reservas.day.a11y.closed" : "reservas.day.a11y", { day: dayTitle(d, locale) });
        // The dot is said too, as Mes does (review H07, WCAG 1.3.1).
        const label = marked ? t("v13.reservas.day.a11y.marked", { day: said }) : said;
        // Ink when chosen; turquoise for today, without a circle (design v3, app.css:1606); the rest in their ink.
        const numberTone = on ? "onSelection" : isToday ? "highlightInk" : closed ? "mutedForeground" : "foreground";
        return (
          <Pressable
            key={d}
            accessibilityRole="button"
            accessibilityLabel={label}
            accessibilityState={{ selected: on }}
            accessibilityActions={actions}
            onAccessibilityAction={(e) => shift(e.nativeEvent.actionName === "nextWeek" ? 7 : -7)}
            onPress={() => {
              if (!on) haptics.select();
              onDate(d);
            }}
            android_ripple={{ color: colors.muted }}
            style={({ pressed }) => [styles.day, { backgroundColor: on ? colors.selection : pressed ? colors.muted : "transparent" }]}
            testID={`strip-${d}`}
          >
            <Text variant="caption" tone={on ? "onSelection" : isToday ? "highlightInk" : "mutedForeground"} maxFontSizeMultiplier={1.4} numberOfLines={1}>
              {stripWeekday(d, isToday, t, locale)}
            </Text>
            {/* Closed: the softer ink at 4.5:1 or more, and struck through — never colour alone (gate review). */}
            <Text variant="bodyStrong" tone={numberTone} style={[styles.num, closed ? styles.closed : null]} maxFontSizeMultiplier={1.4}>
              {dayNumber(d)}
            </Text>
            <View
              testID={marked ? `strip-dot-${d}` : undefined}
              style={[styles.dot, { backgroundColor: marked ? (on ? colors.onSelection : colors.highlightInk) : "transparent" }]}
            />
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 12 },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  navTitle: { alignItems: "center", gap: 6 },
  flex: { flex: 1, minWidth: 0 },
  center: { textAlign: "center" },
  strip: { flexDirection: "row", gap: 4 },
  day: { flex: 1, minWidth: 0, minHeight: Math.max(64, TOUCH), alignItems: "center", justifyContent: "center", gap: 1, borderRadius: RADII.lg + 2, paddingVertical: 6 },
  num: { fontVariant: ["tabular-nums"] },
  dot: { width: 5, height: 5, borderRadius: 3, marginTop: 2 },
  closed: { textDecorationLine: "line-through" },
  toggle: { flexDirection: "row", padding: 2, borderRadius: RADII.lg + 2 },
  // 36 tall with the slop above and below; as wide as the platform's minimum (R3.3: 48 dp on Android).
  toggleButton: { minWidth: MIN_TARGET, minHeight: 36, alignItems: "center", justifyContent: "center", borderRadius: RADII.lg, borderWidth: 1 },
});
