import { StyleSheet, View } from "react-native";

import type { Mode, Origin, ResState } from "@/api/reservas";
import type { T } from "@/i18n/t";
import { RADII, useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";
import { Icon, icons, type IconName } from "@/ui/icon";
import { pillOf } from "@/ui/pill";
import { Text } from "@/ui/text";

/**
 * Reservas' pills in the design's shape (spec 069, R14.1; design §5.2): 24 pt,
 * a capsule, an icon in its tone and the words — the state is never only a
 * colour (R3.6). The words and tones are the shared `pillOf`'s, so a state
 * reads the same in the list, the grid and the sheet; only the shape and the
 * icon are this area's (the shared `ui/pill.tsx` is not).
 */
const STATE_ICON: Record<ResState, IconName> = {
  pending: icons.clock,
  confirmed: icons.circleCheck,
  arrived: icons.walkIn,
  done: icons.checkmark,
  noshow: icons.calendarX,
  cancelled: icons.calendarX,
};

export function StatePill({ state, origin, mode, late, t, testID }: { state: ResState; origin: Origin; mode: Mode; late: number | null; t: T; testID?: string }) {
  const look = pillOf({ state, origin }, mode, late, t);
  return <ResPill label={look.label} icon={late !== null ? icons.clock : STATE_ICON[state]} bg={look.bg} fg={look.fg} dashed={look.border} testID={testID ?? `pill-${late !== null ? "late" : state}`} />;
}

export function ResPill({
  label,
  icon,
  bg,
  fg,
  dashed,
  testID,
}: {
  label: string;
  icon?: IconName;
  bg: keyof Palette;
  fg: keyof Palette;
  /** «Sin confirmar» also carries a dashed edge, as in spec 044. */
  dashed?: keyof Palette;
  testID?: string;
}) {
  const { colors } = useTheme();
  return (
    <View
      testID={testID}
      style={[
        styles.pill,
        { backgroundColor: colors[bg], borderColor: dashed ? colors[dashed] : "transparent", borderStyle: dashed ? "dashed" : "solid" },
      ]}
    >
      {icon ? <Icon name={icon} size={13} tone={fg} /> : null}
      <Text variant="caption" tone={fg} numberOfLines={1} style={styles.text}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    minHeight: 24,
    paddingHorizontal: 9,
    borderRadius: RADII.pill,
    borderWidth: 1,
    alignSelf: "flex-start",
    maxWidth: "100%",
  },
  text: { flexShrink: 1 },
});
