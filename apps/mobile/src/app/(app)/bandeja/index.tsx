import { router, Stack } from "expo-router";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FlatList, RefreshControl, StyleSheet, View, type AccessibilityActionEvent } from "react-native";
import Animated from "react-native-reanimated";
import type { SearchBarCommands } from "react-native-screens";

import type { Conversation, InboxFilter } from "@/api/endpoints";
import { useCounts, useMe } from "@/api/hooks";
import { useLiveStatus } from "@/api/sse";
import { credentialHeaders, type ChannelType } from "@/api/v13-bandeja";
import { avatarSource, useInboxList } from "@/api/v13-bandeja-hooks";
import { ConversationRow } from "@/features/inbox/list/conversation-row";
import { Filters } from "@/features/inbox/list/filters";
import { rowActionsOf, useRowActions, type RowAction } from "@/features/inbox/list/row-actions";
import { InboxSkeleton } from "@/features/inbox/list/skeleton";
import { SwipeRow, type SwipeAction } from "@/features/inbox/list/swipe-row";
import { channelName, channelOf, inboxEntries, resolvedEntries, type InboxEntry, type InboxSection } from "@/features/inbox/model";
import { SettingsToolbar } from "@/features/tab-stack";
import { useLocale, useT, type MessageKey, type T } from "@/i18n/t";
import { clock } from "@/lib/format";
import { usePullRefresh } from "@/lib/use-pull-refresh";
import { haptics } from "@/motion/haptics";
import { useArrival } from "@/motion/micro";
import { CARD_RADIUS, useTheme } from "@/theme/theme";
import { useActions } from "@/ui/actions";
import { Button } from "@/ui/button";
import { icons, type IconName } from "@/ui/icon";
import { useOnline } from "@/ui/online";
import { EmptyState, ErrorState, OfflineBanner, PartialNotice, ReconnectingIndicator } from "@/ui/states";
import { Text } from "@/ui/text";

/**
 * The Bandeja (spec 031 R5.1–R5.4; spec 044 R10; spec 069 R9, R10): the
 * client's conversations, who waits for a person first and apart, the rest
 * grouped by day in compact rows with their channel's mark. Filters with their
 * counts and the drawn ✓, a channel selector when there is more than one, the
 * agent's when there are several. The header's search finds by name, phone or
 * account and by what was said — the resolved ones too, in their own group —
 * within the chosen channel. A row swipes to resolve or reopen and to mark
 * read or unread, with «Deshacer»; a conversation that arrives drops into its
 * group (micro 3). Pages load as the list scrolls and pulling re-reads.
 */
const SEARCH_DEBOUNCE_MS = 250;

