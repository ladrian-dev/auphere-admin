import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";

import type { Location, Shift, SpecialDate } from "@/api/endpoints";
import type { Locale, T } from "@/i18n/t";
import { checkShifts, shiftsText, shortDate } from "@/lib/business-model";
import { useTheme } from "@/theme/theme";
import { Divider } from "@/ui/bits";
import { Button, IconButton } from "@/ui/button";
import { Card } from "@/ui/card";
import { Chip } from "@/ui/chip";
import { Field } from "@/ui/field";
import { icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import { DateField, ShiftsEditor, SwitchRow } from "./parts";

/** A special date being written: a new one (`id` null) or a change to one that exists. */
export type SpecialForm = { id: string | null; name: string; from: string; to: string; closed: boolean; shifts: Shift[]; location_id: string | null };

export function newSpecial(today: string): SpecialForm {
  return { id: null, name: "", from: today, to: today, closed: true, shifts: [], location_id: null };
}

export function specialForm(s: SpecialDate): SpecialForm {
  return { id: s.id, name: s.name, from: s.from, to: s.to, closed: s.closed, shifts: s.shifts.map((x) => ({ open: x.open, close: x.close })), location_id: s.location_id };
}

/** What the API would refuse, before sending: its codes. */
export function checkSpecial(f: SpecialForm): "date_range" | "no_shifts" | "invalid_time" | "overlap" | "too_many_shifts" | null {
  if (f.to < f.from) return "date_range";
  if (f.closed) return null;
  if (f.shifts.length === 0) return "no_shifts";
  return checkShifts("mon", f.shifts)?.code ?? null;
}

/**
 * Fechas especiales (spec 047, T169; 10.3): holidays and days with other
 * hours, nearest first. Each one opens to change it and has its own «Quitar»;
 * a new one is a short form — the dates on a calendar, closed all day or its
 * shifts, and where, when the business has locations.
 */
export function SpecialDatesSection({
  items,
  locations,
  form,
  onForm,
  onRemove,
  saveBar,
  problem,
  today,
  t,
  locale,
}: {
  items: SpecialDate[];
  locations: Location[];
  form: SpecialForm | null;
  onForm: (f: SpecialForm | null) => void;
  onRemove: (s: SpecialDate) => void;
  /** The bar that saves the form (shared with every section: offline, errors, conflicts). */
  saveBar: ReactNode;
  problem: ReturnType<typeof checkSpecial>;
  today: string;
  t: T;
  locale: Locale;
}) {
  const { colors } = useTheme();
  // The date being changed leaves the list while its form is open, at the top of the section.
  const shown = items.filter((s) => !s.archived && s.id !== form?.id).sort((a, b) => a.from.localeCompare(b.from));
  const where = (id: string | null) => (id ? (locations.find((l) => l.id === id)?.name ?? null) : null);
  const range = (s: { from: string; to: string }) =>
    s.from === s.to ? shortDate(s.from, locale, today) : t("negocio.special.range", { from: shortDate(s.from, locale, today), to: shortDate(s.to, locale, today) });

  const editor = (f: SpecialForm) => (
      <Card testID="special-form">
        <Field label={t("business.special.name")} value={f.name} onChangeText={(name) => onForm({ ...f, name })} maxLength={80} />
        <DateField
          label={t("business.special.from")}
          value={f.from}
          onChange={(from) => onForm({ ...f, from, to: f.to < from ? from : f.to })}
          t={t}
          locale={locale}
        />
        <DateField label={t("business.special.to")} value={f.to} min={f.from} onChange={(to) => onForm({ ...f, to })} t={t} locale={locale} />
        <SwitchRow
          label={t("business.special.closed")}
          value={f.closed}
          onChange={(closed) => onForm({ ...f, closed, shifts: closed ? [] : f.shifts.length ? f.shifts : [{ open: "10:00", close: "14:00" }] })}
        />
        {!f.closed ? <ShiftsEditor shifts={f.shifts} onChange={(shifts) => onForm({ ...f, shifts })} t={t} /> : null}
        {locations.length > 0 ? (
          <View style={styles.where} accessibilityRole="radiogroup" accessibilityLabel={t("business.special.location")}>
            <Text variant="subhead">{t("business.special.location")}</Text>
            <View style={styles.chips}>
              <Chip label={t("business.special.location.all")} on={f.location_id === null} onPress={() => onForm({ ...f, location_id: null })} />
              {locations
                .filter((l) => !l.archived)
                .map((l) => (
                  <Chip key={l.id} label={l.name} on={f.location_id === l.id} onPress={() => onForm({ ...f, location_id: l.id })} />
                ))}
            </View>
          </View>
        ) : null}
        {problem ? (
          <Text variant="footnote" tone="dangerText" accessibilityRole="alert">
            {problem === "date_range" || problem === "no_shifts" ? t(`business.special.error.${problem}`) : t(`business.hours.error.${problem}`, { day: f.name || t("negocio.special.unnamed") })}
          </Text>
        ) : null}
        {saveBar}
      </Card>
  );

  return (
    <View style={styles.stack} testID="special-dates">
      <Text variant="title" accessibilityRole="header">
        {t("business.special.title")}
      </Text>
      <Text variant="callout" tone="mutedForeground">
        {t("business.special.intro")}
      </Text>
      {form && form.id !== null ? editor(form) : null}
      {shown.length > 0 ? (
        <Card style={styles.list}>
          {shown.map((s, i) => {
            const name = s.name || t("negocio.special.unnamed");
            const detail = [range(s), s.closed ? t("business.hours.closed") : shiftsText(s.shifts, t), where(s.location_id)].filter(Boolean).join(" · ");
            return (
              <View key={s.id}>
                {i > 0 ? <Divider /> : null}
                <View style={[styles.row, { borderColor: colors.border }]}>
                  <View style={styles.flex} accessible accessibilityLabel={`${name}. ${detail}`}>
                    <Text variant="body">{name}</Text>
                    <Text variant="footnote" tone="mutedForeground">
                      {detail}
                    </Text>
                  </View>
                  <IconButton icon={icons.edit} label={t("negocio.special.edit", { name })} onPress={() => onForm(specialForm(s))} />
                  <IconButton icon={icons.remove} tone="destructive" label={t("business.special.remove", { name })} onPress={() => onRemove(s)} />
                </View>
              </View>
            );
          })}
        </Card>
      ) : form === null ? (
        <Text variant="callout" tone="mutedForeground">
          {t("business.special.empty")}
        </Text>
      ) : null}

      {form && form.id === null ? (
        editor(form)
      ) : form ? null : (
        <Button label={t("business.special.add")} icon={icons.plus} variant="secondary" full onPress={() => onForm(newSpecial(today))} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 12 },
  list: { paddingVertical: 4, gap: 0 },
  row: { flexDirection: "row", alignItems: "center", gap: 4, paddingVertical: 8 },
  flex: { flex: 1, minWidth: 0, gap: 2 },
  where: { gap: 8 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
});
