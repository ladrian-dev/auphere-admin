import { useState, type ComponentRef, type ReactNode, type Ref } from "react";
import { StyleSheet, TextInput, View, type TextInputProps } from "react-native";

import { TOUCH, useTheme } from "@/theme/theme";
import { type } from "@/theme/type";

import { Text } from "./text";

/**
 * A labelled text field. The label is visible above the box and is also the
 * field's accessible name; the box shows focus with the `ring` token, two
 * points wide (WCAG 2.4.7, 2.4.13). Text grows with the system's size (R14.3)
 * and the box grows with it: no fixed heights around text.
 *
 * `trailing` is an action inside the box (show the password, for instance).
 */
export function Field({
  label,
  trailing,
  ref,
  style,
  onFocus,
  onBlur,
  ...input
}: TextInputProps & { label: string; trailing?: ReactNode; ref?: Ref<ComponentRef<typeof TextInput>> }) {
  const { colors, radius } = useTheme();
  const [focused, setFocused] = useState(false);
  return (
    <View style={styles.wrap}>
      <Text variant="subhead" tone="foreground" importantForAccessibility="no" accessibilityElementsHidden>
        {label}
      </Text>
      <View
        style={[
          styles.box,
          {
            borderRadius: radius.md,
            borderColor: focused ? colors.ring : colors.input,
            borderWidth: focused ? 2 : 1,
            // Keep the text where it is when the border thickens.
            paddingHorizontal: focused ? 11 : 12,
            backgroundColor: colors.card,
          },
        ]}
      >
        <TextInput
          ref={ref}
          accessibilityLabel={label}
          placeholderTextColor={colors.subtle}
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
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 6 },
  box: { flexDirection: "row", alignItems: "center", minHeight: TOUCH },
  input: { flex: 1, minWidth: 0, paddingVertical: 10 },
});
