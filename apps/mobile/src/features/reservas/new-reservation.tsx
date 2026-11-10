import { useEffect, useMemo, useState } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import type { FreeSlot, NewReservation, ResConfig } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { addDays, hhmm, isClosed, type LocalDate } from "@/lib/reservas-model";
import { CARD_RADIUS, useTheme } from "@/theme/theme";
import { Button } from "@/ui/button";
import { Chip } from "@/ui/chip";
import { Field } from "@/ui/field";
import { Skeleton } from "@/ui/states";
import { Text } from "@/ui/text";

import { firstName, party, relativeDay } from "./format";
import { Stepper } from "./stepper";

export type SlotQuery = { date: LocalDate; serviceId?: string; proId?: string | null; partySize?: number };

/** How many open days the day chips offer (the design: up to 8). */
const DAYS = 8;

/**
 * «Nueva reserva» (spec 044, Requisito 5): in Servicios, the service, with
 * whom (or anyone), the day and one of the real slots the API returns — each
 * with who would do it; in Aforo, how many, the day and a time with what is
 * left (a full one cannot be chosen; above the maximum per booking it warns
 * that the agent would not take it, and lets the person do it). Then a name
 * (required) and a phone (optional; with it the customer gets the WhatsApp
 * confirmation), a one-line summary, and «Guardar reserva» once both a name
 * and a time are there. The slots come from outside (`onQuery` → `slots`), so
 * the form is the same against the API or the example data.
 */
