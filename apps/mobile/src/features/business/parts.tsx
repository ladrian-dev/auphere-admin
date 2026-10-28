import { useState } from "react";
import { Pressable, StyleSheet, Switch, View } from "react-native";

import type { BusinessChange, Shift } from "@/api/endpoints";
import type { Locale, T } from "@/i18n/t";
import { changeLine, dateText, MAX_SHIFTS, normalizeTime, validTime } from "@/lib/business-model";
import { addMonths, monthGrid, monthStart } from "@/lib/reservas-model";
import { TOUCH, useTheme } from "@/theme/theme";
import { Button, IconButton } from "@/ui/button";
import { Field } from "@/ui/field";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";
import { switchColors } from "@/ui/switch-colors";

/**
 * The pieces every Negocio screen shares (spec 047, T169): the bar that saves
 * (and says why it cannot), the notice of a conflict with its two ways out,
 * the last change with «Deshacer», a switch row, time fields and a date
 * picker. All of them at least 44 pt / 48 dp, named for the screen reader,
 * growing with the phone's text (50.9).
 */

/**
 * Save and cancel, with the reason they do nothing said above them: without a
 * connection nothing is saved or queued, and what was typed stays (50.5). The
 * buttons stay mounted while saving, so the screen reader keeps its place.
 */
export function SaveBar({
  label,
  onSave,
  onCancel,
  busy,
  online,
  error,
  disabled = false,
  t,
}: {
  label: string;
  onSave: () => void;
  onCancel?: () => void;
  busy: boolean;
  online: boolean;
  error: string | null;
  disabled?: boolean;
  t: T;
}) {
  return (
    <View style={styles.bar}>
      {!online ? (
        <Notice tone="warning" icon={icons.offline} text={t("negocio.offline")} />
      ) : error ? (
        <Notice tone="danger" icon={icons.warning} text={error} />
      ) : null}
      <View style={styles.buttons}>
        <Button label={label} onPress={onSave} busy={busy} disabled={disabled || !online} full />
        {onCancel ? <Button label={t("business.section.cancel")} variant="ghost" onPress={onCancel} disabled={busy} full /> : null}
      </View>
    </View>
  );
}

/** One sentence that says a state, as an alert for the screen reader. Never colour alone: an icon and words. */
export function Notice({ tone, icon, text }: { tone: "warning" | "danger" | "info"; icon: (typeof icons)[keyof typeof icons]; text: string }) {
  const { colors, radius } = useTheme();
  const bg = tone === "warning" ? colors.warningBg : tone === "danger" ? colors.dangerBg : colors.infoBg;
  const fg = tone === "warning" ? "warningText" : tone === "danger" ? "dangerText" : "infoText";
  return (
    <View accessible accessibilityRole="alert" accessibilityLiveRegion="polite" style={[styles.notice, { backgroundColor: bg, borderRadius: radius.md }]}>
      <Icon name={icon} size={18} tone={fg} />
      <Text variant="subhead" tone={fg} style={styles.flex}>
        {text}
      </Text>
    </View>
  );
}

/**
 * Someone saved first (13.4, 412): what the person typed is still on screen,
 * and they choose — save theirs over it, or see what is there now.
 */
export function ConflictNotice({ onMine, onTheirs, busy, t }: { onMine: () => void; onTheirs: () => void; busy: boolean; t: T }) {
  return (
    <View style={styles.bar} testID="conflict">
      <Notice tone="warning" icon={icons.warning} text={t("negocio.conflict")} />
      <View style={styles.buttons}>
        <Button label={t("negocio.conflict.mine")} onPress={onMine} busy={busy} full />
        <Button label={t("negocio.conflict.theirs")} variant="secondary" onPress={onTheirs} disabled={busy} full />
      </View>
    </View>
  );
}

/** The newest change of a section, who made it and from where, with «Deshacer» while it can be (13.3). */
export function LastChange({
  change,
  onUndo,
  busy,
  online,
  t,
  locale,
  now,
}: {
  change: BusinessChange;
  onUndo: (id: string) => void;
  busy: boolean;
  online: boolean;
  t: T;
  locale: Locale;
  now?: Date;
}) {
  const { colors } = useTheme();
  const line = changeLine(change, t, locale, now);
  return (
    <View style={[styles.last, { borderColor: colors.border }]} testID="last-change">
      <View style={styles.flex} accessible accessibilityLabel={`${t("negocio.last")}: ${line}`}>
        <Text variant="footnote" tone="mutedForeground">
          {t("negocio.last")}
        </Text>
        <Text variant="callout">{line}</Text>
      </View>
      <Button
        label={t("business.history.undo")}
        accessibilityLabel={t("negocio.undo.label", { section: line.split(" · ")[0] ?? "" })}
        variant="secondary"
        compact
        icon={icons.giveBack}
        busy={busy}
        disabled={!online}
        onPress={() => onUndo(change.id)}
      />
    </View>
  );
}

