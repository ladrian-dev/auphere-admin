import { Pressable, StyleSheet, View } from "react-native";

import type { WaitEntry } from "@/api/reservas";
import type { T } from "@/i18n/t";
import { CARD_RADIUS, RADII, useTheme } from "@/theme/theme";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import { firstName } from "./format";

/** «Lista de espera · 2 personas · Raúl, Inés» after the bookings (design §4.1, 7); only when someone waits. */
export function WaitlistCard({ items, onPress, t }: { items: WaitEntry[]; onPress: () => void; t: T }) {
  const { colors } = useTheme();
  const names = items.map((w) => firstName(w.name)).join(", ");
  const sub = items.length === 1 ? t("reservas.wl.card.one", { names }) : t("reservas.wl.card.many", { n: items.length, names });
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${t("reservas.waitlist.title")}. ${sub}`}
      onPress={onPress}
      testID="waitlist-card"
      style={({ pressed }) => [styles.wl, { backgroundColor: pressed ? colors.muted : colors.card, borderColor: colors.border, transform: [{ scale: pressed ? 0.985 : 1 }] }]}
    >
      <View style={[styles.wlIcon, { backgroundColor: colors.muted }]}>
        <Icon name={icons.waitlist} size={20} tone="mutedForeground" />
      </View>
      <View style={styles.flex}>
        <Text variant="bodyStrong">{t("reservas.waitlist.title")}</Text>
        <Text variant="footnote" tone="mutedForeground" numberOfLines={1}>
          {sub}
        </Text>
      </View>
      <Icon name={icons.chevron} size={18} tone="subtle" />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1, minWidth: 0 },
  wl: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12, paddingLeft: 14, paddingRight: 12, borderRadius: CARD_RADIUS - 2, borderWidth: StyleSheet.hairlineWidth * 2 },
  wlIcon: { width: 36, height: 36, borderRadius: RADII.md - 2, alignItems: "center", justifyContent: "center" },
});
