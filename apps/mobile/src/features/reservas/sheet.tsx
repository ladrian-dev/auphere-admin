import { StyleSheet, View } from "react-native";

import type { ResEvent, Reservation, ResAction, ResConfig } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import { wallClock, type LocalDate } from "@/lib/reservas-model";
import { useTheme } from "@/theme/theme";
import { Button } from "@/ui/button";
import { Group, Row } from "@/ui/group";
import { ConflictPill, pillOf } from "@/ui/pill";
import { Text } from "@/ui/text";

import { duration, hhmm, nameOf, party, price, when } from "./format";

/**
 * A reservation, in its sheet (spec 044, Requisito 4): who and what, when,
 * with whom or how many, the channel and the state; then only the actions the
 * API allows for it now (`actions`) — «Llegó» and «No vino» today, «Marcar
 * confirmada» while unconfirmed, «Cancelar» while open and ahead — and where it
 * came from, with its history. Cancelling goes through a confirmation (it
 * tells a third party on WhatsApp); the rest act at once and can be undone
 * from the brief notice. Offline, nothing that writes.
 */
export function ReservaSheet({
  r,
  config,
  today,
  online,
  busy = false,
  error = null,
  onAct,
  onCancel,
  t,
  locale,
}: {
  r: Reservation;
  config: ResConfig;
  today: LocalDate;
  online: boolean;
  busy?: boolean;
  /** A refused action, said here: a notice would sit under the sheet on iOS (gate review). */
  error?: string | null;
  onAct: (action: ResAction) => void;
  onCancel: () => void;
  t: T;
  locale: Locale;
}) {
  const { colors } = useTheme();
  const capacity = config.mode === "capacity";
  const unit = config.capacity?.unit ?? "";
  const subtitle = r.service
    ? [r.service.name, duration(r.service.durationMin, t), r.service.price !== null ? price(r.service.price, config.currency, locale) : null].filter(Boolean).join(" · ")
    : r.partySize != null
      ? party(r.partySize, unit, t)
      : "";
  const late = capacity ? (r.lateMinutes ?? null) : null;
  const look = pillOf(r, config.mode, late, t);
  const origin =
    r.origin === "agent"
      ? t("reservas.origin.agent")
      : r.origin === "walkin"
        ? t("reservas.origin.walkin")
        : r.origin === "waitlist"
          ? t("reservas.origin.waitlist")
          : t("reservas.origin.person", { name: r.by ?? "" });
  const can = (a: ResAction) => online && r.actions.includes(a);
  // Oldest first, whatever order the API sends them in.
  const history = [...r.events]
    .sort((a, b) => Date.parse(a.at) - Date.parse(b.at))
    .map((e) => ({ at: e.at, text: eventText(e, config.mode, t) }))
    .filter((h): h is { at: string; text: string } => h.text !== null);
  const shown: ResAction[] = (["arrived", "noshow", "confirm", "undo"] as const).filter((a) => can(a) && !(a === "arrived" && !capacity));

  return (
    <View style={styles.stack}>
      <View style={styles.who}>
        {capacity && r.partySize != null ? (
          <View style={[styles.bubble, { backgroundColor: colors.accentSoft }]} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
            <Text variant="title" tone="accentDeep">
              {String(r.partySize)}
            </Text>
          </View>
        ) : null}
        <Text variant="title" accessibilityRole="header">
          {nameOf(r, t)}
        </Text>
        {subtitle ? (
          <Text variant="callout" tone="mutedForeground">
            {subtitle}
          </Text>
        ) : null}
      </View>

      <Group>
        <Row label={t("reservas.sheet.when")} value={when(r, today, locale, t)} />
        {capacity ? (
          <Row label={t("reservas.sheet.stay")} value={duration(config.capacity?.stayMin ?? 90, t)} />
        ) : r.pro ? (
          <Row label={t("reservas.sheet.with")} value={r.pro.name} />
        ) : null}
        <Row label={t("reservas.sheet.channel")} value={t(`reservas.channel.${r.channel}`)} />
        {r.customer.phone ? <Row label={t("reservas.sheet.phone")} value={r.customer.phone} /> : null}
        {/* The state is said once, as the row's value (first iOS pass); a clash with the calendar adds its own pill. */}
        <Row label={t("reservas.sheet.state")} value={look.label}>
          {r.conflict && r.state !== "cancelled" ? (
            <View style={styles.pills}>
              <ConflictPill />
            </View>
          ) : null}
        </Row>
      </Group>

      {error && online ? (
        <Text variant="callout" tone="dangerText" accessibilityRole="alert">
          {error}
        </Text>
      ) : null}
      {online ? (
        shown.length > 0 || can("cancel") ? (
          <View style={styles.actions}>
            {shown.map((a) => (
              <View key={a} style={styles.half}>
                <Button
                  label={t(`reservas.action.${a}`)}
                  variant={a === "noshow" || a === "undo" ? "secondary" : "primary"}
                  full
                  busy={busy}
                  onPress={() => onAct(a)}
                />
              </View>
            ))}
            {can("cancel") ? (
              <View style={styles.full}>
                <Button label={t("reservas.action.cancel")} variant="destructive" full disabled={busy} onPress={onCancel} />
              </View>
            ) : null}
          </View>
        ) : null
      ) : (
        <Text variant="footnote" tone="warningText" accessibilityRole="alert">
          {t("reservas.error.offline")}
        </Text>
      )}

      <View style={styles.section}>
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
          {t("reservas.sheet.origin")}
        </Text>
        <Text variant="body">{origin}</Text>
      </View>

      {history.length > 0 ? (
        <View style={styles.section}>
          <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
            {t("reservas.sheet.history")}
          </Text>
          {history.map((h, i) => (
            <View key={i} style={styles.event} accessible>
              <View style={[styles.dot, { backgroundColor: colors.border }]} />
              <Text variant="footnote" style={styles.flex}>
                {h.text}
                <Text variant="footnote" tone="mutedForeground">{` · ${historyTime(h.at, config.timezone, today, t)}`}</Text>
              </Text>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

/** «Hoy, 9:00» / «21/10, 22:14», in the business's zone (the API writes instants in UTC). */
function historyTime(at: string, tz: string, today: LocalDate, t: T): string {
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return "";
  const w = wallClock(tz, d);
  const time = hhmm(w.minutes);
  if (w.date === today) return `${t("reservas.today")}, ${time}`;
  return `${Number(w.date.slice(8, 10))}/${Number(w.date.slice(5, 7))}, ${time}`;
}

/**
 * One line of the history in words (043 §4 `events`: the API gives the kind,
 * the screen the sentence). A kind this version does not know is left out.
 */
export function eventText(e: ResEvent, mode: ResConfig["mode"], t: T): string | null {
  const who = e.actor ?? "";
  switch (e.kind) {
    case "created": {
      const origin = e.data.origin;
      if (origin === "walkin") return t("reservas.event.created.walkin");
      if (origin === "waitlist") return t("reservas.event.created.waitlist");
      if (origin === "person" || (who && e.data.channel !== "whatsapp")) return t("reservas.event.created.person", { name: who });
      return t("reservas.event.created.agent");
    }
    case "confirmed":
      return who ? t("reservas.event.confirmed.by", { name: who }) : t("reservas.event.confirmed");
    case "confirmation_requested":
      return t("reservas.event.confirmation_requested");
    case "reminder_sent":
      return t("reservas.event.reminder_sent");
    case "replied_yes":
      return t("reservas.event.replied_yes");
    case "replied_no":
      return t("reservas.event.replied_no");
    case "moved":
      return t("reservas.event.moved", { name: who || t("reservas.event.someone") });
    case "cancelled":
      return e.data.by === "customer"
        ? t("reservas.event.cancelled.customer")
        : e.data.by === "system"
          ? t("reservas.event.cancelled.system")
          : t("reservas.event.cancelled.by", { name: who || t("reservas.event.someone") });
    case "arrived":
      return t("reservas.event.arrived");
    case "noshow":
      return t("reservas.event.noshow");
    case "undone":
      return t("reservas.event.undone", { name: who || t("reservas.event.someone") });
    case "done":
      return mode === "capacity" ? t("reservas.state.done.capacity") : t("reservas.state.done.services");
    case "waitlist_joined":
      return t("reservas.event.waitlist_joined");
    case "waitlist_accepted":
      return t("reservas.event.waitlist_accepted");
    case "notified":
      return t("reservas.event.notified");
    case "notify_failed":
      return t("reservas.event.notify_failed");
    case "released":
      return t("reservas.event.released");
    default:
      return null;
  }
}

/** What the cancel confirmation says (clarification 2): the customer is told on WhatsApp, or cannot be. */
export function cancelCopy(r: Pick<Reservation, "customer">, t: T): { title: string; body: string } {
  return {
    title: t("reservas.cancel.title", { name: nameOf(r, t) }),
    body: r.customer.phone ? t("reservas.cancel.body") : t("reservas.cancel.body.noPhone"),
  };
}

const styles = StyleSheet.create({
  stack: { gap: 16 },
  who: { gap: 4, alignItems: "flex-start" },
  bubble: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center", marginBottom: 4 },
  pills: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  half: { flexBasis: "48%", flexGrow: 1 },
  full: { flexBasis: "100%" },
  section: { gap: 6 },
  event: { flexDirection: "row", gap: 8, alignItems: "flex-start" },
  dot: { width: 6, height: 6, borderRadius: 3, marginTop: 6 },
  flex: { flex: 1, minWidth: 0 },
});
