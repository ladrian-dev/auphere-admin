import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, Switch, View } from "react-native";

import type { FreeSlot, MoveRequest, ResConfig, Reservation } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { earliestFrom, hhmm, nextOpenDays, type LocalDate, type WallTime } from "@/lib/reservas-model";
import { haptics } from "@/motion/haptics";
import { RADII, TOUCH, useTheme } from "@/theme/theme";
import { Button, IconButton } from "@/ui/button";
import { Chip } from "@/ui/chip";
import { icons } from "@/ui/icon";
import { switchColors } from "@/ui/switch-colors";
import { Text } from "@/ui/text";

import { firstName, nameOf, party, relativeDay, when } from "./format";
import { Section, type SlotQuery } from "./new-reservation";
import { OpenDays, slotCells, slotGroups, SlotGroups } from "./slot-picker";
import { Stepper } from "./stepper";

/**
 * «Mover la reserva» (spec 069, R14.3; the web's move dialog): the same day
 * strip and times as «Nueva reserva», asked to the API with this reservation
 * left out (`exclude`), so only free slots are offered and its own neighbours
 * are not blocked by it. Its current time is not offered. In Servicios, with
 * whom (the same person by default); in Aforo, how many. With a phone, whether
 * to tell the customer about the change (yes by default).
 */
export function MoveForm({
  r,
  config,
  today,
  now,
  slots,
  slotsLoading,
  slotsError = false,
  onRetrySlots,
  onQuery,
  onSave,
  saving,
  error,
  online,
  onClose,
  t,
  locale,
}: {
  r: Reservation;
  config: ResConfig;
  today: LocalDate;
  now: WallTime | null;
  slots: FreeSlot[] | null;
  slotsLoading: boolean;
  slotsError?: boolean;
  onRetrySlots?: () => void;
  onQuery: (q: SlotQuery) => void;
  onSave: (body: MoveRequest) => void;
  saving: boolean;
  error: string | null;
  online: boolean;
  onClose?: () => void;
  t: T;
  locale: Locale;
}) {
  const { colors } = useTheme();
  const services = config.mode === "services" ? config.services : null;
  const cap = config.mode === "capacity" ? config.capacity : null;
  const svc = services?.catalog.find((s) => s.id === r.service?.id) ?? null;
  const team = (services?.team ?? []).filter((p) => !svc || svc.proIds === null || svc.proIds.includes(p.id));
  const [proId, setProId] = useState<string | null>(r.pro?.id ?? null);
  const [date, setDate] = useState<LocalDate>(r.date < today ? today : r.date);
  const [size, setSize] = useState(r.partySize ?? 2);
  const [time, setTime] = useState<number | null>(null);
  const [tried, setTried] = useState(false);
  const phone = !!r.customer.phone;
  const [notify, setNotify] = useState(phone);
  const earliest = now ? earliestFrom(now, config.agent?.minNoticeMin ?? 60) : null;
  const days = nextOpenDays(config, today, 7);
  if (!days.includes(date)) days.unshift(date);

  useEffect(() => {
    onQuery(services ? { date, serviceId: r.service?.id, proId, exclude: r.id } : { date, partySize: size, exclude: r.id });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, proId, size]);

  // Its own time, with the same person and party, is where it already is.
  const same = date === r.date && (services ? proId === (r.pro?.id ?? null) : size === r.partySize);
  const cells = slots ? slotCells(config, date, slots, svc?.durationMin ?? r.end - r.start, earliest, same ? r.start : null) : [];
  const groups = slotGroups(config, cells, t);
  const picked = time !== null ? (cells.find((c) => c.time === time && c.state === "free") ?? null) : null;
  const name = nameOf(r, t);

  const save = () => {
    if (saving || !online) return;
    setTried(true);
    if (!picked) {
      haptics.warning();
      return;
    }
    onSave({
      date,
      time: picked.time,
      notify: phone && notify,
      ...(services ? { proId: picked.pro?.id ?? proId } : { partySize: size }),
    });
  };

  const summary = picked
    ? services
      ? t("reservas.new.summary.services", { day: relativeDay(date, today, locale, t), time: hhmm(picked.time), service: r.service?.name ?? "", pro: firstName(picked.pro?.name ?? team.find((p) => p.id === proId)?.name ?? "") })
      : t("reservas.new.summary.capacity", { day: relativeDay(date, today, locale, t), time: hhmm(picked.time), party: party(size, cap?.unit ?? "", t) })
    : t("reservas.new.pick");
  const notifyLabel = t("reservas.move.notify", { name: firstName(name) });

  return (
    <View style={styles.stack}>
      <View style={styles.head}>
        <View style={styles.flex}>
          <Text variant="sheetTitle" accessibilityRole="header">
            {t("reservas.move.title")}
          </Text>
          <Text variant="callout" tone="mutedForeground">
            {t("reservas.move.subtitle", { name, when: when(r, today, locale, t) })}
          </Text>
        </View>
        {onClose ? <IconButton icon={icons.close} label={t("reservas.form.close")} tone="foreground" onPress={onClose} /> : null}
      </View>

      {services ? (
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
      ) : cap ? (
        <Stepper label={t("reservas.new.party")} value={size} onChange={setSize} max={Math.max(cap.capacity - cap.walkinReserved, 1)} unit={cap.unit} t={t} />
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
        {tried && !picked ? (
          <Text variant="footnote" tone="dangerText" accessibilityRole="alert">
            {t("reservas.form.time.required")}
          </Text>
        ) : null}
      </Section>

      {phone ? (
        <View style={[styles.row, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text variant="body" style={styles.flex}>
            {notifyLabel}
          </Text>
          <Switch
            accessibilityRole="switch"
            accessibilityLabel={notifyLabel}
            accessibilityState={{ checked: notify }}
            value={notify}
            onValueChange={(v) => {
              haptics.select();
              setNotify(v);
            }}
            {...switchColors(colors)}
          />
        </View>
      ) : null}

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
      <Button label={t("reservas.move.save")} full busy={saving} disabled={!online} onPress={save} testID="move-save" />
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 18 },
  head: { flexDirection: "row", alignItems: "flex-start", gap: 8 },
  flex: { flex: 1, minWidth: 0 },
  chips: { gap: 8, paddingVertical: 2 },
  row: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: TOUCH, paddingHorizontal: 16, paddingVertical: 8, borderRadius: RADII.lg, borderWidth: StyleSheet.hairlineWidth * 2 },
});
