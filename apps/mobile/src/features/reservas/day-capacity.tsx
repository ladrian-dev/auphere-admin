import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import type { Reservation, ResAction, ResConfig, Slot } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import {
  arrivingNextHour,
  currentSlot,
  daySummary,
  insideAt,
  isClosed,
  lateBy,
  occupancyLevel,
  type LocalDate,
  type WallTime,
} from "@/lib/reservas-model";
import { CARD_RADIUS, useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";
import { Button } from "@/ui/button";
import { Group, Row } from "@/ui/group";
import { icons } from "@/ui/icon";
import { Pill, pillOf } from "@/ui/pill";
import { EmptyState } from "@/ui/states";
import { Text } from "@/ui/text";

import { hhmm, nameOf, party, spoken } from "./format";

/**
 * Aforo · Día (spec 044, R2.7–R2.10, research D9): three figures in the 042's
 * grouped list (today: inside now, the next hour, unconfirmed; another day:
 * booked people, bookings, unconfirmed), the strip of the day's arrival times
 * with who is inside at each — a slot filters the day — and the bookings
 * grouped by hour, with «Llegó» and «No vino» where the API allows them and
 * «Llega tarde» worked out. Offline, nothing that writes is offered.
 */
export function DayCapacity({
  config,
  items,
  slots,
  now,
  date,
  slot,
  onSlot,
  onOpen,
  onAct,
  online,
  t,
  locale,
}: {
  config: ResConfig;
  items: Reservation[];
  slots: Slot[];
  now: WallTime;
  date: LocalDate;
  slot: number | null;
  onSlot: (time: number | null) => void;
  onOpen: (r: Reservation) => void;
  onAct: (r: Reservation, action: ResAction) => void;
  online: boolean;
  t: T;
  locale: Locale;
}) {
  const cap = config.capacity;
  if (!cap) return null;
  const day = items.filter((r) => r.date === date).sort((a, b) => a.start - b.start);
  const today = date === now.date;
  const sum = daySummary(day);
  const daySlots = slots.filter((s) => s.date === date).sort((a, b) => a.time - b.time);
  const unit = cap.unit;

  if (isClosed(config, date) && day.length === 0) return <EmptyState icon={icons.calendar} title={t("reservas.day.closed")} />;

  const booked = day.filter((r) => r.state !== "cancelled" && r.state !== "noshow").reduce((a, r) => a + (r.partySize ?? 0), 0);
  const under = today ? currentSlot(config, date, now.minutes) : null;
  const visible = day.filter((r) => slot === null || r.start === slot);
  const times = [...new Set(visible.map((r) => r.start))];

  return (
    <View style={styles.stack}>
      <Group testID="capacity-figures">
        {today ? (
          <Row
            label={t("reservas.capacity.inside")}
            value={t("reservas.capacity.inside.value", { inside: insideAt(day, date, now.minutes, cap.stayMin), capacity: cap.capacity })}
          />
        ) : (
          <Row label={t("reservas.capacity.booked")} value={party(booked, unit, t)} />
        )}
        {today ? (
          <Row label={t("reservas.capacity.nextHour")} value={String(arrivingNextHour(day, now))} />
        ) : (
          <Row label={t("reservas.capacity.count")} value={String(sum.total)} />
        )}
        <Row label={t("reservas.capacity.unconfirmed")} value={String(sum.unconfirmed)} valueTone={sum.unconfirmed > 0 ? "warningText" : "foreground"} />
      </Group>

      {daySlots.length > 0 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.strip} accessibilityLabel={t("reservas.capacity.slots")}>
          {daySlots.map((s, i) => (
            <SlotCell
              key={s.time}
              s={s}
              gap={i > 0 && s.time - (daySlots[i - 1]?.time ?? s.time) > 60}
              on={slot === s.time}
              now={under === s.time}
              t={t}
              onPress={() => onSlot(slot === s.time ? null : s.time)}
            />
          ))}
        </ScrollView>
      ) : null}

      {slot !== null ? (
        <View style={styles.filter}>
          <Text variant="subhead" tone="mutedForeground" style={styles.flex}>
            {t("reservas.slot.only", { time: hhmm(slot) })}
          </Text>
          <Button label={t("reservas.slot.all")} variant="ghost" compact onPress={() => onSlot(null)} />
        </View>
      ) : null}

      {visible.length === 0 ? (
        // Filtered to a slot, it is that hour that is empty; «Ver todo el día» is just above.
        <EmptyState icon={icons.calendar} title={slot !== null ? t("reservas.day.empty.slot", { time: hhmm(slot) }) : t("reservas.day.empty")} />
      ) : (
        times.map((time) => {
          const group = visible.filter((r) => r.start === time);
          const live = group.filter((r) => r.state !== "cancelled");
          const people = live.reduce((a, r) => a + (r.partySize ?? 0), 0);
          const s = daySlots.find((x) => x.time === time);
          const head = [
            hhmm(time),
            under === time ? t("reservas.group.now") : null,
            live.length === 1 ? t("reservas.group.head.one", { people, unit }) : t("reservas.group.head", { n: live.length, people, unit }),
            s ? t("reservas.group.of", { inside: s.inside, capacity: s.capacity }) : null,
          ]
            .filter(Boolean)
            .join(" · ");
          return (
            <Group key={time} title={s?.blocked ? `${head} · ${t("reservas.group.blocked", { reason: s.blocked })}` : head}>
              {group.map((r) => (
                <CapacityRow key={r.id} r={r} now={now} config={config} online={online} t={t} locale={locale} onOpen={onOpen} onAct={onAct} />
              ))}
            </Group>
          );
        })
      )}
    </View>
  );
}

