import * as DocumentPicker from "expo-document-picker";
import * as ImagePicker from "expo-image-picker";
import { router, Stack, useLocalSearchParams } from "expo-router";
import { useHeaderHeight, useIsFocused } from "expo-router/react-navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { FlatList, Pressable, StyleSheet, View } from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import Animated from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useQueryClient } from "@tanstack/react-query";

import { endpoints, type ThreadItem } from "@/api/endpoints";
import { useConversation, useReplies, useThread } from "@/api/hooks";
import { invalidateInbox } from "@/api/query";
import { checkAttachment, composerMode, attendsLine, dayLabel, withDaySeparators, type ThreadRow } from "@/features/inbox/model";
import { DayLine, EventLine, MessageBubble, PendingBubble, type Pending } from "@/features/inbox/thread/bubble";
import { Composer } from "@/features/inbox/thread/composer";
import { ControlCard } from "@/features/inbox/thread/control";
import { openMedia } from "@/features/inbox/thread/media";
import { useConversationActions } from "@/features/inbox/thread/use-conversation";
import { useLocale, useT } from "@/i18n/t";
import { useMotion } from "@/motion/use-motion";
import { setOpenConversation } from "@/push/handler";
import { useTheme } from "@/theme/theme";
import { useActions } from "@/ui/actions";
import { IconButton } from "@/ui/button";
import { icons } from "@/ui/icon";
import { useOnline } from "@/ui/online";
import { ErrorState, Skeleton } from "@/ui/states";
import { Text } from "@/ui/text";

type Row = ThreadRow | { kind: "pending"; key: string; p: Pending };

/**
 * One conversation (spec 031, R5.3–R6.8). The thread, newest at the bottom;
 * who answers under the name; and at the bottom, either why it waits and
 * «Tomar el control», or the box. It opens above the tabs, like any chat: the
 * box owns the bottom of the screen and the tab bar does not cover it. The orchestrated moment of the app (D24)
 * is here: taking control swaps the card for the box, confirms it with a
 * vibration and puts the cursor in the box.
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
  const focused = useIsFocused();
  const qc = useQueryClient();

  const detail = useConversation(id);
  const thread = useThread(id);
  const act = useConversationActions(id, t);
  const d = detail.data;
  const mode = d ? composerMode(d) : null;
  const replies = useReplies(mode?.kind === "mine");
  const [now] = useState(() => new Date());

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

  const menu = () => {
    if (!d || !mode) return;
    const resolved = d.state === "resolved";
    actions(d.contact.name, [
      // R6.7: first, give it back — to the agent by its name.
      ...(mode.kind === "mine"
        ? [
            {
              label: d.agent ? t("app.inbox.giveBackTo", { name: d.agent.name }) : t("inbox.composer.giveBack"),
              onPress: () => void act.giveBack(d.control_version),
              disabled: !online,
            },
          ]
        : []),
      { label: t("inbox.action.panel"), onPress: openContact },
      {
        label: t("inbox.action.unread"),
        disabled: !online,
        onPress: () =>
          void act.markUnread().then((ok) => {
            if (ok) router.back();
          }),
      },
      resolved
        ? { label: t("inbox.action.reopen"), onPress: () => void act.reopen(), disabled: !online }
        : { label: t("inbox.action.resolve"), onPress: () => void act.resolve(), disabled: !online },
    ]);
  };

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

  const header = (
    <Stack.Screen
      options={{
        headerTitle: () =>
          d ? (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel={`${d.contact.name}. ${attendsLine(d, t)}`}
              accessibilityHint={t("inbox.action.panel")}
              onPress={openContact}
              style={styles.title}
            >
              <Text variant="bodyStrong" numberOfLines={1}>
                {d.contact.name}
              </Text>
              <Text variant="caption" tone="mutedForeground" numberOfLines={1}>
                {attendsLine(d, t)}
              </Text>
            </Pressable>
          ) : null,
        headerRight: () => (d ? <IconButton icon={icons.more} label={t("app.more")} onPress={menu} /> : null),
      }}
    />
  );

  if (!d) {
    return (
      <View style={[styles.fill, { backgroundColor: colors.background }]}>
        {header}
        {detail.isError ? (
          <ErrorState body={t("inbox.thread.error")} onRetry={() => void detail.refetch()} />
        ) : (
          <View style={styles.pad}>
            <Skeleton rows={4} label={t("inbox.thread.loading")} />
          </View>
        )}
      </View>
    );
  }

  return (
    <KeyboardAvoidingView behavior="padding" keyboardVerticalOffset={headerHeight} style={[styles.fill, { backgroundColor: colors.background }]}>
      {header}
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
      <FlatList<Row>
        inverted
        style={styles.fill}
        data={rows}
        keyExtractor={(r) => r.key}
        accessibilityLabel={t("inbox.thread")}
        keyboardDismissMode="interactive"
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={styles.list}
        renderItem={({ item: row }) =>
          row.kind === "day" ? (
            <DayLine label={dayLabel(row.at, now, locale, t)} />
          ) : row.kind === "pending" ? (
            <PendingBubble p={row.p} t={t} onRetry={act.retry} onDismiss={act.dismiss} />
          ) : row.item.type === "event" ? (
            <EventLine item={row.item as ThreadItem} t={t} />
          ) : (
            <MessageBubble item={row.item as ThreadItem} t={t} locale={locale} onOpen={open} />
          )
        }
        onEndReachedThreshold={0.3}
        onEndReached={() => {
          if (thread.hasNextPage && !thread.isFetchingNextPage) void thread.fetchNextPage();
        }}
        ListFooterComponent={
          thread.isFetchingNextPage || thread.isPending ? (
            <View style={styles.pad}>
              <Skeleton rows={2} label={t("inbox.thread.loading")} />
            </View>
          ) : undefined
        }
      />
      <View style={[styles.bottom, { paddingBottom: Math.max(insets.bottom, 8), borderTopColor: colors.border }]}>
        {mode?.kind === "mine" ? (
          <Animated.View key="mine" entering={motion.enter} exiting={motion.exit} layout={motion.layout}>
            <Composer
              mode={mode}
              online={online}
              focusSignal={act.tookOver}
              replies={replies.data ?? null}
              t={t}
              onSend={(text) => void act.send(text)}
              onAttach={attach}
              onReplies={(insert) =>
                actions(
                  t("inbox.replies"),
                  (replies.data ?? []).map((r) => ({ label: r.title, onPress: () => insert(r.body) })),
                )
              }
            />
          </Animated.View>
        ) : mode ? (
          <Animated.View key={`control-${mode.kind}`} entering={motion.enter} exiting={motion.exit} layout={motion.layout}>
            <ControlCard
              mode={mode}
              busy={act.busy}
              online={online}
              t={t}
              onTakeOver={() => void act.takeOver(d.control_version)}
              onGiveBack={() => void act.giveBack(d.control_version)}
              onReopen={() => void act.reopen()}
            />
          </Animated.View>
        ) : null}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  pad: { padding: 16 },
  list: { paddingVertical: 8 },
  title: { minHeight: 44, justifyContent: "center", maxWidth: 240 },
  notice: { paddingHorizontal: 16, paddingVertical: 10 },
  bottom: { paddingHorizontal: 12, paddingTop: 8, borderTopWidth: StyleSheet.hairlineWidth },
});
