import { StyleSheet, View, type TextInputProps } from "react-native";

import { Field } from "@/ui/field";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

/**
 * A field of Reservas' forms (spec 069, R15.1; design §11.7): the app's
 * `Field`, with its help under it and, once the person tried to save, what is
 * wrong in its place — an icon and the words, never colour alone (WCAG
 * 1.4.1, 3.3.1). The error replaces the help and is also the field's hint, so
 * the screen reader hears it on the field itself.
 */
export function FormField({ label, hint, error, ...input }: TextInputProps & { label: string; hint?: string; error?: string | null }) {
  return (
    <View style={styles.wrap}>
      <Field label={label} accessibilityHint={error ?? hint} {...input} />
      {error ? (
        <View style={styles.error} accessibilityRole="alert" accessible>
          <Icon name={icons.failed} size={16} tone="dangerText" />
          <Text variant="footnote" tone="dangerText" style={styles.flex}>
            {error}
          </Text>
        </View>
      ) : hint ? (
        <Text variant="footnote" tone="mutedForeground" importantForAccessibility="no" accessibilityElementsHidden>
          {hint}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 6 },
  error: { flexDirection: "row", alignItems: "flex-start", gap: 6 },
  flex: { flex: 1, minWidth: 0 },
});
