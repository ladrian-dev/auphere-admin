import { StyleSheet, View } from "react-native";

import type { Day, Hours, Shift } from "@/api/endpoints";
import type { T } from "@/i18n/t";
import { DAYS, dayName, shiftsText, type Week, type WeekProblem } from "@/lib/business-model";
import { Card } from "@/ui/card";
import { Text } from "@/ui/text";

import { ShiftsEditor, SwitchRow } from "./parts";

/**
 * The week, day by day (spec 047, T169; requirement 10): «Así lo dirá el
 * agente» first — the API's own sentence for what is saved, or a line that
 * says it changes on saving — then each day with its switch and its shifts.
 * The week is always editable: there is no edit mode to find.
 */
export function HoursEditor({
  hours,
  week,
  dirty,
  problem,
  onWeek,
  t,
}: {
  hours: Pick<Hours, "label">;
  week: Week;
  dirty: boolean;
  problem: WeekProblem | null;
  onWeek: (next: Week) => void;
  t: T;
}) {
  const setDay = (d: Day, shifts: Shift[]) => onWeek({ ...week, [d]: shifts });
  const toggle = (d: Day, open: boolean) => {
    if (!open) return setDay(d, []);
    // Opening a closed day starts from the nearest open day before it, as people usually repeat a week.
    const i = DAYS.indexOf(d);
    const before = [...DAYS.slice(0, i)].reverse().find((x) => week[x].length > 0);
    setDay(d, before ? week[before].map((s) => ({ ...s })) : [{ open: "09:00", close: "18:00" }]);
  };

  return (
    <View style={styles.stack}>
      <Card testID="hours-phrase">
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
          {t("business.hours.phrase")}
        </Text>
        <Text variant="body">{dirty ? t("business.hours.phrase.unsaved") : (hours.label ?? t("business.hours.phrase.none"))}</Text>
      </Card>
      {DAYS.map((d) => {
        const open = week[d].length > 0;
        const name = dayName(d, t);
        return (
          <Card key={d} testID={`day-${d}`} tone={problem?.day === d ? "danger" : undefined}>
            <Text variant="headline" accessibilityRole="header">
              {name}
            </Text>
            <SwitchRow label={t("negocio.hours.day.open", { day: name.toLocaleLowerCase() })} hint={open ? undefined : t("business.hours.closed")} value={open} onChange={(v) => toggle(d, v)} />
            {open ? (
              <ShiftsEditor shifts={week[d]} onChange={(s) => setDay(d, s)} invalid={problem?.day === d ? problem.shift : null} t={t} testID={`shifts-${d}`} />
            ) : null}
            {problem?.day === d ? (
              <Text variant="footnote" tone="dangerText" accessibilityRole="alert">
                {t(`business.hours.error.${problem.code}`, { day: name })}
              </Text>
            ) : null}
          </Card>
        );
      })}
    </View>
  );
}

/** The week as one line per day, for a screen reader summary and the tests. */
export function weekSummary(week: Week, t: T): string {
  return DAYS.map((d) => `${dayName(d, t)}: ${shiftsText(week[d], t)}`).join(". ");
}

const styles = StyleSheet.create({
  stack: { gap: 12 },
});
