import { StyleSheet, View } from "react-native";

import type { T } from "@/i18n/t";
import { useTheme } from "@/theme/theme";
import { IconButton } from "@/ui/button";
import { icons } from "@/ui/icon";
import { Text } from "@/ui/text";

/**
 * «− N +» for a party (spec 044, R5.3, R6.2): two real buttons with their
 * names, and the value said with its unit. Never a gesture only.
 */
export function Stepper({
  label,
  value,
  onChange,
  min = 1,
  max,
  unit,
  t,
}: {
  label: string;
  value: number;
  onChange: (n: number) => void;
  min?: number;
  max: number;
  unit: string;
  t: T;
}) {
  const { colors, radius } = useTheme();
  return (
    <View style={styles.wrap}>
      <Text variant="subhead">{label}</Text>
      <View style={[styles.row, { borderColor: colors.input, borderRadius: radius.full }]}>
        <IconButton icon={icons.minus} label={t("reservas.stepper.minus")} disabled={value <= min} onPress={() => onChange(Math.max(min, value - 1))} />
        {/* One adjustable control for VoiceOver and TalkBack: swipe up or down, and the new value is said. */}
        <View
          accessible
          accessibilityRole="adjustable"
          accessibilityLabel={label}
          accessibilityValue={{ text: t("reservas.stepper.value", { n: value, unit }) }}
          accessibilityActions={[{ name: "increment" }, { name: "decrement" }]}
          onAccessibilityAction={(e) => {
            if (e.nativeEvent.actionName === "increment") onChange(Math.min(max, value + 1));
            if (e.nativeEvent.actionName === "decrement") onChange(Math.max(min, value - 1));
          }}
        >
          <Text variant="headline" style={styles.value}>
            {String(value)}
          </Text>
        </View>
        <IconButton icon={icons.plus} label={t("reservas.stepper.plus")} disabled={value >= max} onPress={() => onChange(Math.min(max, value + 1))} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 6 },
  row: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", borderWidth: 1, paddingHorizontal: 4 },
  value: { minWidth: 40, textAlign: "center", fontVariant: ["tabular-nums"] },
});
