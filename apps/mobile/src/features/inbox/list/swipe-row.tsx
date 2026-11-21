import { useRef, type ReactNode } from "react";
import { StyleSheet, View } from "react-native";
import ReanimatedSwipeable, { SwipeDirection, type SwipeableMethods } from "react-native-gesture-handler/ReanimatedSwipeable";

import { useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";
import { Icon, type IconName } from "@/ui/icon";
import { Text } from "@/ui/text";

/** How far a row travels before letting go does the action (the design's 84 pt). */
export const SWIPE_THRESHOLD = 84;
/** The width the action's ground opens to. */
const PANEL = 104;

export type SwipeAction = { label: string; icon: IconName; tone: "success" | "neutral"; run: () => void };

const TONE: Record<SwipeAction["tone"], { bg: keyof Palette; fg: keyof Palette }> = {
  success: { bg: "positiveBg", fg: "positiveText" },
  neutral: { bg: "selection", fg: "onSelection" },
};

/**
 * A row that does something when swiped (spec 069, R9.4, Historia 4): to the
 * left it resolves or reopens, to the right it marks read or unread. Past the
 * design's 84 pt, letting go does it and the row comes back; short of it, it
 * only comes back. The ground says what will happen in words and an icon,
 * never colour alone, and is hidden from the screen reader — the row offers the
 * same actions as accessibility actions (R3.4). Offline nothing is offered.
 *
 * The gesture is the library's (react-native-gesture-handler, MIT): it yields
 * to the list's vertical scroll and to the system's back swipe.
 */
export function SwipeRow({
  left,
  right,
  enabled,
  children,
  testID,
}: {
  /** Swiping to the left: resolve or reopen. */
  left: SwipeAction;
  /** Swiping to the right: read or unread. */
  right: SwipeAction;
  enabled: boolean;
  children: ReactNode;
  testID?: string;
}) {
  const ref = useRef<SwipeableMethods>(null);
  return (
    <ReanimatedSwipeable
      ref={ref}
      testID={testID}
      enabled={enabled}
      friction={1}
      leftThreshold={SWIPE_THRESHOLD}
      rightThreshold={SWIPE_THRESHOLD}
      overshootFriction={8}
      renderLeftActions={() => <Ground action={right} align="left" />}
      renderRightActions={() => <Ground action={left} align="right" />}
      onSwipeableOpen={(direction) => {
        // The library names the way the row moved: to the right shows the left ground (read), to the left the right one.
        (direction === SwipeDirection.LEFT ? left : right).run();
        ref.current?.close();
      }}
    >
      {children}
    </ReanimatedSwipeable>
  );
}

function Ground({ action, align }: { action: SwipeAction; align: "left" | "right" }) {
  const { colors } = useTheme();
  const tone = TONE[action.tone];
  return (
    <View
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
      style={[styles.ground, align === "right" ? styles.right : styles.left, { backgroundColor: colors[tone.bg] }]}
    >
      {align === "right" ? (
        <Text variant="subhead" tone={tone.fg}>
          {action.label}
        </Text>
      ) : null}
      <Icon name={action.icon} size={20} tone={tone.fg} />
      {align === "left" ? (
        <Text variant="subhead" tone={tone.fg}>
          {action.label}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  ground: { width: PANEL, flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 18 },
  left: { justifyContent: "flex-start" },
  right: { justifyContent: "flex-end" },
});