function SlotCell({ s, gap, on, now, t, onPress }: { s: Slot; gap: boolean; on: boolean; now: boolean; t: T; onPress: () => void }) {
  const { colors, radius } = useTheme();
  const level = occupancyLevel(s.inside, s.capacity);
  const fill: keyof Palette = level === "full" ? "danger" : level === 3 ? "warningSolid" : "positive";
  const pct = Math.min(1, s.capacity > 0 ? s.inside / s.capacity : 0);
  const said = s.blocked ? t("reservas.slot.a11y.blocked", { time: hhmm(s.time), reason: s.blocked }) : t("reservas.slot.a11y", { time: hhmm(s.time), inside: s.inside, capacity: s.capacity });
  // The slot under way is said and drawn apart (dashed) from the chosen one (solid): in dark,
  // `primary` and `primaryText` are the same green (gate review).
  const label = now ? t("reservas.slot.now", { label: said }) : said;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{ selected: on }}
      onPress={onPress}
      android_ripple={{ color: colors.muted }}
      style={({ pressed }) => [
        styles.slot,
        gap ? styles.slotGap : null,
        {
          borderRadius: radius.md,
          borderColor: on ? colors.primaryText : now ? colors.primary : colors.border,
          borderWidth: on || now ? 2 : StyleSheet.hairlineWidth * 2,
          borderStyle: now && !on ? "dashed" : "solid",
          backgroundColor: pressed ? colors.muted : colors.card,
        },
      ]}
    >
      <Text variant="caption" tone="mutedForeground" maxFontSizeMultiplier={1.4}>
        {hhmm(s.time)}
      </Text>
      <View style={[styles.track, { backgroundColor: colors.muted, borderRadius: radius.sm }]}>
        {s.blocked ? (
          <View style={[styles.blocked, { borderColor: colors.subtle }]} />
        ) : (
          <View style={[styles.fill, { height: `${pct * 100}%`, backgroundColor: colors[fill], borderRadius: radius.sm }]} />
        )}
      </View>
      <Text variant="caption" tone="foreground" style={styles.num} maxFontSizeMultiplier={1.4}>
        {s.blocked ? "—" : String(s.inside)}
      </Text>
    </Pressable>
  );
}

function CapacityRow({
  r,
  now,
  config,
  online,
  t,
  locale,
  onOpen,
  onAct,
}: {
  r: Reservation;
  now: WallTime;
  config: ResConfig;
  online: boolean;
  t: T;
  locale: Locale;
  onOpen: (r: Reservation) => void;
  onAct: (r: Reservation, action: ResAction) => void;
}) {
  const { colors } = useTheme();
  const stay = config.capacity?.stayMin ?? 90;
  // The API's `late_minutes` when it gives it (043 §4); worked out the same way otherwise.
  const late = r.lateMinutes ?? lateBy(r, now, stay);
  const look = pillOf(r, "capacity", late, t);
  const unit = config.capacity?.unit ?? "";
  const sub = r.arrivedLocal ? t("reservas.arrivedAt", { time: r.arrivedLocal }) : t(`reservas.channel.${r.channel}`);
  const ink = r.state === "cancelled" || r.state === "noshow" || r.state === "done" ? "mutedForeground" : "foreground";
  return (
    <View testID={`res-${r.id}`} style={styles.rowWrap}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`${spoken(r, look.label, t, unit)}, ${sub}`}
        onPress={() => onOpen(r)}
        android_ripple={{ color: colors.muted }}
        style={({ pressed }) => [styles.row, pressed ? { backgroundColor: colors.muted } : null]}
      >
        <View style={[styles.bubble, { backgroundColor: colors.accentSoft }]} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
          <Text variant="bodyStrong" tone="accentDeep" maxFontSizeMultiplier={1.4}>
            {String(r.partySize ?? 0)}
          </Text>
        </View>
        <View style={styles.body}>
          <Text variant="body" tone={ink} numberOfLines={1}>
            {nameOf(r, t)}
          </Text>
          <Text variant="footnote" tone="mutedForeground" numberOfLines={1}>
            {sub}
          </Text>
          <Pill state={r.state} origin={r.origin} mode="capacity" late={late} />
        </View>
      </Pressable>
      {online && (r.actions.includes("arrived") || r.actions.includes("noshow")) ? (
        <View style={styles.actions}>
          {r.actions.includes("arrived") ? <Button label={t("reservas.action.arrived")} compact onPress={() => onAct(r, "arrived")} /> : null}
          {r.actions.includes("noshow") ? <Button label={t("reservas.action.noshow")} variant="secondary" compact onPress={() => onAct(r, "noshow")} /> : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 16 },
  flex: { flex: 1, minWidth: 0 },
  strip: { gap: 6, paddingVertical: 2 },
  slot: { width: 56, alignItems: "center", gap: 4, paddingVertical: 8 },
  slotGap: { marginLeft: 12 },
  track: { width: 14, height: 44, justifyContent: "flex-end", overflow: "hidden" },
  fill: { width: "100%" },
  blocked: { flex: 1, borderWidth: 2, borderStyle: "dashed" },
  num: { fontVariant: ["tabular-nums"] },
  filter: { flexDirection: "row", alignItems: "center", gap: 8 },
  rowWrap: { borderRadius: CARD_RADIUS },
  row: { flexDirection: "row", gap: 12, paddingHorizontal: 16, paddingVertical: 12, alignItems: "flex-start" },
  bubble: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  body: { flex: 1, minWidth: 0, gap: 4 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 8, paddingHorizontal: 16, paddingBottom: 12, paddingLeft: 64 },
});
