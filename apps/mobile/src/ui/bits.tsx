import { Pressable, StyleSheet, View } from "react-native";

import { TOUCH, useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";

import { Icon, icons, type IconName } from "./icon";
import { Text } from "./text";

/** A small label that says a state, in words (never colour alone, WCAG 1.4.1). */
export function Badge({ label, tone }: { label: string; tone: "danger" | "warning" | "positive" | "info" | "neutral" }) {
  const { colors, radius } = useTheme();
  const map: Record<typeof tone, [keyof Palette, keyof Palette]> = {
    danger: ["dangerBg", "dangerText"],
    warning: ["warningBg", "warningText"],
    positive: ["positiveBg", "positiveText"],
    info: ["infoBg", "infoText"],
    neutral: ["muted", "mutedForeground"],
  };
  const [bg, fg] = map[tone];
  return (
    <View style={[styles.badge, { backgroundColor: colors[bg], borderRadius: radius.sm }]}>
      <Text variant="caption" tone={fg}>
        {label}
      </Text>
    </View>
  );
}

/** Initials in a circle — a contact has no photo here. */
export function Avatar({ initials, size = 40 }: { initials: string; size?: number }) {
  const { colors } = useTheme();
  return (
    <View
      importantForAccessibility="no-hide-descendants"
      accessibilityElementsHidden
      style={[styles.avatar, { width: size, height: size, borderRadius: size / 2, backgroundColor: colors.accentSoft }]}
    >
      {/\p{L}/u.test(initials) ? (
        <Text variant="subhead" tone="accentDeep" maxFontSizeMultiplier={1.4}>
          {initials}
        </Text>
      ) : (
        // Known only by number: a person, not a dot that reads as an error.
        <View testID="avatar-person">
          <Icon name={icons.person} size={Math.round(size * 0.5)} tone="accentDeep" />
        </View>
      )}
    </View>
  );
}

/** A progress bar with its meaning in words for screen readers. */
export function Meter({ value, max, tone, label }: { value: number; max: number; tone: "positive" | "warning" | "danger"; label: string }) {
  const { colors } = useTheme();
  const pct = max > 0 ? Math.max(0, Math.min(1, value / max)) : 0;
  const fill: keyof Palette = tone === "positive" ? "positive" : tone === "warning" ? "warningSolid" : "danger";
  return (
    <View
      accessible
      accessibilityRole="progressbar"
      accessibilityLabel={label}
      accessibilityValue={{ min: 0, max, now: value }}
      style={[styles.track, { backgroundColor: colors.muted }]}
    >
      <View style={[styles.fill, { width: `${pct * 100}%`, backgroundColor: colors[fill] }]} />
    </View>
  );
}

/** A choice of a few, as a native-looking segmented control (radio group for screen readers). */
export function Segmented<T extends string | number>({
  options,
  value,
  onChange,
  label,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
}) {
  const { colors, radius } = useTheme();
  return (
    <View accessibilityRole="radiogroup" accessibilityLabel={label} style={[styles.segments, { backgroundColor: colors.muted, borderRadius: radius.md }]}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable
            key={String(o.value)}
            accessibilityRole="radio"
            accessibilityState={{ checked: on }}
            onPress={() => onChange(o.value)}
            style={[styles.segment, { borderRadius: radius.sm, backgroundColor: on ? colors.card : "transparent" }]}
          >
            {/* One line: with large text a word shrinks to fit its segment rather than break in two (spec 044). */}
            <Text variant="subhead" tone={on ? "foreground" : "mutedForeground"} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.6}>
              {o.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

/**
 * A tappable row of a settings group, 48 pt minimum (spec 042, R6, D12). Its
 * shape says what it does: `push` goes somewhere in the app (chevron),
 * `external` leaves it (the external-link icon, and the subtitle says where),
 * `action` does something here (no indicator). The press shows as a tint on
 * the row, never as a drop in opacity.
 */
export function RowButton({
  title,
  subtitle,
  icon,
  tone = "foreground",
  onPress,
  accessibilityHint,
  testID,
  ...rest
}: {
  title: string;
  icon?: IconName;
  tone?: keyof Palette;
  onPress: () => void;
  accessibilityHint?: string;
  testID?: string;
} & ({ kind?: "push" | "action"; subtitle?: string } | { kind: "external"; subtitle: string })) {
  const { colors } = useTheme();
  const kind = rest.kind ?? "push";
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={subtitle ? `${title}. ${subtitle}` : title}
      accessibilityHint={accessibilityHint}
      onPress={onPress}
      android_ripple={{ color: colors.muted }}
      style={({ pressed }) => [styles.rowButton, pressed ? { backgroundColor: colors.muted } : null]}
      testID={testID}
    >
      {icon ? <Icon name={icon} size={20} tone={tone} /> : null}
      <View style={styles.rowText}>
        <Text variant="body" tone={tone}>
          {title}
        </Text>
        {subtitle ? (
          <Text variant="footnote" tone="mutedForeground">
            {subtitle}
          </Text>
        ) : null}
      </View>
      {kind === "push" ? (
        <View testID="row-indicator-push">
          <Icon name={icons.chevron} size={14} tone="subtle" />
        </View>
      ) : kind === "external" ? (
        <View testID="row-indicator-external">
          <Icon name={icons.external} size={16} tone="subtle" />
        </View>
      ) : null}
    </Pressable>
  );
}

export function Divider() {
  const { colors } = useTheme();
  return <View style={{ height: StyleSheet.hairlineWidth, backgroundColor: colors.border }} />;
}

const styles = StyleSheet.create({
  badge: { paddingHorizontal: 8, paddingVertical: 2, alignSelf: "flex-start" },
  avatar: { alignItems: "center", justifyContent: "center" },
  track: { height: 6, borderRadius: 3, overflow: "hidden" },
  fill: { height: "100%", borderRadius: 3 },
  segments: { flexDirection: "row", padding: 2, gap: 2 },
  segment: { flex: 1, minHeight: 40, alignItems: "center", justifyContent: "center", paddingHorizontal: 8 },
  rowButton: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: TOUCH, paddingHorizontal: 16, paddingVertical: 12 },
  rowText: { flex: 1, minWidth: 0, gap: 2 },
});
