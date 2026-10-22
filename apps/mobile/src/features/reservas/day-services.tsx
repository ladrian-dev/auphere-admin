import { Fragment } from "react";
import { Pressable, ScrollView, StyleSheet, View } from "react-native";

import type { Reservation, ResConfig } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { daySummary, isClosed, isPast, type LocalDate, type WallTime } from "@/lib/reservas-model";
import { CARD_RADIUS, useTheme } from "@/theme/theme";
import { Chip } from "@/ui/chip";
import { icons } from "@/ui/icon";
import { ConflictPill, Pill, pillOf } from "@/ui/pill";
import { EmptyState } from "@/ui/states";
import { Text } from "@/ui/text";

import { durationShort, firstName, hhmm, nameOf, spoken } from "./format";

/**
 * Servicios · Día · Lista (spec 044, R2.4, R2.5, R2.10): the summary of the
 * day, a chip per team member, and one row per reservation — time and length,
 * the customer, «service · person» and the state in words — with the «Ahora»
 * line between rows today and the past ones in a quieter ink (never a drop in
 * opacity). A closed day says where that comes from.
 */
export function DayServices({
  config,
  items,
  now,
  date,
  pro,
  onPro,
  onOpen,
  t,
  locale,
}: {
  config: ResConfig;
  items: Reservation[];
  now: WallTime;
  date: LocalDate;
  pro: string | null;
  onPro: (id: string | null) => void;
  onOpen: (r: Reservation) => void;
  t: T;
  locale: Locale;
}) {
  const team = config.services?.team ?? [];
  const day = items.filter((r) => r.date === date && (pro === null || r.pro?.id === pro)).sort((a, b) => a.start - b.start);
  const sum = daySummary(day);
  const closed = isClosed(config, date);
  const nowIndex = date === now.date ? day.findIndex((r) => r.start >= now.minutes) : -2;

  return (
    <View style={styles.stack}>
      {team.length > 1 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chips} accessibilityRole="radiogroup" accessibilityLabel={t("reservas.team.filter")}>
          <Chip label={t("reservas.team.all")} on={pro === null} onPress={() => onPro(null)} />
          {team.map((p) => (
            <Chip key={p.id} label={firstName(p.name)} accessibilityLabel={p.name} on={pro === p.id} onPress={() => onPro(p.id)} />
          ))}
        </ScrollView>
      ) : null}

      {closed && day.length === 0 ? (
        <EmptyState icon={icons.calendar} title={t("reservas.day.closed")} />
      ) : day.length === 0 && pro !== null ? (
        // Filtered: the person has nothing, not the day (gate review).
        <EmptyState
          icon={icons.calendar}
          title={t("reservas.day.empty.pro", { name: team.find((p) => p.id === pro)?.name ?? "" })}
          action={{ label: t("reservas.team.allAction"), onPress: () => onPro(null) }}
        />
      ) : day.length === 0 ? (
        <EmptyState icon={icons.calendar} title={t("reservas.day.empty")} />
      ) : (
        <>
          <Text variant="subhead" tone="mutedForeground">
            {sum.total === 1 ? t("reservas.summary.one", { unconfirmed: sum.unconfirmed }) : t("reservas.summary", { total: sum.total, unconfirmed: sum.unconfirmed })}
          </Text>
          <ListCard>
            {day.map((r, i) => (
              <Fragment key={r.id}>
                {i === nowIndex ? <NowLine now={now} t={t} /> : null}
                <ServicesRow r={r} past={isPast(r, now)} first={i === 0 && i !== nowIndex} config={config} t={t} locale={locale} onOpen={onOpen} />
              </Fragment>
            ))}
            {nowIndex === -1 ? <NowLine now={now} t={t} /> : null}
          </ListCard>
        </>
      )}
    </View>
  );
}

export function ListCard({ children }: { children: React.ReactNode }) {
  const { colors } = useTheme();
  return <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border, borderRadius: CARD_RADIUS }]}>{children}</View>;
}

export function NowLine({ now, t }: { now: WallTime; t: T }) {
  const { colors } = useTheme();
  return (
    <View style={styles.now} accessibilityRole="text">
      <View style={[styles.nowDot, { backgroundColor: colors.danger }]} />
      <Text variant="caption" tone="dangerText">
        {t("reservas.now", { time: hhmm(now.minutes) })}
      </Text>
      <View style={[styles.nowRule, { backgroundColor: colors.danger }]} />
    </View>
  );
}

export function ServicesRow({
  r,
  past,
  first,
  config,
  t,
  locale,
  onOpen,
}: {
  r: Reservation;
  past: boolean;
  first: boolean;
  config: ResConfig;
  t: T;
  locale: Locale;
  onOpen: (r: Reservation) => void;
}) {
  const { colors } = useTheme();
  const look = pillOf(r, "services", null, t);
  const label = `${spoken(r, look.label, t, "")}${r.conflict ? `, ${t("reservas.state.conflict")}` : ""}${past ? `, ${t("reservas.row.past")}` : ""}`;
  const ink = past || r.state === "cancelled" ? "mutedForeground" : "foreground";
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={() => onOpen(r)}
      android_ripple={{ color: colors.muted }}
      testID={`res-${r.id}`}
      style={({ pressed }) => [styles.row, !first ? { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: colors.border } : null, pressed ? { backgroundColor: colors.muted } : null]}
    >
      <View style={styles.time}>
        <Text variant="bodyStrong" tone={ink} style={styles.num} numberOfLines={1}>
          {hhmm(r.start)}
        </Text>
        <Text variant="caption" tone="mutedForeground" numberOfLines={1}>
          {durationShort(r.service ? r.service.durationMin : r.end - r.start, t)}
        </Text>
      </View>
      <View style={styles.body}>
        <Text variant="body" tone={ink} numberOfLines={1}>
          {nameOf(r, t)}
        </Text>
        {r.service && r.pro ? (
          <Text variant="footnote" tone="mutedForeground" numberOfLines={2}>
            {t("reservas.service.with", { service: r.service.name, pro: firstName(r.pro.name) })}
          </Text>
        ) : null}
        <View style={styles.pills}>
          <Pill state={r.state} origin={r.origin} mode={config.mode} late={null} />
          {r.conflict && r.state !== "cancelled" ? <ConflictPill /> : null}
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 12 },
  chips: { gap: 8, paddingVertical: 2 },
  card: { borderWidth: StyleSheet.hairlineWidth * 2, overflow: "hidden" },
  row: { flexDirection: "row", gap: 12, paddingHorizontal: 16, paddingVertical: 12, minHeight: 64 },
  time: { minWidth: 56, gap: 2 }, // grows with large text rather than break the time (gate review)
  num: { fontVariant: ["tabular-nums"] },
  body: { flex: 1, minWidth: 0, gap: 4 },
  pills: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  now: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 12, paddingVertical: 4 },
  nowDot: { width: 8, height: 8, borderRadius: 4 },
  nowRule: { flex: 1, height: StyleSheet.hairlineWidth * 2 },
});
