import { StyleSheet, View } from "react-native";

import { useT } from "@/i18n/t";
import { useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";
import { Icon, icons, type IconName } from "@/ui/icon";
import { Text } from "@/ui/text";

import { modeLine, type ModeKind } from "../model";

/**
 * Who answers now, in the design's pill (spec 069, R11.1, §6.2 of the
 * inventory): an icon and the words, never colour alone. Amber only for who
 * waits for a person (R1.2).
 */
const LOOK: Record<ModeKind, { icon: IconName; bg: keyof Palette | null; fg: keyof Palette; ring: boolean }> = {
  waiting: { icon: icons.hand, bg: "warningBg", fg: "warningText", ring: false },
  mine: { icon: icons.person, bg: null, fg: "foreground", ring: true },
  other: { icon: icons.person, bg: "infoBg", fg: "infoText", ring: false },
  agent: { icon: icons.bot, bg: "muted", fg: "mutedForeground", ring: false },
  paused: { icon: icons.clock, bg: "muted", fg: "mutedForeground", ring: false },
  resolved: { icon: icons.circleCheck, bg: "positiveBg", fg: "positiveText", ring: false },
};

type ModeSource = Parameters<typeof modeLine>[0];

export function ModePill({ d }: { d: ModeSource }) {
  const t = useT();
  const { colors, radius } = useTheme();
  const m = modeLine(d, t);
  const look = LOOK[m.kind];
  return (
    <View
      testID={`mode-${m.kind}`}
      style={[
        styles.pill,
        { borderRadius: radius.full, backgroundColor: look.bg ? colors[look.bg] : "transparent" },
        look.ring ? { borderWidth: 1, borderColor: colors.input } : null,
      ]}
    >
      <Icon name={look.icon} size={14} tone={look.fg} />
      {/* One line: on Android a wrapping caption in a pill sized to its content can lose its last word. */}
      <Text variant="caption" tone={look.fg} numberOfLines={1} style={styles.text}>
        {m.text}
      </Text>
    </View>
  );
}

/** The dot before the header's line: amber when it waits, green when you answer, mint while the agent does, grey when it no longer can. */
export const MODE_DOT: Record<ModeKind, keyof Palette | null> = {
  waiting: "warningText",
  mine: "primaryText",
  other: "infoText",
  agent: "highlight",
  paused: "mutedForeground",
  resolved: null,
};

const styles = StyleSheet.create({
  pill: { flexDirection: "row", alignItems: "center", gap: 5, minHeight: 24, maxWidth: "100%", paddingHorizontal: 9, paddingVertical: 2, alignSelf: "center" },
  text: { flexShrink: 1 },
});
