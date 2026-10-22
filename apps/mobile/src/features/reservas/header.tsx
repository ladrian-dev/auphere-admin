import { useEffect, useMemo, useRef, type ComponentRef } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import type { ResConfig } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { addDays, addMonths, isClosed, weekStart, type LocalDate } from "@/lib/reservas-model";
import { CARD_RADIUS, TOUCH, useTheme } from "@/theme/theme";
import { Segmented } from "@/ui/bits";
import { Button, IconButton } from "@/ui/button";
import { icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import { dayNumber, dayTitle, monthTitle, weekRange, weekdayShort } from "./format";

export type Period = "day" | "week" | "month";
export type DayView = "list" | "grid";

/**
 * The top of Reservas (spec 044, R2.2–R2.4, R3.4): the period (Día, Semana,
 * Mes) and, separately, the view (Lista or Cuadrícula, only in Servicios'
 * day) — the design keeps them apart. In the day, a strip of days to scroll,
 * the chosen one filled, today marked, the closed ones quiet, and «Hoy» to go
 * back. In the week and the month, the range and its arrows.
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
  t: T;
  locale: Locale;
}) {
  return (
    <View style={styles.stack}>
      <Segmented
        label={t("reservas.period")}
        value={period}
        onChange={onPeriod}
        options={[
          { value: "day", label: t("reservas.period.day") },
          { value: "week", label: t("reservas.period.week") },
          { value: "month", label: t("reservas.period.month") },
        ]}
      />
      {period === "day" ? (
        <>
          <DayStrip date={date} today={today} onDate={onDate} config={config} t={t} locale={locale} />
          <View style={styles.titleRow}>
            <Text variant="headline" accessibilityRole="header" style={styles.flex}>
              {date === today ? t("reservas.day.today", { day: dayTitle(date, locale) }) : dayTitle(date, locale)}
            </Text>
            {date !== today ? (
              <Button label={t("reservas.today")} variant="secondary" compact accessibilityLabel={t("reservas.today.back")} onPress={() => onDate(today)} />
            ) : null}
          </View>
          {config.mode === "services" ? (
            <Segmented
              label={t("reservas.view")}
              value={view}
              onChange={onView}
              options={[
                { value: "list", label: t("reservas.view.list") },
                { value: "grid", label: t("reservas.view.grid") },
              ]}
            />
          ) : null}
        </>
      ) : (
        <View style={styles.titleRow}>
          <IconButton
            icon={icons.back}
            label={t(period === "week" ? "reservas.prev.week" : "reservas.prev.month")}
            onPress={() => onDate(period === "week" ? addDays(weekStart(date), -7) : addMonths(date, -1))}
          />
          <Text variant="headline" accessibilityRole="header" style={[styles.flex, styles.center]}>
            {period === "week" ? weekRange(weekStart(date), locale, t) : monthTitle(date, locale)}
          </Text>
          <IconButton
            icon={icons.chevron}
            label={t(period === "week" ? "reservas.next.week" : "reservas.next.month")}
            onPress={() => onDate(period === "week" ? addDays(weekStart(date), 7) : addMonths(date, 1))}
          />
        </View>
      )}
    </View>
  );
}

const CHIP = 52;

function DayStrip({
  date,
  today,
  onDate,
  config,
  t,
  locale,
}: {
  date: LocalDate;
  today: LocalDate;
  onDate: (d: LocalDate) => void;
  config: ResConfig;
  t: T;
  locale: Locale;
}) {
  const { colors } = useTheme();
  const ref = useRef<ComponentRef<typeof ScrollView>>(null);
  // From the week before this one to four weeks ahead, stretched to reach the chosen day.
  const days = useMemo(() => {
    let from = addDays(weekStart(today), -7);
    let to = addDays(weekStart(today), 27);
    if (date < from) from = weekStart(date);
    if (date > to) to = addDays(weekStart(date), 6);
    const out: LocalDate[] = [];
    for (let d = from; d <= to; d = addDays(d, 1)) out.push(d);
    return out;
  }, [date, today]);
  const index = days.indexOf(date);
  useEffect(() => {
    if (index >= 0) ref.current?.scrollTo({ x: Math.max(0, (index - 2) * (CHIP + 6)), animated: false });
  }, [index]);

  return (
    <ScrollView
      ref={ref}
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.strip}
      accessibilityLabel={t("reservas.days")}
    >
      {days.map((d) => {
        const on = d === date;
        const closed = isClosed(config, d);
        const label = t(d === today ? "reservas.day.a11y.today" : closed ? "reservas.day.a11y.closed" : "reservas.day.a11y", { day: dayTitle(d, locale) });
        return (
          <Pressable
            key={d}
            accessibilityRole="button"
            accessibilityLabel={label}
            accessibilityState={{ selected: on }}
            onPress={() => onDate(d)}
            android_ripple={{ color: colors.muted }}
            style={({ pressed }) => [
              styles.day,
              { borderRadius: CARD_RADIUS, backgroundColor: on ? colors.primary : pressed ? colors.muted : "transparent" },
            ]}
          >
            <Text variant="caption" tone={on ? "primaryForeground" : "mutedForeground"} maxFontSizeMultiplier={1.4}>
              {weekdayShort(d, locale)}
            </Text>
            {/* Closed: the softer ink at 4.5:1 or more, and struck through — never colour alone (gate review). */}
            <Text
              variant="bodyStrong"
              tone={on ? "primaryForeground" : closed ? "mutedForeground" : "foreground"}
              style={closed ? styles.closed : undefined}
              maxFontSizeMultiplier={1.4}
            >
              {dayNumber(d)}
            </Text>
            <View style={[styles.dot, { backgroundColor: d === today ? (on ? colors.primaryForeground : colors.primaryText) : "transparent" }]} />
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 12 },
  titleRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  flex: { flex: 1, minWidth: 0 },
  center: { textAlign: "center" },
  strip: { gap: 6, paddingVertical: 2 },
  day: { width: CHIP, minHeight: TOUCH + 16, alignItems: "center", justifyContent: "center", gap: 2, paddingVertical: 6 },
  dot: { width: 5, height: 5, borderRadius: 3 },
  closed: { textDecorationLine: "line-through" },
});
