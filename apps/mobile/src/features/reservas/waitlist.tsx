import { StyleSheet, View } from "react-native";

import type { ResConfig, WaitEntry } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { hhmm, type LocalDate } from "@/lib/reservas-model";
import { useTheme } from "@/theme/theme";
import { Badge } from "@/ui/bits";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { icons } from "@/ui/icon";
import { EmptyState } from "@/ui/states";
import { Text } from "@/ui/text";

import { party, relativeDay } from "./format";

/**
 * «Lista de espera» (spec 044, Requisito 7): how it works in this mode, then a
 * card per person — what they ask for, where they stand (an offer counts down
 * its minutes), how it was put there — with «Ofrecer ahora» when they fit and
 * «Quitar». The agent does the offering by WhatsApp; this only starts it.
 */
export function WaitlistView({
  config,
  items,
  now,
  today,
  online,
  busy = false,
  onOffer,
  onRemove,
  t,
  locale,
}: {
  config: ResConfig;
  items: WaitEntry[];
  /** The phone's clock, in ms: offers count down in real time. */
  now: number;
  today: LocalDate;
  online: boolean;
  /** An offer or a removal on its way: the buttons wait (no second tap with stale data). */
  busy?: boolean;
  onOffer: (w: WaitEntry) => void;
  onRemove: (w: WaitEntry) => void;
  t: T;
  locale: Locale;
}) {
  const { colors, radius } = useTheme();
  const capacity = config.mode === "capacity";
  return (
    <View style={styles.stack}>
      <View style={[styles.explain, { backgroundColor: colors.muted, borderRadius: radius.md }]}>
        <Text variant="callout" tone="mutedForeground">
          {config.waitlist.enabled ? t(capacity ? "reservas.waitlist.explain.capacity" : "reservas.waitlist.explain.services") : t("reservas.waitlist.off")}
        </Text>
      </View>
      {items.length === 0 ? (
        <EmptyState icon={icons.waitlist} title={t("reservas.waitlist.empty")} />
      ) : (
        items.map((w) => {
          const wants = capacity
            ? t("reservas.waitlist.wants.capacity", {
                party: party(w.wants.partySize ?? 0, config.capacity?.unit ?? "", t),
                day: w.wants.date ? relativeDay(w.wants.date, today, locale, t) : "",
                time: w.wants.time != null ? hhmm(w.wants.time) : "",
              })
            : w.wants.service
              ? w.wants.pro
                ? t("reservas.waitlist.wants.services", { service: w.wants.service, pro: w.wants.pro })
                : t("reservas.waitlist.wants.anyPro", { service: w.wants.service })
              : "";
          const minutes = w.offeredUntil ? Math.ceil((Date.parse(w.offeredUntil) - now) / 60_000) : 0;
          const status =
            w.state === "offered"
              ? { label: minutes > 0 ? t("reservas.waitlist.offered", { min: minutes }) : t("reservas.waitlist.offered.late"), tone: "info" as const }
              : w.state === "accepted"
                ? { label: t("reservas.waitlist.accepted"), tone: "positive" as const }
                : w.fits === true
                  ? { label: t("reservas.waitlist.fits"), tone: "positive" as const }
                  : w.fits === false
                    ? { label: t("reservas.waitlist.noFit"), tone: "warning" as const }
                    : { label: t("reservas.waitlist.waiting"), tone: "neutral" as const };
          const joined = joinedWhen(w.joinedAt, today, t);
          const by = w.joinedBy === "agent" ? t("reservas.waitlist.by.agent", { when: joined }) : t("reservas.waitlist.by.person", { name: w.by ?? "", when: joined });
          return (
            <Card key={w.id} testID={`wait-${w.id}`}>
              {/* The name has the whole width; where they stand goes under it (a long status squeezed it, first iOS pass). */}
              <View testID={`wait-${w.id}-head`} style={styles.head}>
                <Text variant="headline">{w.name}</Text>
                <Badge label={status.label} tone={status.tone} />
              </View>
              {wants ? <Text variant="callout">{wants}</Text> : null}
              {w.wants.text ? (
                <Text variant="callout" tone="mutedForeground">
                  {w.wants.text}
                </Text>
              ) : null}
              {capacity && w.state === "waiting" && w.fits !== null ? (
                <Text variant="footnote" tone={w.fits ? "positiveText" : "mutedForeground"}>
                  {w.fits ? t("reservas.waitlist.fit.yes") : t("reservas.waitlist.fit.no")}
                </Text>
              ) : null}
              <Text variant="footnote" tone="mutedForeground">
                {by}
              </Text>
              {online && w.state !== "accepted" ? (
                <View style={styles.actions}>
                  {/* Offering by hand is Aforo's (043 §7); in Servicios the agent offers when someone cancels. */}
                  {capacity && w.state === "waiting" && w.fits === true ? <Button label={t("reservas.waitlist.offer")} compact busy={busy} onPress={() => onOffer(w)} /> : null}
                  <Button label={t("reservas.waitlist.remove")} variant="secondary" compact disabled={busy} onPress={() => onRemove(w)} />
                </View>
              ) : null}
            </Card>
          );
        })
      )}
    </View>
  );
}

/** «hoy, 9:05» / «ayer» / «21/10», from an ISO with the business's offset. */
function joinedWhen(at: string, today: LocalDate, t: T): string {
  const date = at.slice(0, 10);
  if (date === today) return `${t("reservas.today").toLocaleLowerCase()}, ${at.slice(11, 16)}`;
  const y = new Date(`${today}T12:00:00Z`);
  y.setUTCDate(y.getUTCDate() - 1);
  if (date === y.toISOString().slice(0, 10)) return t("reservas.yesterday");
  return `${Number(date.slice(8, 10))}/${Number(date.slice(5, 7))}`;
}

const styles = StyleSheet.create({
  stack: { gap: 12 },
  explain: { padding: 12 },
  head: { alignItems: "flex-start", gap: 6 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 8, paddingTop: 4 },
});
