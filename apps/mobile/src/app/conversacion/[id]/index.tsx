import * as DocumentPicker from "expo-document-picker";
import * as ImagePicker from "expo-image-picker";
import { router, Stack, useLocalSearchParams } from "expo-router";
import { useHeaderHeight, useIsFocused } from "expo-router/react-navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Alert, FlatList, Keyboard, LayoutAnimation, Platform, StyleSheet, View } from "react-native";
import { KeyboardStickyView } from "react-native-keyboard-controller";
import Animated from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQueryClient } from "@tanstack/react-query";

import { endpoints, type ThreadItem } from "@/api/endpoints";
import { useConversation, useReplies, useThread } from "@/api/hooks";
import { invalidateInbox } from "@/api/query";
import { checkAttachment, composerMode, attendsLine, dayLabel, withDaySeparators, type ThreadRow } from "@/features/inbox/model";
import { DayLine, EventLine, MessageBubble, PendingBubble, type Pending } from "@/features/inbox/thread/bubble";
import { ThreadFoot } from "@/features/inbox/thread/foot";
import { openMedia } from "@/features/inbox/thread/media";
import { ConversationTitle, ConversationToolbar, conversationMenu, type ConversationMenu } from "@/features/inbox/thread/toolbar";
import { useConversationActions } from "@/features/inbox/thread/use-conversation";
import { useLocale, useT } from "@/i18n/t";
import { durations } from "@/motion/durations";
import { useMotion } from "@/motion/use-motion";
import { setOpenConversation } from "@/push/handler";
import { glassAvailable } from "@/theme/glass";
import { useTheme } from "@/theme/theme";
import { useActions } from "@/ui/actions";
import { ContentScroll } from "@/ui/content-scroll";
import { IconButton } from "@/ui/button";
import { icons } from "@/ui/icon";
import { useOnline } from "@/ui/online";
import { ErrorState, Skeleton } from "@/ui/states";
import { Text } from "@/ui/text";

type Row = ThreadRow | { kind: "pending"; key: string; p: Pending };

/**
 * One conversation (spec 031, R5.3–R6.8; spec 042, R2). The thread, newest at
 * the bottom, scrolling under the system's header; who answers under the
 * name; and at the foot, one surface floating over the thread — why it waits
 * and «Tomar el control», or the box. It opens above the tabs, like any chat.
 * The orchestrated moment of the app (D24) is here: taking control changes
 * what the surface holds, the surface animates its height, a vibration
 * confirms it and the cursor lands in the box.
 *
 * The list is the keyboard library's chat scroll view: the foot's measured
 * height is the list's extra bottom padding, so the last message always
 * clears it, and the box rides the keyboard up (D4).
 */
