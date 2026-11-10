import { StyleSheet, View } from "react-native";

import type { Mode, Origin, ResState } from "@/api/reservas";
import { useT, type T } from "@/i18n/t";
import { useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";

import { Text } from "./text";

/**
 * The state of a reservation, in words and in a tone (spec 044, data-model.md
 * «Estados»): never colour alone. «Sin confirmar» also carries a border, as in
 * the design. «Llega tarde» is worked out, never stored, and goes over a
 * still-expected state.
 */
type Look = { label: string; bg: keyof Palette; fg: keyof Palette; border?: keyof Palette };

export function pillOf(r: { state: ResState; origin: Origin }, mode: Mode, late: number | null, t: T): Look {
  if (late !== null) return { label: t("reservas.state.late", { min: late }), bg: "warningBg", fg: "warningText" };
  switch (r.state) {
    case "pending":
      return { label: t("reservas.state.pending"), bg: "card", fg: "warningText", border: "warningSolid" };
    case "confirmed":
      return { label: t("reservas.state.confirmed"), bg: "positiveBg", fg: "positiveText" };
    case "arrived":
      return { label: t(r.origin === "walkin" ? "reservas.state.walkin" : "reservas.state.arrived"), bg: "accentDeep", fg: "accentSoft" };
    case "done":
      return { label: t(mode === "capacity" ? "reservas.state.done.capacity" : "reservas.state.done.services"), bg: "muted", fg: "mutedForeground" };
    case "noshow":
      return { label: t("reservas.state.noshow"), bg: "dangerBg", fg: "dangerText" };
    case "cancelled":
      return { label: t("reservas.state.cancelled"), bg: "muted", fg: "mutedForeground" };
  }
}

export function Pill({ state, origin, mode, late }: { state: ResState; origin: Origin; mode: Mode; late: number | null }) {
  const t = useT();
  const { colors, radius } = useTheme();
  const look = pillOf({ state, origin }, mode, late, t);
  return (
    <View
      testID={`pill-${late !== null ? "late" : state}`}
      style={[
        styles.pill,
        { backgroundColor: colors[look.bg], borderRadius: radius.full },
        look.border ? { borderColor: colors[look.border], borderStyle: "dashed", borderWidth: 1 } : { borderColor: "transparent", borderWidth: 1 },
      ]}
    >
      <Text variant="caption" tone={look.fg} numberOfLines={1}>
        {look.label}
      </Text>
    </View>
  );
}

/** «Choca con Google» (Servicios): over the state, worked out by the API. */
export function ConflictPill() {
  const t = useT();
  const { colors, radius } = useTheme();
  return (
    <View style={[styles.pill, { backgroundColor: colors.warningBg, borderRadius: radius.full, borderWidth: 1, borderColor: "transparent" }]}>
      <Text variant="caption" tone="warningText" numberOfLines={1}>
        {t("reservas.state.conflict")}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: { paddingHorizontal: 8, paddingVertical: 2, alignSelf: "flex-start", maxWidth: "100%" },
});
