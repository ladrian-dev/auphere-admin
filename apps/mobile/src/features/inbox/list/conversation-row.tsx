import { memo } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import type { Conversation } from "@/api/endpoints";
import type { Locale, T } from "@/i18n/t";
import { useTheme } from "@/theme/theme";
import { Avatar, Badge } from "@/ui/bits";
import { Text } from "@/ui/text";

import { badgeOf, initialsOf, listTime, previewOf } from "../model";

/**
 * One conversation in the list (R5.2): who, when, the last line and its state
 * in words. Unread is bold and a dot — and said, not only shown. The whole row
 * is one button with one spoken sentence.
 */
export const ConversationRow = memo(function ConversationRow({
  c,
  now,
  t,
  locale,
  agentName,
  onPress,
}: {
  c: Conversation;
  now: Date;
  t: T;
  locale: Locale;
  /** The agent's name, only when the client has more than one. */
  agentName: string | null;
  onPress: (id: string) => void;
}) {
  const { colors } = useTheme();
  const time = c.last_message ? listTime(c.last_message.at, now, locale, t) : "";
  const preview = previewOf(c, t);
  const badge = badgeOf(c, t);
  const spoken = [c.contact.name, c.unread ? t("inbox.row.unread") : null, badge?.label, agentName, preview, time]
    .filter(Boolean)
    .join(". ");
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={spoken}
      onPress={() => onPress(c.id)}
      style={({ pressed }) => [styles.row, { backgroundColor: pressed ? colors.muted : colors.background }]}
      testID={`conversation-${c.id}`}
    >
      <Avatar initials={c.contact.initials || initialsOf(c.contact.name)} size={44} />
      <View style={styles.body}>
        <View style={styles.top}>
          <Text variant={c.unread ? "bodyStrong" : "body"} numberOfLines={1} style={styles.name}>
            {c.contact.name}
          </Text>
          <Text variant="caption" tone={c.unread ? "primaryText" : "mutedForeground"}>
            {time}
          </Text>
        </View>
        {preview ? (
          <Text variant="callout" tone={c.unread ? "foreground" : "mutedForeground"} numberOfLines={2}>
            {preview}
          </Text>
        ) : null}
        {badge || agentName || c.unread ? (
          <View style={styles.meta}>
            {badge ? <Badge label={badge.label} tone={badge.tone} /> : null}
            {agentName ? <Badge label={agentName} tone="neutral" /> : null}
            <View style={styles.spacer} />
            {c.unread ? <View style={[styles.dot, { backgroundColor: colors.primary }]} /> : null}
          </View>
        ) : null}
      </View>
    </Pressable>
  );
});

const styles = StyleSheet.create({
  row: { flexDirection: "row", gap: 12, paddingHorizontal: 16, paddingVertical: 12, minHeight: 72 },
  body: { flex: 1, minWidth: 0, gap: 4 },
  top: { flexDirection: "row", alignItems: "baseline", gap: 8 },
  name: { flex: 1, minWidth: 0 },
  meta: { flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap" },
  spacer: { flex: 1 },
  dot: { width: 10, height: 10, borderRadius: 5 },
});
