import { useEffect, useRef, useState } from "react";
import { AccessibilityInfo, Platform, StyleSheet, View } from "react-native";

import type { ResConfig, Slot } from "@/api/reservas";
import type { T } from "@/i18n/t";
import { currentSlot, hhmm, type WallTime } from "@/lib/reservas-model";
import { useTheme } from "@/theme/theme";
import { Button } from "@/ui/button";
import { Field } from "@/ui/field";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import { Stepper } from "./stepper";

/**
 * «Llegada sin reserva» (spec 044, Requisito 6): at the door, how many and,
 * if they say it, a name. It says live whether they fit — with the whole
 * capacity: the seats kept for walk-ins count here, and only here — and what
 * stays free until when; if not, the waitlist; outside the shifts, that there
 * is no service. The API has the last word when it is saved.
 */
export function WalkIn({
  config,
  slots,
  now,
  online,
  busy,
  error = null,
  onRegister,
  onWait,
  t,
}: {
  config: ResConfig;
  slots: Slot[];
  now: WallTime;
  online: boolean;
  busy: boolean;
  /** A refused arrival, said here: a notice would sit under the sheet on iOS. */
  error?: string | null;
  onRegister: (party: number, name: string | null) => void;
  onWait: (party: number, name: string | null) => void;
  t: T;
}) {
  const { colors, radius } = useTheme();
  const cap = config.capacity;
  const [party, setParty] = useState(2);
  const [name, setName] = useState("");
  const slot = cap ? currentSlot(config, now.date, now.minutes) : null;
  const window = !cap || slot === null ? [] : slots.filter((s) => s.date === now.date && s.time >= slot && s.time < slot + cap.stayMin);
  const inside = Math.max(0, ...window.map((s) => s.inside));
  const fits = !!cap && slot !== null && cap.capacity - inside >= party;
  const who = name.trim() || null;
  const message =
    !cap || slot === null
      ? { text: t("reservas.walkin.closed"), tone: "mutedForeground" as const, icon: icons.clock }
      : fits
        ? { text: t("reservas.walkin.fits", { left: cap.capacity - inside - party, until: hhmm(slot + cap.stayMin) }), tone: "positiveText" as const, icon: icons.check }
        : { text: t("reservas.walkin.full"), tone: "warningText" as const, icon: icons.warning };

  // Whether they fit is said aloud when it changes: Android reads the live region below,
  // iOS has none (gate review). Not on opening: the sheet's content is read then anyway.
  const said = useRef(message.text);
  useEffect(() => {
    if (said.current === message.text) return;
    said.current = message.text;
    if (Platform.OS === "ios") AccessibilityInfo.announceForAccessibility(message.text);
  }, [message.text]);

  if (!cap) return null;
  const unit = cap.unit;

  return (
    <View style={styles.stack}>
      <Text variant="title" accessibilityRole="header">
        {t("reservas.walkin.title")}
      </Text>
      <Stepper label={t("reservas.new.party")} value={party} onChange={setParty} max={cap.capacity} unit={unit} t={t} />
      <Field label={t("reservas.walkin.name")} value={name} onChangeText={setName} autoCapitalize="words" textContentType="name" returnKeyType="done" />
      <View
        accessible
        accessibilityRole="text"
        accessibilityLiveRegion="polite"
        style={[styles.message, { backgroundColor: colors.muted, borderRadius: radius.md }]}
      >
        <Icon name={message.icon} size={18} tone={message.tone} />
        <Text variant="callout" tone={message.tone} style={styles.flex}>
          {message.text}
        </Text>
      </View>
      {error && online ? (
        <Text variant="callout" tone="dangerText" accessibilityRole="alert">
          {error}
        </Text>
      ) : null}
      {!online ? (
        <Text variant="footnote" tone="warningText" accessibilityRole="alert">
          {t("reservas.error.offline")}
        </Text>
      ) : slot === null ? null : fits ? (
        <Button label={t("reservas.walkin.register")} full busy={busy} onPress={() => onRegister(party, who)} testID="walkin-register" />
      ) : (
        <Button label={t("reservas.walkin.wait")} variant="secondary" full busy={busy} onPress={() => onWait(party, who)} />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 16 },
  message: { flexDirection: "row", alignItems: "flex-start", gap: 10, padding: 12 },
  flex: { flex: 1, minWidth: 0 },
});