export function NewReservationForm({
  config,
  today,
  initialDate,
  slots,
  slotsLoading,
  slotsError = false,
  onRetrySlots,
  onQuery,
  onSave,
  saving,
  error,
  online,
  t,
  locale,
}: {
  config: ResConfig;
  today: LocalDate;
  initialDate: LocalDate;
  slots: FreeSlot[] | null;
  slotsLoading: boolean;
  /** The slots could not be read: said as such, with «Reintentar» — never «no quedan huecos». */
  slotsError?: boolean;
  onRetrySlots?: () => void;
  onQuery: (q: SlotQuery) => void;
  onSave: (body: NewReservation) => void;
  saving: boolean;
  error: string | null;
  online: boolean;
  t: T;
  locale: Locale;
}) {
  const { colors } = useTheme();
  const services = config.mode === "services" ? config.services : null;
  const cap = config.mode === "capacity" ? config.capacity : null;
  const [serviceId, setServiceId] = useState(services?.catalog[0]?.id ?? "");
  const [proId, setProId] = useState<string | null>(null);
  const [date, setDate] = useState<LocalDate>(initialDate < today ? today : initialDate);
  const [size, setSize] = useState(2);
  const [time, setTime] = useState<number | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("+56 ");

  const service = services?.catalog.find((s) => s.id === serviceId) ?? null;
  const team = (services?.team ?? []).filter((p) => !service || service.proIds === null || service.proIds.includes(p.id));

  const days = useMemo(() => {
    const out: LocalDate[] = [];
    for (let d = today; out.length < DAYS && d <= addDays(today, 30); d = addDays(d, 1)) if (!isClosed(config, d)) out.push(d);
    if (!out.includes(date)) out.unshift(date);
    return out;
  }, [config, today, date]);

  // Each change of what is asked asks the API again; a time counts only while it is among the new slots.
  useEffect(() => {
    onQuery(services ? { date, serviceId, proId } : { date, partySize: size });
    // onQuery is the parent's setter; the query is what matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, serviceId, proId, size]);

  const picked = slots?.find((s) => s.time === time) ?? null;
  const cleanPhone = phone.replace(/\s+/g, " ").trim();
  const customerPhone = cleanPhone === "" || cleanPhone === "+56" ? null : cleanPhone;
  const can = online && !saving && name.trim().length > 0 && picked !== null && !picked.full;
  const day = relativeDay(date, today, locale, t);
  const summary = picked
    ? services && service
      ? t("reservas.new.summary.services", { day, time: hhmm(picked.time), service: service.name, pro: firstName(picked.pro?.name ?? team.find((p) => p.id === proId)?.name ?? "") })
      : t("reservas.new.summary.capacity", { day, time: hhmm(picked.time), party: party(size, cap?.unit ?? "", t) })
    : t("reservas.new.pick");

  const save = () => {
    if (!can || !picked) return;
    const customer = { name: name.trim(), phone: customerPhone };
    onSave(
      services
        ? { date, time: picked.time, customer, serviceId, proId: picked.pro?.id ?? proId }
        : { date, time: picked.time, customer, partySize: size },
    );
  };

  return (
    <View style={styles.stack}>
      <Text variant="title" accessibilityRole="header">
        {t("reservas.new")}
      </Text>

      {services ? (
        <>
          <Section title={t("reservas.new.service")}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} accessibilityRole="radiogroup">
              {services.catalog.map((s) => (
                <Chip key={s.id} label={s.name} on={serviceId === s.id} onPress={() => setServiceId(s.id)} />
              ))}
            </ScrollView>
          </Section>
          <Section title={t("reservas.new.with")}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} accessibilityRole="radiogroup">
              <Chip label={t("reservas.new.any")} on={proId === null} onPress={() => setProId(null)} />
              {team.map((p) => (
                <Chip key={p.id} label={firstName(p.name)} accessibilityLabel={p.name} on={proId === p.id} onPress={() => setProId(p.id)} />
              ))}
            </ScrollView>
          </Section>
        </>
      ) : cap ? (
        <>
          <Stepper label={t("reservas.new.party")} value={size} onChange={setSize} max={Math.max(cap.capacity - cap.walkinReserved, 1)} unit={cap.unit} t={t} />
          {size > cap.maxParty ? (
            <Text variant="footnote" tone="warningText" accessibilityLiveRegion="polite">
              {t("reservas.new.over", { max: cap.maxParty })}
            </Text>
          ) : null}
        </>
      ) : null}

      <Section title={t("reservas.new.day")}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} accessibilityRole="radiogroup">
          {days.map((d) => (
            <Chip key={d} label={relativeDay(d, today, locale, t)} on={date === d} onPress={() => setDate(d)} />
          ))}
        </ScrollView>
      </Section>

      <Section title={t("reservas.new.time")}>
        {slotsLoading && !slots ? (
          <Skeleton rows={1} label={t("reservas.new.slots.loading")} />
        ) : slotsError && !slots ? (
          <View style={styles.slotsError}>
            <Text variant="callout" tone="dangerText" accessibilityRole="alert">
              {t("reservas.new.slots.error")}
            </Text>
            {onRetrySlots ? <Button label={t("app.retry")} variant="secondary" compact onPress={onRetrySlots} /> : null}
          </View>
        ) : !slots || slots.length === 0 ? (
          <Text variant="callout" tone="mutedForeground">
            {services ? t("reservas.new.noSlots") : t("reservas.new.noSlots.capacity")}
          </Text>
        ) : (
          <View style={styles.grid}>
            {slots.map((s) => {
              const on = time === s.time;
              const label = s.full
                ? t("reservas.new.slot.a11y.full", { time: hhmm(s.time) })
                : s.left !== null
                  ? t("reservas.new.slot.a11y.left", { time: hhmm(s.time), n: s.left })
                  : s.pro
                    ? t("reservas.new.slot.a11y", { time: hhmm(s.time), pro: s.pro.name })
                    : hhmm(s.time);
              return (
                <Pressable
                  key={`${s.time}-${s.pro?.id ?? ""}`}
                  accessibilityRole="radio"
                  accessibilityLabel={label}
                  accessibilityState={{ checked: on, disabled: s.full }}
                  disabled={s.full}
                  onPress={() => setTime(s.time)}
                  android_ripple={{ color: colors.muted }}
                  style={({ pressed }) => [
                    styles.slot,
                    {
                      borderRadius: CARD_RADIUS,
                      borderColor: on ? colors.primary : colors.border,
                      backgroundColor: on ? colors.primary : s.full ? colors.muted : pressed ? colors.muted : colors.card,
                    },
                  ]}
                >
                  <Text variant="bodyStrong" tone={on ? "primaryForeground" : s.full ? "subtle" : "foreground"} style={styles.num}>
                    {hhmm(s.time)}
                  </Text>
                  <Text variant="caption" tone={on ? "primaryForeground" : "mutedForeground"} numberOfLines={1}>
                    {s.full ? t("reservas.new.full") : s.left !== null ? t("reservas.new.left", { n: s.left }) : s.pro && proId === null ? firstName(s.pro.name) : " "}
                  </Text>
                </Pressable>
              );
            })}
            {/* Empty places to finish the last row of four, so its times are as wide as the others. */}
            {Array.from({ length: (4 - (slots.length % 4)) % 4 }, (_, i) => (
              <View key={`filler-${i}`} testID="slot-filler" style={[styles.slot, styles.filler]} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" pointerEvents="none" />
            ))}
          </View>
        )}
      </Section>

      <Field label={t("reservas.new.name")} value={name} onChangeText={setName} autoCapitalize="words" textContentType="name" autoComplete="name" />
      <View style={styles.section}>
        <Field
          label={t("reservas.new.phone")}
          value={phone}
          onChangeText={setPhone}
          keyboardType="phone-pad"
          textContentType="telephoneNumber"
          autoComplete="tel"
        />
        <Text variant="footnote" tone="mutedForeground">
          {t("reservas.new.phone.hint")}
        </Text>
      </View>

      <Text variant="callout" tone={picked ? "foreground" : "mutedForeground"} accessibilityLiveRegion="polite">
        {summary}
      </Text>
      {error ? (
        <Text variant="footnote" tone="dangerText" accessibilityRole="alert">
          {error}
        </Text>
      ) : null}
      {!online ? (
        <Text variant="footnote" tone="warningText" accessibilityRole="alert">
          {t("reservas.error.offline")}
        </Text>
      ) : null}
      <Button label={t("reservas.new.save")} full busy={saving} disabled={!can && !saving} onPress={save} testID="new-save" />
    </View>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <Text variant="subhead" accessibilityRole="header">
        {title}
      </Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 18 },
  section: { gap: 8 },
  chips: { gap: 8, paddingVertical: 2 },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  slot: { flexBasis: "22%", flexGrow: 1, minHeight: 52, alignItems: "center", justifyContent: "center", borderWidth: 1, paddingVertical: 6, gap: 2 },
  filler: { borderColor: "transparent" },
  slotsError: { gap: 8, alignItems: "flex-start" },
  num: { fontVariant: ["tabular-nums"] },
});
