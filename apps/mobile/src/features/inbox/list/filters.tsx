import { Pressable, ScrollView, StyleSheet } from "react-native";

import type { Counts, InboxFilter } from "@/api/endpoints";
import type { T } from "@/i18n/t";
import { haptics } from "@/motion/haptics";
import { useTheme } from "@/theme/theme";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

const FILTERS: InboxFilter[] = ["all", "unread", "waiting", "resolved"];

/**
 * The list's filters (R5.2) as a row of chips, one chosen at a time, and the
 * agent's when the client has more than one. Each chip is a real target
 * (48 pt with its slop) and says whether it is chosen.
 */
export function Filters({
  filter,
  onFilter,
  counts,
  agentLabel,
  onAgent,
  t,
}: {
  filter: InboxFilter;
  onFilter: (f: InboxFilter) => void;
  counts: Counts | null;
  agentLabel: string | null;
  onAgent: (() => void) | null;
  t: T;
}) {
  const label = (f: InboxFilter) =>
    f === "waiting" && counts && counts.waiting > 0
      ? t("inbox.filter.waiting.count", { count: counts.waiting })
      : t(`inbox.filter.${f}` as const);
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.row}
      accessibilityRole="radiogroup"
      accessibilityLabel={t("inbox.filters")}
    >
      {FILTERS.map((f) => (
        <Chip
          key={f}
          label={label(f)}
          on={filter === f}
          onPress={() => {
            if (filter !== f) haptics.light();
            onFilter(f);
          }}
        />
      ))}
      {onAgent && agentLabel ? <Chip label={agentLabel} on={false} onPress={onAgent} icon /> : null}
    </ScrollView>
  );
}

function Chip({ label, on, onPress, icon = false }: { label: string; on: boolean; onPress: () => void; icon?: boolean }) {
  const { colors, radius } = useTheme();
  return (
    <Pressable
      accessibilityRole={icon ? "button" : "radio"}
      accessibilityState={icon ? undefined : { checked: on }}
      onPress={onPress}
      hitSlop={{ top: 6, bottom: 6 }}
      style={({ pressed }) => [
        styles.chip,
        {
          borderRadius: radius.full,
          backgroundColor: on ? colors.primary : colors.card,
          borderColor: on ? colors.primary : colors.border,
          opacity: pressed ? 0.7 : 1,
        },
      ]}
    >
      {icon ? <Icon name={icons.bot} size={14} tone="foreground" /> : null}
      <Text variant="subhead" tone={on ? "primaryForeground" : "foreground"}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { gap: 8, paddingHorizontal: 16, paddingVertical: 8 },
  chip: { minHeight: 36, paddingHorizontal: 14, borderWidth: 1, flexDirection: "row", alignItems: "center", gap: 6 },
});
