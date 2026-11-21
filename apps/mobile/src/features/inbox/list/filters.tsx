import { ScrollView, StyleSheet } from "react-native";

import type { Counts, InboxFilter } from "@/api/endpoints";
import type { MessageKey, T } from "@/i18n/t";
import { Chip } from "@/ui/chip";
import { icons } from "@/ui/icon";

const FILTERS: InboxFilter[] = ["all", "unread", "waiting", "resolved"];

/** The chips' words: the console's, except «Esperan a una persona», the design's (spec 069, R9.2). */
const LABEL: Record<InboxFilter, MessageKey> = {
  all: "inbox.filter.all",
  unread: "inbox.filter.unread",
  waiting: "v13.inbox.filter.waiting",
  resolved: "inbox.filter.resolved",
};

/**
 * The list's filters (spec 031 R5.2; spec 069 R9.2, R9.8) as a row of chips,
 * one chosen at a time with its drawn ✓ (micro 2). Only the counts the API
 * gives are said — unread and waiting — and never a loose zero. Then the
 * channel, when the client has more than one, and the agent, when it has
 * more than one: each a button that opens its choice. While searching the
 * state chips step aside (the search spans them all, R10.2); the channel and
 * the agent still apply, so they stay.
 */
export function Filters({
  filter,
  onFilter,
  counts,
  showStates = true,
  channelLabel,
  onChannel,
  agentLabel,
  onAgent,
  t,
}: {
  filter: InboxFilter;
  onFilter: (f: InboxFilter) => void;
  counts: Counts | null;
  showStates?: boolean;
  channelLabel?: string | null;
  onChannel?: (() => void) | null;
  agentLabel: string | null;
  onAgent: (() => void) | null;
  t: T;
}) {
  const count = (f: InboxFilter): number | undefined => {
    const n = f === "unread" ? counts?.unread : f === "waiting" ? counts?.waiting : undefined;
    return n && n > 0 ? n : undefined;
  };
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.row}
      accessibilityRole="radiogroup"
      accessibilityLabel={t("inbox.filters")}
      testID="inbox-filters"
    >
      {showStates
        ? FILTERS.map((f) => {
            const n = count(f);
            const label = t(LABEL[f]);
            return (
              <Chip
                key={f}
                label={label}
                count={n}
                accessibilityLabel={n !== undefined ? t("v13.inbox.chip.count", { label, n }) : label}
                on={filter === f}
                onPress={() => onFilter(f)}
                testID={`filter-${f}`}
              />
            );
          })
        : null}
      {onChannel && channelLabel ? (
        <Chip
          label={channelLabel}
          on={false}
          onPress={onChannel}
          icon={icons.message}
          accessibilityLabel={t("v13.inbox.channel.chip", { name: channelLabel })}
          testID="filter-channel"
        />
      ) : null}
      {onAgent && agentLabel ? <Chip label={agentLabel} on={false} onPress={onAgent} icon={icons.bot} /> : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  row: { gap: 8, paddingHorizontal: 16, paddingVertical: 8 },
});
