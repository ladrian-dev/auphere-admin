import { useState, type ComponentRef, type ReactNode, type Ref } from "react";
import { StyleSheet, TextInput, View, type TextInputProps } from "react-native";

import { RADII, TOUCH, useTheme } from "@/theme/theme";
import { type } from "@/theme/type";
import { Icon, icons, type IconName } from "@/ui/icon";
import { Text } from "@/ui/text";

/**
 * A field of the entry screens (spec 069, R5.4; design §3.1): the label above,
 * the icon of what goes in it, and — once the person has tried — what is wrong
 * with it, under it, in words and with an icon (never colour alone, R3.6).
 *
 * The label is the input's accessible name; the error is its hint, so the
 * screen reader says it with the field, and it is announced when it appears.
 * Focus is a 2 pt ring, an error a 2 pt border in the danger tone (R3.5). The
 * box grows with the text size: no fixed heights around text.
 *
 * `ui/field.tsx` has neither icon nor error; this stays in the entry area
 * until the shared field grows both.
 */
export function EntryField({
  label,
  icon,
  error,
  trailing,
  ref,
  style,
  onFocus,
  onBlur,
  ...input
}: TextInputProps & {
  label: string;
  icon: IconName;
  /** Shown only when set: the screen decides when the first attempt happened. */
  error?: string | null;
  trailing?: ReactNode;
  ref?: Ref<ComponentRef<typeof TextInput>>;
}) {
  const { colors } = useTheme();
  const [focused, setFocused] = useState(false);
  const wrong = !!error;
  const border = wrong ? colors.destructive : focused ? colors.ring : colors.input;
  const thick = wrong || focused;
  return (
    <View style={styles.wrap}>
      <Text variant="subhead" tone="foreground" importantForAccessibility="no" accessibilityElementsHidden>
        {label}
      </Text>
      <View
        style={[
          styles.box,
          {
            borderColor: border,
            borderWidth: thick ? 2 : 1,
            // Keep the content where it is when the border thickens.
            paddingLeft: thick ? 13 : 14,
            backgroundColor: wrong ? colors.dangerBg : colors.card,
          },
        ]}
      >
        <Icon name={icon} size={20} tone={wrong ? "destructive" : "mutedForeground"} />
        <TextInput
          ref={ref}
          accessibilityLabel={label}
          accessibilityHint={error ?? undefined}
          placeholderTextColor={colors.mutedForeground}
          selectionColor={colors.primaryText}
          style={[styles.input, type.body, { color: colors.foreground }, style]}
          onFocus={(e) => {
            setFocused(true);
            onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            onBlur?.(e);
          }}
          {...input}
        />
        {trailing}
      </View>
      {wrong ? (
        <View style={styles.error} accessibilityLiveRegion="polite" accessibilityRole="alert">
          <Icon name={icons.failed} size={16} tone="destructive" />
          <Text variant="footnote" tone="destructive" style={styles.errorText}>
            {error}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 6 },
  box: { flexDirection: "row", alignItems: "center", gap: 10, minHeight: TOUCH, borderRadius: RADII.md, borderCurve: "continuous", paddingRight: 4 },
  input: { flex: 1, minWidth: 0, paddingVertical: 12 },
  error: { flexDirection: "row", alignItems: "flex-start", gap: 6 },
  errorText: { flex: 1, minWidth: 0, fontWeight: "600" },
});