export default function ConversationScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const t = useT();
  const locale = useLocale();
  const online = useOnline();
  const motion = useMotion();
  const actions = useActions();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const headerHeight = useHeaderHeight();
  // With Liquid Glass the header is transparent and the screen runs under it; elsewhere it starts below it.
  const underHeader = glassAvailable() ? headerHeight : 0;
  const focused = useIsFocused();
  const qc = useQueryClient();

  const detail = useConversation(id);
  const thread = useThread(id);
  const act = useConversationActions(id, t);
  const d = detail.data;
  const mode = d ? composerMode(d) : null;
  const replies = useReplies(mode?.kind === "mine");
  const [now] = useState(() => new Date());

  // A spacer at the list's visual bottom keeps the last message clear of the foot (R2.2): the foot's
  // clearance plus what the keyboard lifts it. Both live in React state and move with the platform's own
  // LayoutAnimation — never a Reanimated layout prop inside the list: on iOS 26 that leaves every row
  // drawn at a fraction of its opacity (H20), with the chat scroll view's inset as much as with a spacer.
  const [clearance, setClearance] = useState(0);
  const [keyboard, setKeyboard] = useState(0);
  const onClearance = useCallback(
    (px: number) => {
      setClearance((cur) => {
        if (cur !== 0 && cur !== px && !motion.reduced) LayoutAnimation.configureNext(LayoutAnimation.create(durations.state, "easeInEaseOut", "opacity"));
        return px;
      });
    },
    [motion.reduced],
  );
  useEffect(() => {
    const curve = (ms: number) => LayoutAnimation.create(ms || durations.state, "keyboard", "opacity");
    const show = Keyboard.addListener(Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow", (e) => {
      if (Platform.OS === "ios" && !motion.reduced) LayoutAnimation.configureNext(curve(e.duration));
      setKeyboard(e.endCoordinates.height);
    });
    const hide = Keyboard.addListener(Platform.OS === "ios" ? "keyboardWillHide" : "keyboardDidHide", (e) => {
      if (Platform.OS === "ios" && !motion.reduced) LayoutAnimation.configureNext(curve(e.duration));
      setKeyboard(0);
    });
    return () => {
      show.remove();
      hide.remove();
    };
  }, [motion.reduced]);
  const spacer = clearance + Math.max(0, keyboard - insets.bottom);

  // R8.7: this conversation's notices stay quiet while it is on screen.
  useEffect(() => {
    if (!focused) return;
    setOpenConversation(id);
    return () => setOpenConversation(null);
  }, [focused, id]);

  // Read on open, and again whenever the contact writes while it is on screen.
  const items = useMemo(() => (thread.data ? [...thread.data.pages].reverse().flatMap((p) => p.items) : []), [thread.data]);
  const lastInbound = useMemo(() => [...items].reverse().find((i) => i.type === "message" && i.direction === "inbound")?.id ?? null, [items]);
  const readUpTo = useRef<string | null>(null);
  useEffect(() => {
    if (!focused || !thread.data || readUpTo.current === (lastInbound ?? "none")) return;
    readUpTo.current = lastInbound ?? "none";
    void endpoints
      .markRead(id)
      .then(() => invalidateInbox(qc))
      .catch(() => undefined);
  }, [focused, thread.data, lastInbound, id, qc]);

  const rows: Row[] = useMemo(() => {
    const asc: Row[] = [...withDaySeparators(items), ...act.pending.map((p) => ({ kind: "pending" as const, key: p.key, p }))];
    return asc.reverse();
  }, [items, act.pending]);

  const openContact = () => router.push(`/conversacion/${id}/contacto`);
  // Spec 047 (T176, 52.1): «Corregir esta respuesta» on an answer of the agent, as a sheet over the thread.
  const correct = useCallback((messageId: string) => router.push(`/conversacion/${id}/corregir?message=${encodeURIComponent(messageId)}`), [id]);

  // One menu, two shapes (R1.4, R2.9): the bar's own menu on iOS, the action sheet behind a button on Android.
  const menu: ConversationMenu | null =
    d && mode
      ? {
          mine: mode.kind === "mine",
          agentName: d.agent?.name ?? null,
          resolved: d.state === "resolved",
          online,
          onGiveBack: () => void act.giveBack(d.control_version),
          onContact: openContact,
          onUnread: () =>
            void act.markUnread().then((ok) => {
              if (ok) router.back();
            }),
          onResolve: () => void act.resolve(),
          onReopen: () => void act.reopen(),
        }
      : null;
  const openMenu = () => {
    if (d && menu) actions(d.contact.name, conversationMenu(menu, t));
  };
  const toolbar = menu ? <ConversationToolbar {...menu} /> : null;

  const pick = async (source: "camera" | "library" | "document") => {
    let asset: { uri: string; mimeType?: string | null; size?: number | null; name: string } | null = null;
    if (source === "document") {
      const r = await DocumentPicker.getDocumentAsync({ type: "application/pdf", copyToCacheDirectory: true });
      const a = r.canceled ? null : r.assets[0];
      if (a) asset = { uri: a.uri, mimeType: a.mimeType ?? "application/pdf", size: a.size ?? null, name: a.name };
    } else {
      if (source === "camera") {
        const perm = await ImagePicker.requestCameraPermissionsAsync();
        if (!perm.granted) return;
      }
      const options: ImagePicker.ImagePickerOptions = { mediaTypes: ["images"], quality: 0.8 };
      const r = source === "camera" ? await ImagePicker.launchCameraAsync(options) : await ImagePicker.launchImageLibraryAsync(options);
      const a = r.canceled ? null : r.assets[0];
      if (a) asset = { uri: a.uri, mimeType: a.mimeType ?? "image/jpeg", size: a.fileSize ?? null, name: a.fileName ?? t("inbox.media.image") };
    }
    if (!asset) return;
    const check = checkAttachment({ type: asset.mimeType, size: asset.size });
    if (!check.ok) {
      act.setNotice({
        text: check.reason === "type" ? t("inbox.composer.attach.type") : t("inbox.composer.attach.size", { mb: check.maxMb }),
        tone: "warning",
      });
      return;
    }
    void act.attach(asset.uri, t("inbox.composer.attach.sending", { name: asset.name }));
  };

  const attach = () =>
    actions(t("inbox.composer.attach"), [
      { label: t("app.inbox.attach.photo"), onPress: () => void pick("camera") },
      { label: t("app.inbox.attach.library"), onPress: () => void pick("library") },
      { label: t("app.inbox.attach.document"), onPress: () => void pick("document") },
    ]);

  const open = (messageId: string, mime: string | null) =>
    void openMedia(messageId, mime).then((ok) => {
      if (!ok) act.setNotice({ text: t("app.inbox.open.failed"), tone: "warning" });
    });

  // R2.4: the agent's reason, whole, when two lines were not enough.
  const readMore = () => {
    if (mode?.kind === "waiting" && mode.reason) Alert.alert(t("inbox.composer.waiting.title"), mode.reason);
  };

  const header = (
    <Stack.Screen
      options={{
        headerTitle: () =>
          d ? <ConversationTitle name={d.contact.name} line={attendsLine(d, t)} hint={t("inbox.action.panel")} onPress={openContact} /> : null,
        headerRight: Platform.OS === "android" && d ? () => <IconButton icon={icons.more} label={t("app.more")} onPress={openMenu} /> : undefined,
      }}
    />
  );

  if (!d) {
    return (
      <View style={[styles.fill, { backgroundColor: colors.background }]}>
        {header}
        {toolbar}
        {detail.isError ? (
          <ErrorState body={t("inbox.thread.error")} onRetry={() => void detail.refetch()} />
        ) : (
          <View style={[styles.pad, { paddingTop: underHeader + 16 }]}>
            <Skeleton rows={4} label={t("inbox.thread.loading")} />
          </View>
        )}
      </View>
    );
  }

  return (
    <View style={[styles.fill, { backgroundColor: colors.background }]}>
      {/* The thread hides the scroll-edge effects of iOS 26: on an inverted list the system draws its gradient over
          the whole thread (H20). With no soft edge, the rows start under the header's edge instead of running under
          its title — where the header is transparent; elsewhere the content already starts below it. */}
      <ContentScroll edges="hidden" style={{ marginTop: underHeader }}>
      <FlatList<Row>
        inverted
        style={styles.fill}
        data={rows}
        keyExtractor={(r) => r.key}
        accessibilityLabel={t("inbox.thread")}
        automaticallyAdjustContentInsets={false}
        contentInsetAdjustmentBehavior="never"
        keyboardDismissMode="interactive"
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={styles.list}
        ListHeaderComponent={
          // Inverted: the "header" is the visual bottom — the notice, then the spacer that clears the foot.
          <View>
            {act.notice ? (
              <Animated.View
                entering={motion.enter}
                exiting={motion.exit}
                accessible
                accessibilityRole="alert"
                accessibilityLiveRegion="polite"
                style={[styles.notice, { backgroundColor: act.notice.tone === "warning" ? colors.warningBg : colors.infoBg }]}
              >
                <Text variant="subhead" tone={act.notice.tone === "warning" ? "warningText" : "infoText"}>
                  {act.notice.text}
                </Text>
              </Animated.View>
            ) : null}
            <View testID="thread-spacer" style={{ height: spacer }} />
          </View>
        }
        renderItem={({ item: row }) =>
          row.kind === "day" ? (
            <DayLine label={dayLabel(row.at, now, locale, t)} />
          ) : row.kind === "pending" ? (
            <PendingBubble p={row.p} t={t} onRetry={act.retry} onDismiss={act.dismiss} />
          ) : row.item.type === "event" ? (
            <EventLine item={row.item as ThreadItem} t={t} />
          ) : (
            <MessageBubble item={row.item as ThreadItem} t={t} locale={locale} onOpen={open} onCorrect={correct} />
          )
        }
        onEndReachedThreshold={0.3}
        onEndReached={() => {
          if (thread.hasNextPage && !thread.isFetchingNextPage) void thread.fetchNextPage();
        }}
        ListFooterComponent={
          // Inverted: the "footer" is the visual top — the room the transparent header needs, then older pages loading.
          <View style={styles.top}>
            {thread.isFetchingNextPage || thread.isPending ? (
              <View style={styles.pad}>
                <Skeleton rows={2} label={t("inbox.thread.loading")} />
              </View>
            ) : null}
          </View>
        }
      />
      </ContentScroll>
      <KeyboardStickyView offset={{ closed: 0, opened: insets.bottom }} style={styles.foot}>
        {mode ? (
          <ThreadFoot
            mode={mode}
            busy={act.busy}
            online={online}
            t={t}
            replies={replies.data ?? null}
            focusSignal={act.tookOver}
            onTakeOver={() => void act.takeOver(d.control_version)}
            onGiveBack={() => void act.giveBack(d.control_version)}
            onReopen={() => void act.reopen()}
            onReadMore={readMore}
            onSend={(text) => void act.send(text)}
            onAttach={attach}
            onReplies={(insert) =>
              actions(
                t("inbox.replies"),
                (replies.data ?? []).map((r) => ({ label: r.title, onPress: () => insert(r.body) })),
              )
            }
            onClearance={onClearance}
            bottomInset={insets.bottom}
          />
        ) : null}
      </KeyboardStickyView>
      {header}
      {toolbar}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  pad: { padding: 16 },
  list: { paddingVertical: 8 },
  top: { paddingTop: 8 },
  notice: { marginHorizontal: 12, marginBottom: 8, paddingHorizontal: 16, paddingVertical: 10, borderRadius: 12 },
  foot: { position: "absolute", left: 0, right: 0, bottom: 0 },
});
