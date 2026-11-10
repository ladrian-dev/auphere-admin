import { StyleSheet, View } from "react-native";

import type { Reservation, ResConfig } from "@/api/reservas";
import { firstName, nameOf, party } from "@/features/reservas/format";
import type { T } from "@/i18n/t";
import { arrivingNextHour, daySummary, hhmm, insideAt, upcoming, type WallTime } from "@/lib/reservas-model";
import { RowButton } from "@/ui/bits";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Pill } from "@/ui/pill";
import { Skeleton } from "@/ui/states";
import { Text } from "@/ui/text";

/**
 * «Hoy en Reservas» on Inicio (spec 044, R9.1, R9.4, research D4): counted from
 * the very read the Reservas tab makes for today, so the two never disagree.
 * `null` is a client without the module: nothing at all (R1.2).
 */
export type TodayReservas =
  | { state: "loading" }
  | { state: "error"; retry: () => void }
  | { state: "ready"; config: ResConfig; items: Reservation[]; now: WallTime; waitlist: number | null };

/** Today's reservations still unconfirmed: the attention block's count (R9.1). */
export function unconfirmedToday(r: TodayReservas | null): number {
  if (!r || r.state !== "ready") return 0;
  return r.items.filter((x) => x.date === r.now.date && x.state === "pending").length;
}

export function TodayCard({ today, onReservas, t }: { today: TodayReservas; onReservas: () => void; t: T }) {
  return (
    <Card testID="home-reservas">
      <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
        {t("app.home.today.title")}
      </Text>
      {today.state === "loading" ? (
        <Skeleton rows={2} label={t("reservas.loading")} />
      ) : today.state === "error" ? (
        <View style={styles.error}>
          <Text variant="callout" tone="mutedForeground" style={styles.flex}>
            {t("reservas.error")}
          </Text>
          <Button label={t("app.retry")} variant="secondary" compact onPress={today.retry} />
        </View>
      ) : (
        <Ready today={today} t={t} />
      )}
      <View style={styles.bleed}>
        <RowButton title={t("app.home.reservas.see")} tone="primaryText" kind="push" onPress={onReservas} />
      </View>
    </Card>
  );
}

function Ready({ today, t }: { today: Extract<TodayReservas, { state: "ready" }>; t: T }) {
  const { config, items, now, waitlist } = today;
  const day = items.filter((r) => r.date === now.date);
  const next = upcoming(day, now);
  const sum = daySummary(day);
  const cap = config.capacity;
  return (
    <View style={styles.stack}>
      {cap ? (
        <>
          <Text variant="headline">{t("app.home.today.inside", { inside: insideAt(day, now.date, now.minutes, cap.stayMin), capacity: cap.capacity })}</Text>
          <Text variant="footnote" tone="mutedForeground">
            {waitlist !== null
              ? t("app.home.today.arriving", { n: arrivingNextHour(day, now), unit: cap.unit, w: waitlist })
              : t("app.home.today.arriving.noWait", { n: arrivingNextHour(day, now), unit: cap.unit })}
          </Text>
        </>
      ) : (
        <>
          <Text variant="headline">{sum.total === 1 ? t("app.home.today.services.one") : t("app.home.today.services", { n: sum.total })}</Text>
          {next[0] ? (
            <Text variant="footnote" tone="mutedForeground">
              {t("app.home.today.next", { time: hhmm(next[0].start), n: sum.unconfirmed })}
            </Text>
          ) : null}
        </>
      )}
      {next.length === 0 ? (
        <Text variant="callout" tone="mutedForeground">
          {t("app.home.today.none")}
        </Text>
      ) : (
        next.map((r) => (
          <View key={r.id} style={styles.row} accessible>
            <Text variant="bodyStrong" style={styles.time} numberOfLines={1}>
              {hhmm(r.start)}
            </Text>
            {/* The state under the name: beside it, large text squeezed the name (gate review). */}
            <View testID={`today-${r.id}-body`} style={styles.body}>
              <Text variant="body" numberOfLines={1}>
                {nameOf(r, t)}
              </Text>
              <Text variant="footnote" tone="mutedForeground" numberOfLines={1}>
                {r.service && r.pro
                  ? t("reservas.service.with", { service: r.service.name, pro: firstName(r.pro.name) })
                  : `${party(r.partySize ?? 0, cap?.unit ?? "", t)} · ${t(`reservas.channel.${r.channel}`)}`}
              </Text>
              <Pill state={r.state} origin={r.origin} mode={config.mode} late={null} />
            </View>
          </View>
        ))
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 8 },
  row: { flexDirection: "row", alignItems: "flex-start", gap: 10, paddingVertical: 4 },
  time: { minWidth: 52, fontVariant: ["tabular-nums"] },
  body: { flex: 1, minWidth: 0, gap: 4, alignItems: "flex-start" },
  flex: { flex: 1, minWidth: 0 },
  error: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  bleed: { marginHorizontal: -16, marginBottom: -8 },
});
