import { router, Stack } from "expo-router";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, View } from "react-native";

import type { InboxFilter } from "@/api/endpoints";
import { useConversations, useCounts, useMe } from "@/api/hooks";
import { useLiveStatus } from "@/api/sse";
import { ConversationRow } from "@/features/inbox/list/conversation-row";
import { Filters } from "@/features/inbox/list/filters";
import { SettingsToolbar } from "@/features/tab-stack";
import { useLocale, useT } from "@/i18n/t";
import { clock } from "@/lib/format";
import { usePullRefresh } from "@/lib/use-pull-refresh";
import { useTheme } from "@/theme/theme";
import { useActions } from "@/ui/actions";
import { Divider } from "@/ui/bits";
import { icons } from "@/ui/icon";
import { useOnline } from "@/ui/online";
import { EmptyState, ErrorState, OfflineBanner, ReconnectingIndicator, Skeleton } from "@/ui/states";
import { Button } from "@/ui/button";
import { Text } from "@/ui/text";

/**
 * The Bandeja (spec 031, R5.1–R5.4; spec 044, R10): the client's conversations, filtered,
 * searchable by name or number from the native search bar, live while the
 * app is in front. An empty inbox and an empty filter are different things,
 * and say so.
 */
export default function Bandeja() {
  const t = useT();
  const locale = useLocale();
  const { colors } = useTheme();
  const online = useOnline();
  const live = useLiveStatus();
  const actions = useActions();
  const me = useMe();
  const [filter, setFilter] = useState<InboxFilter>("all");
  const [search, setSearch] = useState("");
  const query = useDeferredValue(search.trim());
  const [agent, setAgent] = useState<string | null>(null);
  const counts = useCounts(true);
  const list = useConversations(filter, query, agent);
  const pull = usePullRefresh(() => Promise.all([list.refetch(), counts.refetch()]));
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);

  const agents = useMemo(() => (me.data?.agents ?? []).map((a) => ({ id: a.id, name: a.name })), [me.data]);
  const agentNames = useMemo(() => (agents.length > 1 ? new Map(agents.map((a) => [a.id, a.name])) : null), [agents]);
  const items = useMemo(() => list.data?.pages.flatMap((p) => p.items) ?? [], [list.data]);
  const first = list.data?.pages[0];
  const filtered = filter !== "all" || query !== "" || agent !== null;
  // Spec 044, R10.1: with «Todas» and no search, the ones waiting for a person go first, apart.
  const isWaiting = (c: (typeof items)[number]) => c.state === "waiting" && !c.assignee;
  const pinned = filtered ? [] : items.filter(isWaiting);
  const rest = filtered ? items : items.filter((c) => !isWaiting(c));

  const pickAgent = () =>
    actions(t("inbox.filter.agent"), [
      { label: t("inbox.filter.agent.all"), onPress: () => setAgent(null) },
      ...agents.map((a) => ({ label: a.name, onPress: () => setAgent(a.id) })),
    ]);
  const agentLabel = agent ? t("app.inbox.agentFilter.value", { name: agentNames?.get(agent) ?? "" }) : t("inbox.filter.agent.all");

  const header = (
    <View>
      <Filters
        filter={filter}
        onFilter={setFilter}
        counts={counts.data ?? first?.counts ?? null}
        agentLabel={agents.length > 1 ? agentLabel : null}
        onAgent={agents.length > 1 ? pickAgent : null}
        t={t}
      />
      <View style={styles.status}>
        {!online && list.data ? <OfflineBanner since={clock(new Date(list.dataUpdatedAt), locale)} /> : null}
        {online && live === "reconnecting" ? <ReconnectingIndicator label={t("inbox.live.reconnecting")} /> : null}
      </View>
      {pinned.length > 0 ? (
        <View>
          <Text variant="subhead" tone="dangerText" accessibilityRole="header" style={styles.section}>
            {t("app.inbox.waitingGroup", { n: pinned.length })}
          </Text>
          {pinned.map((c, i) => (
            <View key={c.id}>
              {i > 0 ? <Divider /> : null}
              <ConversationRow
                c={c}
                now={now}
                t={t}
                locale={locale}
                pinned
                agentName={agentNames && c.agent ? (agentNames.get(c.agent.id) ?? c.agent.name) : null}
                onPress={(id) => router.push(`/conversacion/${id}`)}
              />
            </View>
          ))}
          {rest.length > 0 ? (
            <Text variant="subhead" tone="mutedForeground" accessibilityRole="header" style={styles.section}>
              {t("app.inbox.others")}
            </Text>
          ) : null}
        </View>
      ) : null}
    </View>
  );

  const empty = list.isPending ? (
    <View style={styles.pad}>
      <Skeleton rows={5} label={t("inbox.list.loading")} />
    </View>
  ) : list.isError && !list.data ? (
    <ErrorState body={t("inbox.error")} onRetry={() => void list.refetch()} />
  ) : filtered || first?.has_any ? (
    <EmptyState
      icon={icons.inbox}
      title={t("inbox.empty.filtered")}
      action={{
        label: t("inbox.empty.clear"),
        onPress: () => {
          setFilter("all");
          setSearch("");
          setAgent(null);
        },
      }}
    />
  ) : (
    <EmptyState icon={icons.inbox} title={t("inbox.empty.title")} body={t("inbox.empty.body")} />
  );

  return (
    <>
      <SettingsToolbar />
      <Stack.Screen
        options={{
          headerSearchBarOptions: {
            placeholder: t("inbox.search.label"),
            onChangeText: (e) => setSearch(e.nativeEvent.text),
            onCancelButtonPress: () => setSearch(""),
            hideWhenScrolling: false,
            // Spec 042, D6 (spike S2, check 3): the system chooses where a section's search goes.
            placement: "automatic",
            tintColor: colors.primaryText,
            // Android draws the search icon, the text and the hint in its own greys unless told (H23): from the theme.
            headerIconColor: colors.primaryText,
            textColor: colors.foreground,
            hintTextColor: colors.mutedForeground,
          },
        }}
      />
      <FlatList
        testID="bandeja"
        accessibilityLabel={t("inbox.list")}
        data={rest}
        keyExtractor={(c) => c.id}
        contentInsetAdjustmentBehavior="automatic"
        style={{ backgroundColor: colors.background }}
        keyboardDismissMode="on-drag"
        ListHeaderComponent={header}
        ListEmptyComponent={pinned.length > 0 ? undefined : empty}
        ItemSeparatorComponent={Divider}
        renderItem={({ item }) => (
          <ConversationRow
            c={item}
            now={now}
            t={t}
            locale={locale}
            agentName={agentNames && item.agent ? (agentNames.get(item.agent.id) ?? item.agent.name) : null}
            onPress={(id) => router.push(`/conversacion/${id}`)}
          />
        )}
        onEndReachedThreshold={0.5}
        onEndReached={() => {
          if (list.hasNextPage && !list.isFetchingNextPage) void list.fetchNextPage();
        }}
        ListFooterComponent={
          list.isFetchingNextPage ? (
            <View style={styles.pad}>
              <Skeleton rows={1} label={t("inbox.list.loading")} />
            </View>
          ) : list.hasNextPage ? (
            <View style={styles.more}>
              <Button label={t("inbox.list.more")} variant="ghost" onPress={() => void list.fetchNextPage()} />
            </View>
          ) : items.length > 0 ? (
            // Spec 044, R10.3: what the Bandeja is, and what it is not.
            <Text variant="footnote" tone="mutedForeground" style={styles.footer}>
              {t("app.inbox.footer")}
            </Text>
          ) : undefined
        }
        refreshControl={
          <RefreshControl
            refreshing={pull.refreshing}
            onRefresh={pull.onRefresh}
            tintColor={colors.primaryText}
            colors={[colors.primaryDeep]}
          />
        }
      />
    </>
  );
}

const styles = StyleSheet.create({
  status: { paddingHorizontal: 16, gap: 8 },
  pad: { padding: 16 },
  more: { alignItems: "center", paddingVertical: 8 },
  section: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 4 },
  footer: { paddingHorizontal: 16, paddingVertical: 20, textAlign: "center" },
});
