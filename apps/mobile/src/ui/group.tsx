import { Children, Fragment, type ReactNode } from "react";
import { Pressable, StyleSheet, useWindowDimensions, View } from "react-native";

import { CARD_RADIUS, TOUCH, useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";

import { Divider } from "./bits";
import { Icon, icons } from "./icon";
import { Text } from "./text";

/**
 * A grouped list (spec 042, R5.5, R6): figures and settings as rows of one
 * surface, the way the platform lays out settings-shaped content. A row's
 * shape says what it does — chevron to go somewhere in the app, the
 * external-link icon to leave it — and a row that leads nowhere has neither
 * and does not respond (R6.4: the absence is designed).
 */
export function Group({
  title,
  accessibilityLabel,
  testID,
  children,
}: {
  title?: string;
  accessibilityLabel?: string;
  testID?: string;
  children: ReactNode;
}) {
  const { colors } = useTheme();
  const items = Children.toArray(children).filter(Boolean);
  return (
    <View accessibilityLabel={accessibilityLabel} testID={testID} style={styles.group}>
      {title ? (
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header" style={styles.title}>
          {title}
        </Text>
      ) : null}
      <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border, borderRadius: CARD_RADIUS }]}>
        {items.map((child, i) => (
          <Fragment key={i}>
            {i > 0 ? <Divider /> : null}
            {child}
          </Fragment>
        ))}
      </View>
    </View>
  );
}

/** How a row looks is how it behaves: a row that responds has to say which kind it is. */
type Static = { kind?: "none"; onPress?: undefined };
type Push = { kind: "push"; onPress: () => void };
type External = { kind: "external"; onPress: () => void; hint: string };

export type RowProps = {
  label: string;
  value?: string;
  hint?: string;
  tone?: keyof Palette;
  valueTone?: keyof Palette;
  accessibilityHint?: string;
  testID?: string;
  /** Something of its own under the words: a meter, a chart. */
  children?: ReactNode;
} & (Static | Push | External);

/** Past this text size the label and the value stack: a long figure never splits a word (R4.7). */
const STACK_AT = 1.5;

export function Row({ label, value, hint, tone = "foreground", valueTone = "foreground", accessibilityHint, testID, children, ...rest }: RowProps) {
  const { colors } = useTheme();
  const stacked = useWindowDimensions().fontScale >= STACK_AT;
  const kind = rest.kind ?? "none";
  const body = (
    <>
      <View style={styles.text}>
        <View testID={testID ? `${testID}-body` : undefined} style={[styles.body, stacked ? styles.bodyStacked : null]}>
          <Text variant="body" tone={tone} style={styles.label}>
            {label}
          </Text>
          {value ? (
            <Text variant="bodyStrong" tone={valueTone} style={styles.value}>
              {value}
            </Text>
          ) : null}
        </View>
        {hint ? (
          <Text variant="footnote" tone="mutedForeground">
            {hint}
          </Text>
        ) : null}
        {children}
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
    </>
  );

  if (kind === "none") {
    const spoken = value ? `${label}: ${value}${hint ? `. ${hint}` : ""}` : hint ? `${label}. ${hint}` : label;
    return (
      <View accessible accessibilityLabel={spoken} testID={testID} style={styles.row}>
        {body}
      </View>
    );
  }
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={[label, value, hint].filter(Boolean).join(". ")}
      accessibilityHint={accessibilityHint}
      onPress={rest.onPress}
      android_ripple={{ color: colors.muted }}
      style={({ pressed }) => [styles.row, pressed ? { backgroundColor: colors.muted } : null]}
      testID={testID}
    >
      {body}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  group: { gap: 8 },
  title: { paddingHorizontal: 4 },
  card: { borderWidth: StyleSheet.hairlineWidth * 2, overflow: "hidden" },
  row: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: TOUCH, paddingHorizontal: 16, paddingVertical: 12 },
  text: { flex: 1, minWidth: 0, gap: 4 },
  body: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between", gap: 12 },
  bodyStacked: { flexDirection: "column", alignItems: "flex-start", gap: 2 },
  label: { flexShrink: 1, minWidth: 0 },
  value: { fontVariant: ["tabular-nums"], flexShrink: 0 },
});
