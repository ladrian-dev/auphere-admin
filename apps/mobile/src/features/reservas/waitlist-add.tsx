import { useState } from "react";
import { ScrollView, StyleSheet, View } from "react-native";

import type { JoinWaitlist, ResConfig } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { hhmm, nextOpenDays, slotsOfDay, type LocalDate, type Minutes } from "@/lib/reservas-model";
import { haptics } from "@/motion/haptics";
import { Button } from "@/ui/button";
import { Chip } from "@/ui/chip";
import { Text } from "@/ui/text";

import { FormField } from "./form-field";
import { firstName } from "./format";
import { Section } from "./new-reservation";
import { cleanPhone, phoneProblem, phoneProblemKey } from "./phone";
import { OpenDays } from "./slot-picker";
import { Stepper } from "./stepper";

/**
 * «Apuntar en la lista de espera» (spec 069, R16.1; the web's
 * `add-waitlist-dialog.tsx`, spec 064 R3.7): someone the team puts on the
 * list by hand. Name and phone are required — the agent offers a freed slot
 * on WhatsApp — and so is what they want: in Servicios a service, with
 * anyone or someone, and «any opening until» a day; in Aforo how many, the
 * day and, if they say, the time. A walk-in at the door is the other way in
 * and asks no phone.
 */
export function WaitlistAddForm({
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
  onSave: (body: JoinWaitlist) => void;
  t: T;
  locale: Locale;
}) {
  const services = config.mode === "services" ? config.services : null;
  const cap = config.mode === "capacity" ? config.capacity : null;
  const days = nextOpenDays(config, today, 7);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [serviceId, setServiceId] = useState(services?.catalog[0]?.id ?? "");
  const [proId, setProId] = useState<string | null>(null);
  // Servicios: «until» a week ahead by default (the web's 7 days); Aforo: the day they want.
  const [day, setDay] = useState<LocalDate>((services ? days.at(-1) : days[0]) ?? today);
  const [size, setSize] = useState(2);
  const [time, setTime] = useState<Minutes | null>(null);
  const [tried, setTried] = useState(false);

  const service = services?.catalog.find((s) => s.id === serviceId) ?? null;
  const team = (services?.team ?? []).filter((p) => !service || service.proIds === null || service.proIds.includes(p.id));
  const problem = phoneProblem(phone);
  const errors = {
    name: name.trim() ? null : t("reservas.wl.add.name.required"),
    phone: problem ? t(phoneProblemKey(problem, "reservas.phone.required.wait")) : null,
  };
  const times = cap ? slotsOfDay(config, day).map((s) => s.time) : [];

  const save = () => {
    if (saving || !online) return;
    setTried(true);
    if (errors.name || errors.phone || (services && !service)) {
      haptics.warning();
      return;
    }
    onSave(
      services
        ? { partySize: 1, name: name.trim(), phone: cleanPhone(phone), inPerson: false, serviceId, proId, date: null, time: null, until: day }
        : { partySize: size, name: name.trim(), phone: cleanPhone(phone), inPerson: false, date: day, time },
    );
  };

  return (
    <View style={styles.stack}>
      <Text variant="callout" tone="mutedForeground">
        {t("reservas.wl.add.subtitle")}
      </Text>
      <Section title={t("reservas.form.client")}>
        <FormField label={t("reservas.new.name")} value={name} onChangeText={setName} autoCapitalize="words" textContentType="name" autoComplete="name" error={tried ? errors.name : null} />
        <FormField
          label={t("reservas.phone.label")}
          value={phone}
          onChangeText={setPhone}
          keyboardType="phone-pad"
          textContentType="telephoneNumber"
          autoComplete="tel"
          placeholder={t("reservas.phone.placeholder")}
          hint={t("reservas.phone.hint.wait")}
          error={tried ? errors.phone : null}
        />
      </Section>

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
          <Section title={t("reservas.wl.add.until")}>
            <OpenDays days={days} value={day} today={today} onChange={setDay} t={t} locale={locale} />
            <Text variant="footnote" tone="mutedForeground">
              {t("reservas.wl.add.until.hint")}
            </Text>
          </Section>
        </>
      ) : cap ? (
        <>
          <Stepper label={t("reservas.new.party")} value={size} onChange={setSize} max={Math.max(cap.capacity, 1)} unit={cap.unit} t={t} />
          <Section title={t("reservas.new.day")}>
            <OpenDays
              days={days}
              value={day}
              today={today}
              onChange={(d) => {
                setDay(d);
                setTime(null);
              }}
              t={t}
              locale={locale}
            />
          </Section>
          <Section title={t("reservas.new.time")}>
            <View style={styles.wrap} accessibilityRole="radiogroup">
              <Chip label={t("reservas.wl.add.time.any")} on={time === null} onPress={() => setTime(null)} />
              {times.map((m) => (
                <Chip key={m} label={hhmm(m)} on={time === m} onPress={() => setTime(m)} />
              ))}
            </View>
          </Section>
        </>
      ) : null}

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
      <Button label={t("reservas.wl.add.save")} full busy={saving} disabled={!online} onPress={save} testID="wait-add-save" />
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 18 },
  chips: { gap: 8, paddingVertical: 2 },
  wrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
});
