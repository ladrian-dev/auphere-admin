import { useMemo, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import type { ResConfig } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { addDays, slotsOfDay, type LocalDate } from "@/lib/reservas-model";
import { Button } from "@/ui/button";
import { Chip } from "@/ui/chip";
import { Field } from "@/ui/field";
import { Text } from "@/ui/text";

import { relativeDay } from "./format";

/**
 * «Bloquear horas» (spec 044, R8.7; Aforo): a day, a shift and a reason — the
 * reason is required. The agent stops taking bookings in those hours; the
 * ones already there stay, and the sheet says so before anything is blocked.
 */
export function BlockForm({
  config,
  today,
  saving,
  error,
  online,
  onSave,
  t,
  locale,
}: {
  config: ResConfig;
  today: LocalDate;
  saving: boolean;
  error: string | null;
  online: boolean;
  /** The shift's arrivals, both ends included (043 §6). */
  onSave: (b: { date: LocalDate; from: number; until: number; reason: string }) => void;
  t: T;
  locale: Locale;
}) {
  const [date, setDate] = useState(today);
  const shifts = useMemo(() => [...new Set(slotsOfDay(config, date).map((s) => s.shift))], [config, date]);
  const [shift, setShift] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [missing, setMissing] = useState(false);
  const chosen = shift && shifts.includes(shift) ? shift : (shifts[0] ?? null);
  const days = Array.from({ length: 14 }, (_, i) => addDays(today, i)).filter((d) => slotsOfDay(config, d).length > 0);

  return (
    <View style={styles.stack}>
      <Text variant="title" accessibilityRole="header">
        {t("reservas.block.title")}
      </Text>
      <Text variant="callout" tone="mutedForeground">
        {t("reservas.block.body")}
      </Text>
      <View style={styles.section}>
        <Text variant="subhead" accessibilityRole="header">
          {t("reservas.block.day")}
        </Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} accessibilityRole="radiogroup">
          {days.map((d) => (
            <Chip key={d} label={relativeDay(d, today, locale, t)} on={date === d} onPress={() => setDate(d)} />
          ))}
        </ScrollView>
      </View>
      <View style={styles.section}>
        <Text variant="subhead" accessibilityRole="header">
          {t("reservas.block.shift")}
        </Text>
        <View style={styles.wrap}>
          {shifts.map((s) => (
            <Chip key={s} label={s} on={chosen === s} onPress={() => setShift(s)} />
          ))}
        </View>
      </View>
      <Field
        label={t("reservas.block.reason")}
        placeholder={t("reservas.block.reason.hint")}
        value={reason}
        onChangeText={(v) => {
          setReason(v);
          if (v.trim()) setMissing(false);
        }}
      />
      {missing ? (
        <Text variant="footnote" tone="dangerText" accessibilityRole="alert">
          {t("reservas.block.missing")}
        </Text>
      ) : null}
      {error ? (
        <Text variant="footnote" tone="dangerText" accessibilityRole="alert">
          {error}
        </Text>
      ) : null}
      <Button
        label={t("reservas.block.save")}
        full
        busy={saving}
        disabled={!online || !chosen}
        onPress={() => {
          if (!reason.trim()) return setMissing(true);
          const shift = config.capacity?.shifts.find((s) => s.name === chosen);
          if (shift) onSave({ date, from: shift.from, until: shift.to, reason: reason.trim() });
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 16 },
  section: { gap: 8 },
  chips: { gap: 8, paddingVertical: 2 },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
});
