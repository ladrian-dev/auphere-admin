import { useState } from "react";
import { Pressable, StyleSheet, Switch, View } from "react-native";

import type { CancelOptions, CancelPreview, Mode, Reservation } from "@/api/reservas";
import type { Locale, T } from "@/i18n/t";
import type { LocalDate } from "@/lib/reservas-model";
import { haptics } from "@/motion/haptics";
import { RADII, TOUCH, useTheme } from "@/theme/theme";
import { Button } from "@/ui/button";
import { Icon, icons } from "@/ui/icon";
import { Skeleton } from "@/ui/states";
import { switchColors } from "@/ui/switch-colors";
import { Text } from "@/ui/text";

import { firstName, nameOf, when } from "./format";

/**
 * «¿Cancelar esta reserva?» (spec 069, R14.2; the web's `cancel-dialog.tsx`;
 * design §5.3): in the sheet, before anything is sent. Whether to tell the
 * customer on WhatsApp — yes by default, and only with a phone — and, in
 * Servicios, whether the agent should offer the slot to the waitlist, as the
 * API's preview says (how many fit, or why it cannot). «Cancelar reserva»
 * passes the choices on; the screen then gives «Deshacer» before anything
 * goes out.
 */
export function CancelPanel({
  r,
  mode,
  preview,
  previewLoading,
  leadHours,
  today,
  busy = false,
  onConfirm,
  onBack,
  t,
  locale,
}: {
  r: Reservation;
  mode: Mode;
  /** `null` when there is none (Aforo, or it could not be read): no offer is asked. */
  preview: CancelPreview | null;
  previewLoading: boolean;
  leadHours: number;
  today: LocalDate;
  busy?: boolean;
  onConfirm: (opts: CancelOptions) => void;
  onBack: () => void;
  t: T;
  locale: Locale;
}) {
  const { colors } = useTheme();
  const phone = !!r.customer.phone;
  const [notify, setNotify] = useState(phone);
  const [offer, setOffer] = useState(true);
  const canOffer = mode === "services" && !!preview?.canOffer && preview.candidates > 0;
  const why = !canOffer && preview?.whyNot && preview.whyNot !== "not_services" ? preview.whyNot : null;
  const label = t("reservas.cancel.notify", { name: firstName(nameOf(r, t)) });

  return (
    <View style={styles.stack}>
      <View style={[styles.icon, { backgroundColor: colors.dangerBg }]} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
        <Icon name={icons.calendarX} size={28} tone="dangerText" />
      </View>
      <View style={styles.head}>
        <Text variant="dialogTitle" accessibilityRole="header" style={styles.center}>
          {t("reservas.cancel.ask")}
        </Text>
        <Text variant="callout" tone="mutedForeground" style={styles.center}>
          {`${nameOf(r, t)} · ${when(r, today, locale, t)}`}
        </Text>
      </View>

      {phone ? (
        <View style={[styles.row, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text variant="body" style={styles.flex}>
            {label}
          </Text>
          <Switch
            accessibilityRole="switch"
            accessibilityLabel={label}
            accessibilityState={{ checked: notify, disabled: busy }}
            value={notify}
            disabled={busy}
            onValueChange={(v) => {
              haptics.select();
              setNotify(v);
            }}
            {...switchColors(colors)}
          />
        </View>
      ) : (
        <Text variant="footnote" tone="mutedForeground">
          {t("reservas.cancel.body.noPhone")}
        </Text>
      )}

      {mode === "services" && previewLoading ? (
        <Skeleton rows={2} label={t("reservas.cancel.preview.loading")} />
      ) : canOffer && preview ? (
        <View style={styles.fieldset} accessibilityRole="radiogroup" accessibilityLabel={t("reservas.cancel.offer.question")}>
          <Text variant="subhead">{t("reservas.cancel.offer.question")}</Text>
          <Option
            on={offer}
            label={t("reservas.cancel.offer.yes")}
            hint={preview.candidates === 1 ? t("reservas.cancel.offer.yesHint.one") : t("reservas.cancel.offer.yesHint.other", { count: preview.candidates })}
            onPress={() => setOffer(true)}
          />
          <Option on={!offer} label={t("reservas.cancel.offer.no")} onPress={() => setOffer(false)} />
        </View>
      ) : why ? (
        <View style={[styles.note, { backgroundColor: colors.muted }]} accessibilityRole="text">
          <Text variant="footnote" tone="mutedForeground">
            {t(`reservas.cancel.why.${why}`, { lead: t("reservas.settings.hoursN", { h: leadHours }) })}
          </Text>
        </View>
      ) : null}

      <View style={styles.buttons}>
        <Button
          label={t("reservas.cancel.confirm")}
          variant="destructive"
          full
          busy={busy}
          disabled={mode === "services" && previewLoading}
          onPress={() => onConfirm({ notify: phone && notify, offerSlot: canOffer && offer })}
        />
        <Button label={t("reservas.cancel.keep")} variant="ghost" full disabled={busy} onPress={onBack} />
      </View>
    </View>
  );
}

function Option({ on, label, hint, onPress }: { on: boolean; label: string; hint?: string; onPress: () => void }) {
  const { colors } = useTheme();
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityLabel={label}
      accessibilityHint={hint}
      accessibilityState={{ checked: on }}
      onPress={() => {
        if (!on) haptics.select();
        onPress();
      }}
      style={({ pressed }) => [
        styles.option,
        { backgroundColor: pressed ? colors.muted : colors.card, borderColor: on ? colors.primary : colors.border, borderWidth: on ? 2 : 1 },
      ]}
    >
      <View style={[styles.radio, { borderColor: on ? colors.primary : colors.input }]}>{on ? <View style={[styles.radioDot, { backgroundColor: colors.primary }]} /> : null}</View>
      <View style={styles.flex}>
        <Text variant="body">{label}</Text>
        {hint ? (
          <Text variant="footnote" tone="mutedForeground">
            {hint}
          </Text>
        ) : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 16 },
  icon: { width: 64, height: 64, borderRadius: RADII.xl, alignItems: "center", justifyContent: "center", alignSelf: "center" },
  head: { gap: 6 },
  center: { textAlign: "center" },
  row: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: TOUCH, paddingHorizontal: 16, paddingVertical: 8, borderRadius: RADII.lg, borderWidth: StyleSheet.hairlineWidth * 2 },
  flex: { flex: 1, minWidth: 0 },
  fieldset: { gap: 8 },
  option: { flexDirection: "row", alignItems: "flex-start", gap: 12, minHeight: 52, padding: 12, borderRadius: RADII.lg },
  radio: { width: 22, height: 22, borderRadius: 11, borderWidth: 2, alignItems: "center", justifyContent: "center", marginTop: 1 },
  radioDot: { width: 12, height: 12, borderRadius: 6 },
  note: { padding: 12, borderRadius: RADII.md },
  buttons: { gap: 4 },
});