/** A labelled switch, the whole row its target. */
export function SwitchRow({ label, hint, value, disabled = false, onChange }: { label: string; hint?: string; value: boolean; disabled?: boolean; onChange: (v: boolean) => void }) {
  const { colors } = useTheme();
  return (
    <View style={styles.switchRow}>
      <View style={styles.flex}>
        <Text variant="body">{label}</Text>
        {hint ? (
          <Text variant="footnote" tone="mutedForeground">
            {hint}
          </Text>
        ) : null}
      </View>
      <Switch accessibilityLabel={label} accessibilityHint={hint} value={value} disabled={disabled} onValueChange={onChange} {...switchColors(colors)} />
    </View>
  );
}

/**
 * A time, typed: the numbers keyboard, «9» becomes «09:00» when the field is
 * left, and a wrong one is said under it in words (not only in red).
 */
export function TimeField({ label, value, onChange, closing = false, invalid = false, t }: { label: string; value: string; onChange: (v: string) => void; closing?: boolean; invalid?: boolean; t: T }) {
  // Said once the field is left (or a save found it wrong), never while the person is still typing.
  const [left, setLeft] = useState(false);
  const wrong = invalid || (left && value !== "" && !validTime(value, closing));
  return (
    <View style={styles.time}>
      <Field
        label={label}
        value={value}
        onChangeText={onChange}
        onBlur={() => {
          setLeft(true);
          onChange(normalizeTime(value));
        }}
        placeholder={t("negocio.hours.time.placeholder")}
        keyboardType="numbers-and-punctuation"
        maxLength={5}
        autoCorrect={false}
      />
      {wrong ? (
        <Text variant="footnote" tone="dangerText" accessibilityRole="alert">
          {t("negocio.hours.time.invalid")}
        </Text>
      ) : null}
    </View>
  );
}

/**
 * The shifts of one day (or of a special date): pairs of «Abre» and
 * «Cierra», a button to take one away and one to add another, up to six.
 */
export function ShiftsEditor({
  shifts,
  onChange,
  invalid,
  t,
  testID,
}: {
  shifts: Shift[];
  onChange: (next: Shift[]) => void;
  /** The index of the shift the API (or the check before it) refused. */
  invalid?: number | null;
  t: T;
  testID?: string;
}) {
  const set = (i: number, patch: Partial<Shift>) => onChange(shifts.map((s, k) => (k === i ? { ...s, ...patch } : s)));
  return (
    <View style={styles.shifts} testID={testID}>
      {shifts.map((s, i) => (
        <View key={i} style={styles.shift}>
          <View style={styles.pair}>
            <TimeField label={t("business.hours.open", { n: i + 1 })} value={s.open} onChange={(v) => set(i, { open: v })} invalid={invalid === i && !validTime(s.open)} t={t} />
            <TimeField label={t("business.hours.close", { n: i + 1 })} value={s.close} onChange={(v) => set(i, { close: v })} closing invalid={invalid === i && !validTime(s.close, true)} t={t} />
          </View>
          <IconButton icon={icons.remove} tone="destructive" label={t("business.hours.remove_shift", { n: i + 1 })} onPress={() => onChange(shifts.filter((_, k) => k !== i))} />
        </View>
      ))}
      {shifts.length < MAX_SHIFTS ? (
        <Button
          label={t("business.hours.add_shift")}
          icon={icons.plus}
          variant="ghost"
          compact
          onPress={() => {
            const last = shifts[shifts.length - 1];
            onChange([...shifts, last ? { open: last.close === "24:00" ? "00:00" : last.close, close: "" } : { open: "09:00", close: "14:00" }]);
          }}
        />
      ) : (
        <Text variant="footnote" tone="mutedForeground">
          {t("business.hours.max_shifts")}
        </Text>
      )}
    </View>
  );
}

/**
 * A date, chosen on a month: the field says the date in words and opens a
 * calendar under it (Monday first), with buttons for the month before and
 * after. No gesture is the only way: every day is a button with its date.
 */
