import type { ImageSource } from "expo-image";
import { memo } from "react";
import { Pressable, StyleSheet, View, type AccessibilityActionEvent, type AccessibilityActionInfo } from "react-native";

import type { Conversation } from "@/api/endpoints";
import type { Locale, T } from "@/i18n/t";
import { useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";
import { Avatar } from "@/ui/bits";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import { channelName, channelOf, initialsOf, isWaitingRow, modeLine, previewOf, reasonText, rowTime, waitingReasonText } from "../model";

/**
 * One conversation in the list (spec 031 R5.2; spec 044 R10.1; spec 069
 * R9.1): the design's compact row — the photo or the initials with the
 * channel's mark, the name and the time, the state only when it asks for
 * something («Espera», «Tú», ✓), and the last line with who wrote it. Unread
 * is a dot in the highlight colour and the line in ink — and said, not only
 * shown. Pinned among the ones waiting, the agent's reason is the line and the
 * wait is said under it. The whole row is one button with one spoken
 * sentence; its swipe actions are also its accessibility actions (R3.4).
 */
export const ConversationRow = memo(function ConversationRow({
  c,
  now,
  t,
  locale,
  agentName,
  pinned = false,
  photo = null,
  accessibilityActions,
  onAccessibilityAction,
  onPress,
}: {
  c: Conversation;
  now: Date;
  t: T;
  locale: Locale;
  /** The agent's name, only when the client has more than one; `handled_by_agent` (spec 047) says it when the API has it. */
  agentName: string | null;
  /** Spec 044, R10.1: in the waiting group, the agent's reason is the preview and the line under it says how long. */
  pinned?: boolean;
  /** The contact's photo (Instagram, Messenger), with the phone's credential. */
  photo?: ImageSource | null;
  /** The same actions as the swipe (spec 069, R3.4): resolve or reopen, read or unread. */
  accessibilityActions?: AccessibilityActionInfo[];
  onAccessibilityAction?: (e: AccessibilityActionEvent) => void;
  onPress: (id: string) => void;
}) {
  const { colors } = useTheme();
  const time = c.last_message ? rowTime(c.last_message.at, now, locale, t) : "";
  // Spec 056 (7.1): the agent's reason in words — a code never reaches the screen.
  const preview = pinned && c.waiting?.reason ? reasonText(c.waiting.reason, t) : previewOf(c, t);
  const waiting = isWaitingRow(c);
  // Spec 047 (50.7): why it waits, from its code, and which agent takes it — while an agent does (not a person).
  const said = c.state === "waiting" ? waitingReasonText(c.waiting_reason, t) : null;
  // Pinned, the reason is already the preview: once is enough.
  const reason = said && said !== preview ? said : null;
  // Without the time from the API there is no time: never an invented wait (044 R10.2).
  const waited = pinned && c.waiting?.since ? waitedText(c.waiting.since, now, t) : null;
  // The agent answering is the normal case and says nothing (design §3.3) — unless there are several, or it waits.
  const handler =
    c.handled_by_agent && (waiting || (agentName !== null && c.state === "agent"))
      ? t("bandeja.handledBy", { agent: c.handled_by_agent.name })
      : c.state === "agent"
        ? agentName
        : null;
  const mode = modeLine(c, t);
  const stateSaid = mode.kind === "agent" ? null : mode.text;
  const channel = channelOf(c.channel.kind);
  const spoken = [c.contact.name, channelName(c.channel.kind, t), c.unread ? t("inbox.row.unread") : null, stateSaid, reason, waited, handler, preview, time]
    .filter((part): part is string => Boolean(part))
    // A part that already ends in «.» is not read with a second one.
    .map((part) => part.replace(/\.\s*$/, ""))
    .join(". ");
  const meta = reason || waited || handler;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={spoken}
      accessibilityActions={accessibilityActions}
      onAccessibilityAction={onAccessibilityAction}
      onPress={() => onPress(c.id)}
      android_ripple={{ color: colors.muted }}
      style={({ pressed }) => [styles.row, { backgroundColor: pressed ? colors.muted : colors.card }]}
      testID={`conversation-${c.id}`}
    >
      <Avatar initials={c.contact.initials || initialsOf(c.contact.name)} size={44} photo={photo} channel={channel} />
      <View style={styles.body}>
        <View style={styles.top}>
          <Text variant="bodyStrong" numberOfLines={1} style={styles.name}>
            {c.contact.name}
          </Text>
          <Text variant="caption" tone={c.unread ? "highlightInk" : "mutedForeground"} style={[styles.time, c.unread ? styles.timeUnread : null]}>
            {time}
          </Text>
        </View>
        <View style={styles.line}>
          <StateTag kind={mode.kind} label={mode.kind === "other" ? (c.assignee?.name ?? null) : null} t={t} />
          {preview ? (
            <Text variant="subhead" tone={c.unread ? "foreground" : "mutedForeground"} numberOfLines={1} style={styles.preview}>
              {preview}
            </Text>
          ) : (
            <View style={styles.preview} />
          )}
          {c.unread ? <View testID="unread-dot" style={[styles.dot, { backgroundColor: colors.highlight }]} /> : null}
        </View>
        {meta ? (
          <View style={styles.meta}>
            {/* Amber is only the «Espera» label and its hand (R1.2): the reason and the wait read in the quiet ink. */}
            {reason ? (
              <Text variant="caption" tone="mutedForeground">
                {reason}
              </Text>
            ) : null}
            {waited ? (
              <Text variant="caption" tone="mutedForeground">
                {waited}
              </Text>
            ) : null}
            {handler ? (
              <Text variant="caption" tone="mutedForeground">
                {handler}
              </Text>
            ) : null}
          </View>
        ) : null}
      </View>
    </Pressable>
  );
});