export default function Bandeja() {
  const t = useT();
  const locale = useLocale();
  const { colors } = useTheme();
  const online = useOnline();
  const live = useLiveStatus();
  const actions = useActions();
  const me = useMe();
  const runAction = useRowActions(t);
  const [filter, setFilter] = useState<InboxFilter>("all");
  const [channel, setChannel] = useState<ChannelType | null>(null);
  const [agent, setAgent] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const searchBar = useRef<SearchBarCommands>(null);
  const query = useDebounced(search.trim(), SEARCH_DEBOUNCE_MS);
  const searching = query !== "";

  const counts = useCounts(true);
  // Searching spans every state (R10.2): the API leaves the resolved out of all but «Resueltas», so it is two reads.
  const list = useInboxList(searching ? "all" : filter, query, agent, channel);
  const done = useInboxList("resolved", query, agent, channel, searching);
  const pull = usePullRefresh(() => Promise.all([list.refetch(), counts.refetch(), ...(searching ? [done.refetch()] : [])]));
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(id);
  }, []);

  const agents = useMemo(() => (me.data?.agents ?? []).map((a) => ({ id: a.id, name: a.name })), [me.data]);
  const agentNames = useMemo(() => (agents.length > 1 ? new Map(agents.map((a) => [a.id, a.name])) : null), [agents]);
  const items = useMemo(() => list.data?.pages.flatMap((p) => p.items) ?? [], [list.data]);
  const resolvedItems = useMemo(() => (searching ? (done.data?.pages.flatMap((p) => p.items) ?? []) : []), [done.data, searching]);
  const first = list.data?.pages[0];
  // The channels the client has, kept while a filtered page loads so the chip does not blink.
  const kinds = useStickyKinds(first?.channel_kinds);
  const filtered = filter !== "all" || searching || agent !== null || channel !== null;
  // Spec 056 (6.2): «Abiertas» empty with resolved ones. Old APIs do not send it: 0.
  const resolved = filtered ? 0 : (first?.resolved ?? 0);
  const entries = useMemo(
    () =>
      searching
        ? [...inboxEntries(items, now, { pinWaiting: false }), ...resolvedEntries(resolvedItems)]
        : inboxEntries(items, now, { pinWaiting: filter === "all" || filter === "unread" }),
    [searching, items, resolvedItems, now, filter],
  );
  const more = searching ? list.hasNextPage || done.hasNextPage : list.hasNextPage;
  const fetchingMore = list.isFetchingNextPage || done.isFetchingNextPage;
  const loadMore = useCallback(() => {
    if (list.hasNextPage && !list.isFetchingNextPage) void list.fetchNextPage();
    else if (searching && done.hasNextPage && !done.isFetchingNextPage) void done.fetchNextPage();
  }, [list, done, searching]);

  // Micro 3: a conversation that was not here before — not the first load, not a new page — drops in.
  const arrivals = useArrivals(`${filter}|${channel}|${agent}|${query}`, items, list.data?.pages.length ?? 0, list.data !== undefined);
  const arrival = useArrival();

  // One read of the phone's credential for every photo of the list (R9.1).
  const [headers, setHeaders] = useState<Record<string, string> | null>(null);
  const wantsPhotos = items.some((c) => c.contact.has_avatar) || resolvedItems.some((c) => c.contact.has_avatar);
  useEffect(() => {
    if (!wantsPhotos) return;
    let live = true;
    // Re-read on the minute's tick: a renewed token replaces the old one, and a photo asked with it would fail.
    // The rows only reload when the credential really changed.
    void credentialHeaders().then((h) => {
      if (live) setHeaders((cur) => (cur?.Authorization === h?.Authorization ? cur : h));
    });
    return () => {
      live = false;
    };
  }, [wantsPhotos, now]);

  const pickAgent = () =>
    actions(t("inbox.filter.agent"), [
      { label: t("inbox.filter.agent.all"), onPress: () => setAgent(null) },
      ...agents.map((a) => ({ label: a.name, onPress: () => setAgent(a.id) })),
    ]);
  const agentLabel = agent ? t("app.inbox.agentFilter.value", { name: agentNames?.get(agent) ?? "" }) : t("inbox.filter.agent.all");
  const chooseChannel = (k: ChannelType | null) => {
    if (k !== channel) haptics.select();
    setChannel(k);
  };
  const pickChannel = () =>
    actions(t("inbox.filter.channel"), [
      { label: t("inbox.filter.channel.all"), onPress: () => chooseChannel(null) },
      ...kinds.map((k) => ({ label: channelName(k, t), onPress: () => chooseChannel(k) })),
    ]);
  const showChannel = kinds.length > 1 || channel !== null;
  const clearSearch = () => {
    searchBar.current?.clearText();
    setSearch("");
  };

  const header = (
    <View>
      <Filters
        filter={filter}
        onFilter={setFilter}
        counts={counts.data ?? first?.counts ?? null}
        showStates={!searching}
        channelLabel={showChannel ? (channel ? channelName(channel, t) : t("inbox.filter.channel.all")) : null}
        onChannel={showChannel ? pickChannel : null}
        agentLabel={agents.length > 1 ? agentLabel : null}
        onAgent={agents.length > 1 ? pickAgent : null}
        t={t}
      />
      <View style={styles.status}>
        {!online && list.data ? <OfflineBanner since={clock(new Date(list.dataUpdatedAt), locale)} /> : null}
        {online && live === "reconnecting" ? <ReconnectingIndicator label={t("inbox.live.reconnecting")} /> : null}
        {online && list.data && (list.isRefetchError || (searching && done.isError)) ? <PartialNotice /> : null}
      </View>
    </View>
  );

  const loading = list.isPending || (searching && done.isPending);
  const empty = loading ? (
    <InboxSkeleton label={t("inbox.list.loading")} />
  ) : list.isError && !list.data ? (
    <ErrorState body={t("inbox.error")} onRetry={() => void list.refetch()} />
  ) : searching ? (
    <EmptyState
      icon={icons.search}
      title={t("v13.search.empty.title", { q: query })}
      body={channel ? `${t("v13.search.empty.body")} ${t("v13.search.empty.channel", { channel: channelName(channel, t) })}` : t("v13.search.empty.body")}
      action={channel ? { label: t("v13.search.empty.removeChannel"), onPress: () => setChannel(null) } : { label: t("v13.search.empty.clear"), onPress: clearSearch }}
    />
  ) : resolved > 0 ? (
    <EmptyState
      icon={icons.inbox}
      title={t("bandeja.open.empty.title")}
      body={resolved === 1 ? t("bandeja.open.empty.resolved.one") : t("bandeja.open.empty.resolved", { count: resolved })}
      action={{ label: t("bandeja.open.empty.action"), onPress: () => setFilter("resolved") }}
    />
  ) : agent !== null || channel !== null ? (
    <EmptyState
      icon={icons.inbox}
      title={t("inbox.empty.filtered")}
      action={{
        label: t("inbox.empty.clear"),
        onPress: () => {
          setFilter("all");
          setAgent(null);
          setChannel(null);
        },
      }}
    />
  ) : filter !== "all" ? (
    <FilterEmpty filter={filter} agent={agents.length === 1 ? (agents[0]?.name ?? null) : null} t={t} onAll={() => setFilter("all")} />
  ) : first?.has_any ? (
    <EmptyState icon={icons.inbox} title={t("inbox.empty.filtered")} action={{ label: t("inbox.empty.clear"), onPress: () => setFilter("all") }} />
  ) : (
    <EmptyState icon={icons.inbox} title={t("inbox.empty.title")} body={t("v13.inbox.empty.all.body")} />
  );

  const swipe = (c: Conversation) => {
    const next = rowActionsOf(c);
    const left: SwipeAction = {
      label: t(next.left === "resolve" ? "v13.inbox.swipe.resolve" : "v13.inbox.swipe.reopen"),
      icon: next.left === "resolve" ? icons.circleCheck : icons.reopen,
      tone: "success",
      run: () => void runAction(c, next.left),
    };
    const right: SwipeAction = {
      label: t(next.right === "read" ? "v13.inbox.swipe.read" : "v13.inbox.swipe.unread"),
      icon: next.right === "read" ? icons.show : icons.mail,
      tone: "neutral",
      run: () => void runAction(c, next.right),
    };
    return { next, left, right };
  };

  const renderItem = ({ item }: { item: InboxEntry }) => {
    if (item.kind === "header") return <GroupHeader section={item.section} count={item.count} exact={!more} t={t} />;
    const c = item.c;
    const { next, left, right } = swipe(c);
    const a11y = online
      ? [
          { name: next.left, label: t(ACTION_LABEL[next.left]) },
          { name: next.right, label: t(ACTION_LABEL[next.right]) },
        ]
      : undefined;
    const onA11y = (e: AccessibilityActionEvent) => {
      const name = e.nativeEvent.actionName as RowAction;
      if (name === next.left || name === next.right) void runAction(c, name);
    };
    const row = (
      <View style={[styles.card, { backgroundColor: colors.card }, item.first ? styles.cardTop : null, item.last ? styles.cardBottom : null]}>
        {!item.first ? <View style={[styles.separator, { backgroundColor: colors.border }]} /> : null}
        <SwipeRow left={left} right={right} enabled={online} testID={`swipe-${c.id}`}>
          <ConversationRow
            c={c}
            now={now}
            t={t}
            locale={locale}
            pinned={item.pinned}
            photo={c.contact.has_avatar && headers ? avatarSource(c.id, headers) : null}
            agentName={agentNames && c.agent ? (agentNames.get(c.agent.id) ?? c.agent.name) : null}
            accessibilityActions={a11y}
            onAccessibilityAction={onA11y}
            onPress={(id) => router.push(`/conversacion/${id}`)}
          />
        </SwipeRow>
      </View>
    );
    // Always the same wrapper, so a row never remounts; `entering` only plays when it mounts as an arrival.
    const arrived = arrivals.has(c.id);
    return (
      <Animated.View entering={arrived ? arrival.entering : undefined} testID={arrived ? `arrived-${c.id}` : undefined}>
        {row}
      </Animated.View>
    );
  };

  const footerText =
    agents.length === 1 && agents[0]
      ? t("v13.inbox.footer", { agent: agents[0].name })
      : agents.length > 1
        ? t("v13.inbox.footer.agents")
        : t("v13.inbox.footer.noAgent");

  return (
    <>
      <SettingsToolbar />
      <Stack.Screen
        options={{
          headerSearchBarOptions: {
            ref: searchBar,
            placeholder: t("v13.inbox.search.placeholder"),
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
        data={entries}
        keyExtractor={(e) => e.key}
        contentInsetAdjustmentBehavior="automatic"
        style={{ backgroundColor: colors.background }}
        contentContainerStyle={styles.content}
        keyboardDismissMode="on-drag"
        ListHeaderComponent={header}
        ListEmptyComponent={empty}
        renderItem={renderItem}
        onEndReachedThreshold={0.5}
        onEndReached={loadMore}
        ListFooterComponent={
          fetchingMore ? (
            <InboxSkeleton rows={1} label={t("inbox.list.loading")} />
          ) : more ? (
            <View style={styles.more}>
              <Button label={t("inbox.list.more")} variant="ghost" onPress={loadMore} />
            </View>
          ) : entries.length > 0 ? (
            // Spec 044 R10.3, spec 069 R9.7: what the Bandeja is, and what it is not — without naming a channel.
            <Text variant="footnote" tone="mutedForeground" style={styles.footer}>
              {footerText}
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

const ACTION_LABEL: Record<RowAction, MessageKey> = {
  resolve: "v13.inbox.swipe.resolve",
  reopen: "v13.inbox.swipe.reopen",
  read: "v13.inbox.action.read",
  unread: "inbox.action.unread",
};

const SECTION_LABEL: Record<Exclude<InboxSection, "waiting">, MessageKey> = {
  today: "v13.inbox.group.today",
  yesterday: "v13.inbox.group.yesterday",
  week: "v13.inbox.group.week",
  older: "v13.inbox.group.older",
  resolved: "inbox.filter.resolved",
};

/**
 * A group's heading (design §3.3): its name and, on the right, how many —
 * only when the whole list is loaded; with more pages to come a number would
 * not be true (R21). Who waits keeps 044's heading, with its count.
 */
function GroupHeader({ section, count, exact, t }: { section: InboxSection; count: number; exact: boolean; t: T }) {
  if (section === "waiting") {
    return (
      <Text variant="footnote" tone="mutedForeground" accessibilityRole="header" style={[styles.group, styles.groupText]}>
        {t("app.inbox.waitingGroup", { n: count })}
      </Text>
    );
  }
  const label = t(SECTION_LABEL[section]);
  return (
    <View style={styles.groupRow} accessible accessibilityRole="header" accessibilityLabel={exact ? `${label}, ${count}` : label}>
      <Text variant="footnote" tone="mutedForeground" style={styles.groupText}>
        {label}
      </Text>
      {exact ? (
        <Text variant="footnote" tone="mutedForeground" style={styles.groupCount}>
          {count}
        </Text>
      ) : null}
    </View>
  );
}

/** Each filter's own empty (design §3.8): what will show here and how it gets there — never a loose zero. */
function FilterEmpty({ filter, agent, t, onAll }: { filter: Exclude<InboxFilter, "all">; agent: string | null; t: T; onAll: () => void }) {
  const copy: Record<Exclude<InboxFilter, "all">, { icon: IconName; title: string; body: string }> = {
    waiting: {
      icon: icons.hand,
      title: t("v13.inbox.empty.waiting.title"),
      body: t("v13.inbox.empty.waiting.body", { agent: agent ?? t("v13.inbox.theAgent") }),
    },
    unread: { icon: icons.mailCheck, title: t("v13.inbox.empty.unread.title"), body: t("v13.inbox.empty.unread.body") },
    resolved: { icon: icons.circleCheck, title: t("v13.inbox.empty.resolved.title"), body: t("v13.inbox.empty.resolved.body") },
  };
  const c = copy[filter];
  return <EmptyState icon={c.icon} title={c.title} body={c.body} action={{ label: t("v13.inbox.empty.seeAll"), onPress: onAll }} />;
}

/** A value that settles a moment after the person stops typing (R10.1); clearing it is at once. */
function useDebounced(value: string, ms: number): string {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    // Cleared, it settles on the next tick too, so a new search never starts from an older one.
    const id = setTimeout(() => setSettled(value), value === "" ? 0 : ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return value === "" ? "" : settled;
}

/** The client's channels as the app knows them, kept from the last page that said them (no blink while a filter loads). */
function useStickyKinds(kinds: readonly string[] | undefined): ChannelType[] {
  const [kept, setKept] = useState<{ from: readonly string[] | undefined; kinds: ChannelType[] }>({ from: undefined, kinds: [] });
  if (kinds && kinds !== kept.from) setKept({ from: kinds, kinds: kinds.filter((k): k is ChannelType => channelOf(k) !== null) });
  return kinds && kinds !== kept.from ? kinds.filter((k): k is ChannelType => channelOf(k) !== null) : kept.kinds;
}

/**
 * The ids that arrived since the last render of the same list (micro 3): none
 * on the first load, none when the list changes, none when a page is added.
 * Kept as state adjusted while rendering (React's pattern for «what changed
 * since the last props»), never a ref read during render.
 */
type Arrivals = { key: string; items: readonly Conversation[]; pages: number; seen: ReadonlySet<string>; fresh: ReadonlySet<string> };
const NONE: ReadonlySet<string> = new Set();

function useArrivals(key: string, items: readonly Conversation[], pages: number, loaded: boolean): ReadonlySet<string> {
  const [mem, setMem] = useState<Arrivals | null>(null);
  if (loaded && (mem === null || mem.items !== items || mem.key !== key)) {
    const same = mem !== null && mem.key === key && pages <= mem.pages;
    const fresh = same ? new Set(items.filter((c) => !mem.seen.has(c.id)).map((c) => c.id)) : new Set<string>();
    const seen = new Set([...(same ? mem.seen : []), ...items.map((c) => c.id)]);
    setMem({ key, items, pages, seen, fresh });
    return fresh;
  }
  return mem?.fresh ?? NONE;
}

const styles = StyleSheet.create({
  content: { paddingBottom: 24 },
  status: { paddingHorizontal: 16, gap: 8 },
  more: { alignItems: "center", paddingVertical: 8 },
  group: { paddingHorizontal: 20, paddingTop: 16, paddingBottom: 6 },
  groupRow: { flexDirection: "row", alignItems: "baseline", paddingHorizontal: 20, paddingTop: 16, paddingBottom: 6 },
  groupText: { flex: 1, fontWeight: "600" },
  groupCount: { fontVariant: ["tabular-nums"] },
  card: { marginHorizontal: 16, overflow: "hidden" },
  cardTop: { borderTopLeftRadius: CARD_RADIUS, borderTopRightRadius: CARD_RADIUS },
  cardBottom: { borderBottomLeftRadius: CARD_RADIUS, borderBottomRightRadius: CARD_RADIUS },
  separator: { position: "absolute", top: 0, left: 68, right: 0, height: StyleSheet.hairlineWidth, zIndex: 1 },
  footer: { paddingHorizontal: 20, paddingVertical: 20, textAlign: "center" },
});