export function DateField({ label, value, onChange, min, t, locale }: { label: string; value: string; onChange: (d: string) => void; min?: string; t: T; locale: Locale }) {
  const { colors, radius } = useTheme();
  const [open, setOpen] = useState(false);
  const [month, setMonth] = useState(() => monthStart(value));
  const words = dateText(value, locale);
  const letters = t("reservas.weekdays").split(",");
  return (
    <View style={styles.dateWrap}>
      <Text variant="subhead" importantForAccessibility="no" accessibilityElementsHidden>
        {label}
      </Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${label}: ${words}`}
        accessibilityHint={t("negocio.date.pick", { label })}
        accessibilityState={{ expanded: open }}
        onPress={() => {
          setMonth(monthStart(value));
          setOpen((o) => !o);
        }}
        android_ripple={{ color: colors.muted }}
        style={({ pressed }) => [styles.dateBox, { borderRadius: radius.md, borderColor: open ? colors.ring : colors.input, backgroundColor: pressed ? colors.muted : colors.card }]}
      >
        <Icon name={icons.calendar} size={18} tone="mutedForeground" />
        <Text variant="body" style={styles.flex}>
          {words}
        </Text>
      </Pressable>
      {open ? (
        <View style={[styles.calendar, { borderColor: colors.border, borderRadius: radius.md, backgroundColor: colors.card }]} testID="date-calendar">
          <View style={styles.monthBar}>
            <IconButton icon={icons.back} label={t("negocio.date.prev")} onPress={() => setMonth(addMonths(month, -1))} />
            <Text variant="headline" accessibilityRole="header" style={styles.monthTitle}>
              {dateText(month, locale, { month: "long", year: "numeric" })}
            </Text>
            <IconButton icon={icons.chevron} label={t("negocio.date.next")} onPress={() => setMonth(addMonths(month, 1))} />
          </View>
          <View style={styles.week} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
            {letters.map((l, i) => (
              <Text key={i} variant="caption" tone="mutedForeground" style={styles.cellText}>
                {l}
              </Text>
            ))}
          </View>
          {monthGrid(month).map((week, w) => (
            <View key={w} style={styles.week}>
              {week.map((d, i) => {
                if (!d) return <View key={i} style={styles.cell} />;
                const on = d === value;
                const before = min !== undefined && d < min;
                return (
                  <Pressable
                    key={d}
                    accessibilityRole="button"
                    accessibilityLabel={dateText(d, locale)}
                    accessibilityState={{ selected: on, disabled: before }}
                    disabled={before}
                    onPress={() => {
                      onChange(d);
                      setOpen(false);
                    }}
                    style={({ pressed }) => [styles.cell, { borderRadius: radius.full, backgroundColor: on ? colors.primary : pressed ? colors.muted : "transparent" }]}
                  >
                    <Text variant="callout" tone={on ? "primaryForeground" : before ? "subtle" : "foreground"} maxFontSizeMultiplier={1.4}>
                      {String(Number(d.slice(8)))}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, minWidth: 0, gap: 2 },
  bar: { gap: 12 },
  buttons: { gap: 8 },
  notice: { flexDirection: "row", alignItems: "flex-start", gap: 10, padding: 12 },
  last: { flexDirection: "row", alignItems: "center", gap: 12, flexWrap: "wrap", paddingTop: 12, borderTopWidth: StyleSheet.hairlineWidth },
  switchRow: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: TOUCH, paddingVertical: 4 },
  time: { flex: 1, minWidth: 120, gap: 4 },
  shifts: { gap: 12 },
  shift: { flexDirection: "row", alignItems: "flex-end", gap: 4 },
  pair: { flex: 1, flexDirection: "row", flexWrap: "wrap", gap: 8 },
  dateWrap: { gap: 6 },
  dateBox: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: TOUCH, paddingHorizontal: 12, borderWidth: 1 },
  // A little past the field's edges, so seven days keep 44 pt each on a 375 pt phone inside a card (50.9).
  calendar: { borderWidth: StyleSheet.hairlineWidth * 2, padding: 4, marginHorizontal: -8, gap: 2 },
  monthBar: { flexDirection: "row", alignItems: "center" },
  monthTitle: { flex: 1, textAlign: "center", textTransform: "capitalize" },
  week: { flexDirection: "row" },
  cell: { flex: 1, minHeight: 44, alignItems: "center", justifyContent: "center" },
  cellText: { flex: 1, textAlign: "center" },
});