/** The state, only when it asks for something (design §3.3): amber «Espera», a ringed «Tú», a green ✓. */
function StateTag({ kind, label, t }: { kind: ReturnType<typeof modeLine>["kind"]; label: string | null; t: T }) {
  const { colors, radius } = useTheme();
  if (kind === "agent" || kind === "paused") return null;
  if (kind === "resolved") {
    return (
      <View testID="row-state-resolved">
        <Icon name={icons.circleCheck} size={14} tone="positiveText" />
      </View>
    );
  }
  const look: Record<"waiting" | "mine" | "other", { bg: keyof Palette | null; fg: keyof Palette; text: string }> = {
    waiting: { bg: "warningBg", fg: "warningText", text: t("v13.inbox.row.waits") },
    mine: { bg: null, fg: "foreground", text: t("v13.inbox.row.you") },
    other: { bg: "infoBg", fg: "infoText", text: label ?? t("inbox.who.someone") },
  };
  const l = look[kind];
  return (
    <View
      testID={`row-state-${kind}`}
      style={[
        styles.tag,
        { borderRadius: radius.full, backgroundColor: l.bg ? colors[l.bg] : "transparent" },
        l.bg ? null : { borderWidth: 1, borderColor: colors.input },
      ]}
    >
      {kind === "waiting" ? <Icon name={icons.hand} size={12} tone={l.fg} /> : null}
      <Text variant="caption" tone={l.fg} numberOfLines={1}>
        {l.text}
      </Text>
    </View>
  );
}

/** «Espera hace 12 min»: how long it has waited, in the console's words (`inbox.row.waiting.*`). */
export function waitedText(since: string, now: Date, t: T): string {
  const min = Math.floor((now.getTime() - Date.parse(since)) / 60_000);
  if (min < 1) return t("inbox.row.waiting.now");
  if (min < 60) return t("inbox.row.waiting.min", { n: min });
  if (min < 24 * 60) return t("inbox.row.waiting.h", { n: Math.floor(min / 60) });
  const d = Math.floor(min / (24 * 60));
  return d === 1 ? t("inbox.row.waiting.d.one") : t("inbox.row.waiting.d", { n: d });
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", gap: 12, paddingLeft: 12, paddingRight: 14, paddingVertical: 10, minHeight: 64 },
  body: { flex: 1, minWidth: 0, gap: 2 },
  top: { flexDirection: "row", alignItems: "baseline", gap: 8 },
  name: { flex: 1, minWidth: 0 },
  time: { fontVariant: ["tabular-nums"] },
  timeUnread: { fontWeight: "600" },
  line: { flexDirection: "row", alignItems: "center", gap: 6 },
  preview: { flex: 1, minWidth: 0 },
  tag: { flexDirection: "row", alignItems: "center", gap: 4, minHeight: 20, paddingHorizontal: 7, maxWidth: 140 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  meta: { flexDirection: "row", flexWrap: "wrap", columnGap: 8, rowGap: 2 },
});
