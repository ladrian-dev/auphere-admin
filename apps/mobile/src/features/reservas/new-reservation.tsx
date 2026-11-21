import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import type { FreeSlot, NewReservation, ResConfig } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { earliestFrom, hhmm, nextOpenDays, type LocalDate, type Minutes, type WallTime } from "@/lib/reservas-model";
import { haptics } from "@/motion/haptics";
import { Button, IconButton } from "@/ui/button";
import { Chip } from "@/ui/chip";
import { icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import { FormField } from "./form-field";
import { firstName, party, relativeDay } from "./format";
import { cleanPhone, phoneProblem, phoneProblemKey } from "./phone";
import { OpenDays, slotCells, slotGroups, SlotGroups } from "./slot-picker";
import { Stepper } from "./stepper";

export type SlotQuery = { date: LocalDate; serviceId?: string; proId?: string | null; partySize?: number; exclude?: string };

/** What the way in already knows: a free slot of the grid, someone of the waitlist (spec 069 R13.3, R16.3). */
export type NewPrefill = { time?: Minutes; proId?: string | null; serviceId?: string; name?: string; phone?: string; partySize?: number };

/** The seven open days ahead (spec 069, R15.1). */
const DAYS = 7;

/**
 * «Nueva reserva» (spec 044 Requisito 5, spec 069 Requisito 15): in
 * Servicios, the service and with whom (or anyone); in Aforo, how many. Then
 * the day — the seven open days ahead — and the time, in morning and
 * afternoon (or Aforo's shifts) with the taken ones struck through in place,
 * none before the agent's minimum notice. Then the client: name and phone,
 * both required and the phone with its country prefix (064 R3). «Guardar
 * reserva» always answers: with something missing it says what, under each
 * field, and saves nothing (Historia 5, escenario 2). The slots come from
 * outside (`onQuery` → `slots`), so the form is the same against the API or
 * the example data.
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
  now = null,
  initial,
  onDirty,
  onClose,
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
  /** The business's «now»: with it, no time before now plus the agent's notice is offered (R15.2). */
  now?: WallTime | null;
  initial?: NewPrefill;
  /** Whether something was written or chosen, so closing can ask first (R15.3). */
  onDirty?: (dirty: boolean) => void;
  onClose?: () => void;
}) {
  const services = config.mode === "services" ? config.services : null;
  const cap = config.mode === "capacity" ? config.capacity : null;
  const firstService = services?.catalog.find((s) => s.id === initial?.serviceId)?.id ?? services?.catalog[0]?.id ?? "";
  const [serviceId, setServiceId] = useState(firstService);
  const [proId, setProId] = useState<string | null>(initial?.proId ?? null);
  const [date, setDate] = useState<LocalDate>(initialDate < today ? today : initialDate);
  const [size, setSize] = useState(initial?.partySize ?? 2);
  const [time, setTime] = useState<number | null>(initial?.time ?? null);
  const [name, setName] = useState(initial?.name ?? "");
  const [phone, setPhone] = useState(initial?.phone ?? "");
  const [tried, setTried] = useState(false);

  const service = services?.catalog.find((s) => s.id === serviceId) ?? null;
  const team = (services?.team ?? []).filter((p) => !service || service.proIds === null || service.proIds.includes(p.id));
  const earliest = now ? earliestFrom(now, config.agent?.minNoticeMin ?? 60) : null;
  const days = nextOpenDays(config, today, DAYS);
  if (!days.includes(date)) days.unshift(date);

  // Each change of what is asked asks the API again; a time counts only while it is among the new slots.
  useEffect(() => {
    onQuery(services ? { date, serviceId, proId } : { date, partySize: size });
    // onQuery is the parent's setter; the query is what matters.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, serviceId, proId, size]);

  // Against what the way in brought: «Reservarle ahora» opens with a name and a phone, and is not «written» yet.
  const dirty = name.trim() !== (initial?.name ?? "").trim() || phone.trim() !== (initial?.phone ?? "").trim() || time !== (initial?.time ?? null);
  useEffect(() => {
    onDirty?.(dirty);
  }, [dirty, onDirty]);

  const cells = slots ? slotCells(config, date, slots, service?.durationMin ?? cap?.stayMin ?? 30, earliest) : [];
  const groups = slotGroups(config, cells, t);
  const picked = time !== null ? (cells.find((c) => c.time === time && c.state === "free") ?? null) : null;
  // A time brought from the grid that the API no longer offers is said, not silently dropped.
  const gone = time !== null && slots !== null && !slotsLoading && picked === null;
  const problem = phoneProblem(phone);
  const errors = {
    time: picked === null ? t("reservas.form.time.required") : null,
    name: name.trim().length === 0 ? t("reservas.form.name.required") : null,
    phone: problem ? t(phoneProblemKey(problem)) : null,
  };
  const day = relativeDay(date, today, locale, t);
  const pickedPro = picked?.pro?.name ?? team.find((p) => p.id === proId)?.name ?? "";
  const summary = picked
    ? services && service
      ? t("reservas.new.summary.services", { day, time: hhmm(picked.time), service: service.name, pro: firstName(pickedPro) })
      : t("reservas.new.summary.capacity", { day, time: hhmm(picked.time), party: party(size, cap?.unit ?? "", t) })
    : t("reservas.new.pick");
  const notice = earliest && (config.agent?.minNoticeMin ?? 60) > 0 ? earliest : null;
  // The notice cuts into this day, or covers it whole (24 h reaches into tomorrow): said, never an unexplained «no slots».
  const noticeText = notice
    ? date === notice.date
      ? t("reservas.form.notice", { time: hhmm(notice.minutes) })
      : date < notice.date
        ? t("reservas.form.notice.day", { when: t("reservas.dayAt", { day: relativeDay(notice.date, today, locale, t).toLocaleLowerCase(locale), time: hhmm(notice.minutes) }) })
        : null
    : null;

  const save = () => {
    if (saving || !online) return;
    setTried(true);
    if (errors.time || errors.name || errors.phone || !picked) {
      haptics.warning();
      return;
    }
    const customer = { name: name.trim(), phone: cleanPhone(phone) };
    onSave(services ? { date, time: picked.time, customer, serviceId, proId: picked.pro?.id ?? proId } : { date, time: picked.time, customer, partySize: size });
  };

  return (
    <View style={styles.stack}>
      <View style={styles.head}>
        <Text variant="sheetTitle" accessibilityRole="header" style={styles.flex}>
          {t("reservas.new")}
        </Text>
        {onClose ? <IconButton icon={icons.close} label={t("reservas.form.close")} tone="foreground" onPress={onClose} /> : null}
      </View>

      {services ? (
        <>
          <Section title={t("reservas.new.service")}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} accessibilityRole="radiogroup">
              {services.catalog.map((s) => (
                <Chip
                  key={s.id}
                  label={s.name}
                  on={serviceId === s.id}
                  onPress={() => {
                    setServiceId(s.id);
                    setTime(null);
                  }}
                />
              ))}
            </ScrollView>
          </Section>
          <Section title={t("reservas.new.with")}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} accessibilityRole="radiogroup">
              <Chip
                label={t("reservas.new.any")}
                on={proId === null}
                onPress={() => {
                  setProId(null);
                  setTime(null);
                }}
              />
              {team.map((p) => (
                <Chip
                  key={p.id}
                  label={firstName(p.name)}
                  accessibilityLabel={p.name}
                  on={proId === p.id}
                  onPress={() => {
                    setProId(p.id);
                    setTime(null);
                  }}
                />
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
        <OpenDays
          days={days}
          value={date}
          today={today}
          onChange={(d) => {
            setDate(d);
            setTime(null);
          }}
          t={t}
          locale={locale}
        />
      </Section>

      <Section title={t("reservas.new.time")}>
        {noticeText ? (
          <Text variant="footnote" tone="mutedForeground">
            {noticeText}
          </Text>
        ) : null}
        <SlotGroups
          groups={groups}
          value={picked ? picked.time : null}
          onChange={(c) => setTime(c.time)}
          loading={slotsLoading && !slots}
          error={slotsError && !slots}
          onRetry={onRetrySlots}
          empty={services ? t("reservas.new.noSlots") : t("reservas.new.noSlots.capacity")}
          anyPro={services !== null && proId === null}
          t={t}
        />
        {gone && time !== null ? (
          <Text variant="footnote" tone="warningText" accessibilityLiveRegion="polite">
            {t("reservas.form.prefill.gone", { time: hhmm(time) })}
          </Text>
        ) : tried && errors.time ? (
          <Text variant="footnote" tone="dangerText" accessibilityRole="alert">
            {errors.time}
          </Text>
        ) : null}
      </Section>

      <Section title={t("reservas.form.client")}>
        <FormField
          label={t("reservas.new.name")}
          value={name}
          onChangeText={setName}
          autoCapitalize="words"
          textContentType="name"
          autoComplete="name"
          error={tried ? errors.name : null}
        />
        <FormField
          label={t("reservas.phone.label")}
          value={phone}
          onChangeText={setPhone}
          keyboardType="phone-pad"
          textContentType="telephoneNumber"
          autoComplete="tel"
          placeholder={t("reservas.phone.placeholder")}
          hint={t("reservas.phone.hint")}
          error={tried ? errors.phone : null}
        />
      </Section>

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
      <Button label={t("reservas.new.save")} full busy={saving} disabled={!online} onPress={save} testID="new-save" />
    </View>
  );
}

export function Section({ title, aside, children }: { title: string; aside?: string; children: React.ReactNode }) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHead}>
        <Text variant="subhead" accessibilityRole="header">
          {title}
        </Text>
        {aside ? (
          <Text variant="footnote" tone="mutedForeground">
            {aside}
          </Text>
        ) : null}
      </View>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 18 },
  head: { flexDirection: "row", alignItems: "center", gap: 8 },
  flex: { flex: 1, minWidth: 0 },
  section: { gap: 8 },
  sectionHead: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between", gap: 8, flexWrap: "wrap" },
  chips: { gap: 8, paddingVertical: 2 },
});
