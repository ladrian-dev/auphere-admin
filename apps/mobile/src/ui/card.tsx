import { StyleSheet, View, type ViewProps } from "react-native";

import { CARD_RADIUS, useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";

/** A raised surface. `tone` tints the border for a card that says a state. */
export function Card({ style, tone, ...rest }: ViewProps & { tone?: "danger" | "warning" | "positive" }) {
  const { colors } = useTheme();
  const border: keyof Palette = tone === "danger" ? "danger" : tone === "warning" ? "warningSolid" : tone === "positive" ? "positive" : "border";
  return (
    <View
      {...rest}
      style={[
        styles.card,
        { backgroundColor: colors.card, borderRadius: CARD_RADIUS, borderColor: colors[border] },
        style,
      ]}
    />
  );
}

const styles = StyleSheet.create({
  card: { padding: 16, gap: 8, borderWidth: StyleSheet.hairlineWidth * 2 },
});
