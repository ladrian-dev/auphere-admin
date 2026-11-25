import type { ImageSource } from "expo-image";
import { Stack } from "expo-router";
import { Platform, Pressable, StyleSheet, View } from "react-native";

import { useT } from "@/i18n/t";
import { useTheme } from "@/theme/theme";
import type { Action } from "@/ui/actions";
import { Avatar } from "@/ui/bits";
import { icons, type IconName } from "@/ui/icon";
import { Text } from "@/ui/text";

import { channelName, type KnownChannel, type ModeKind } from "../model";
import { MODE_DOT } from "./mode";

/**
 * The conversation's title in the bar: the contact and who answers, a button
 * to the contact. How far it grows with the phone's text size (spec 042,
 * R4.6, H24): iOS keeps inline titles at their size, as Apple's own do — the
 * bar cannot grow; Android scales app-bar titles in sp, and 1,3 is what the
 * 64 dp bar holds with its two lines.
 *
 * Spec 069 (R11.1, design §4.3): the contact's photo or initials with the
 * channel's mark, and a dot before who answers — amber while it waits, green
 * when you do, mint while the agent does. The words say it; the dot repeats it.
 */
export function ConversationTitle({
  name,
  line,
  hint,
  onPress,
  initials,
  photo = null,
  channel = null,
  mode,
}: {
  name: string;
  line: string;
  hint: string;
  onPress: () => void;
  initials?: string;
  photo?: ImageSource | null;
  channel?: KnownChannel | null;
  mode?: ModeKind;
}) {
  const t = useT();
  const { colors } = useTheme();
  const max = Platform.OS === "ios" ? 1 : 1.3;
  const dot = mode ? MODE_DOT[mode] : null;
  // The avatar is hidden from the screen reader, so the channel it marks is said in the label (R11.1).
  const spoken = channel ? `${name}. ${channelName(channel, t)}. ${line}` : `${name}. ${line}`;
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={spoken} accessibilityHint={hint} onPress={onPress} style={styles.title}>
      {initials !== undefined ? <Avatar initials={initials} size={32} photo={photo} channel={channel} /> : null}
      <View style={styles.titleText}>
        <Text variant="bodyStrong" numberOfLines={1} maxFontSizeMultiplier={max}>
          {name}
        </Text>
        <View style={styles.lineRow}>
          {dot ? <View testID="mode-dot" style={[styles.dot, { backgroundColor: colors[dot] }]} /> : null}
          <Text variant="caption" tone="mutedForeground" numberOfLines={1} maxFontSizeMultiplier={max} style={styles.lineText}>
            {line}
          </Text>
        </View>
      </View>
    </Pressable>
  );
}

/** What a conversation's menu needs to know, and what each action does. */
export type ConversationMenu = {
  /** This person is answering: the first action gives the conversation back (031 R6.7). */
  mine: boolean;
  agentName: string | null;
  resolved: boolean;
  online: boolean;
  onGiveBack: () => void;
  onContact: () => void;
  onUnread: () => void;
  onResolve: () => void;
  onReopen: () => void;
  /** Spec 069 (R11.4, 056 R16): «Vaciar chat» and «Eliminar chat», each after its confirmation. */
  onClear?: () => void;
  onDelete?: () => void;
};

export type MenuItem = Action & { icon: IconName };

/**
 * The actions of a conversation, in order: give it back first — to the agent
 * by its name — then the contact, unread, and resolve or reopen; last, after
 * the rest (Apple's guides: what destroys goes at the end), «Vaciar chat» and
 * «Eliminar chat» (spec 069, R11.4). Offline, what writes is disabled rather
 * than hidden. One list for both platforms: the iOS bar menu below and
 * Android's action sheet.
 */
export function conversationMenu(m: ConversationMenu, t: ReturnType<typeof useT>): MenuItem[] {
  return [
    ...(m.mine
      ? [
          {
            icon: icons.giveBack,
            label: m.agentName ? t("app.inbox.giveBackTo", { name: m.agentName }) : t("inbox.composer.giveBack"),
            onPress: m.onGiveBack,
            disabled: !m.online,
          },
        ]
      : []),
    { icon: icons.person, label: t("inbox.action.panel"), onPress: m.onContact },
    { icon: icons.unread, label: t("inbox.action.unread"), onPress: m.onUnread, disabled: !m.online },
    m.resolved
      ? { icon: icons.reopen, label: t("inbox.action.reopen"), onPress: m.onReopen, disabled: !m.online }
      : { icon: icons.check, label: t("inbox.action.resolve"), onPress: m.onResolve, disabled: !m.online },
    ...(m.onClear ? [{ icon: icons.clear, label: t("inbox.action.clear"), onPress: m.onClear, disabled: !m.online, destructive: true }] : []),
    ...(m.onDelete ? [{ icon: icons.trash, label: t("inbox.action.delete"), onPress: m.onDelete, disabled: !m.online, destructive: true }] : []),
  ];
}

/**
 * The conversation's menu on iOS (spec 042, R1.4, R2.9): the system's own bar
 * menu, grouped in glass on iOS 26, with the one accent colour set explicitly
 * (the bar does not inherit `headerTintColor`). Android keeps the action
 * sheet of the 031 behind the header's button, so this renders nothing there.
 */
export function ConversationToolbar(m: ConversationMenu) {
  const t = useT();
  const { colors } = useTheme();
  if (Platform.OS !== "ios") return null;
  return (
    <Stack.Toolbar placement="right">
      <Stack.Toolbar.Menu icon={icons.more.ios} tintColor={colors.primaryText} accessibilityLabel={t("app.more")}>
        {conversationMenu(m, t).map((a) => (
          <Stack.Toolbar.MenuAction key={a.label} icon={a.icon.ios} disabled={a.disabled} destructive={a.destructive} onPress={a.onPress}>
            {a.label}
          </Stack.Toolbar.MenuAction>
        ))}
      </Stack.Toolbar.Menu>
    </Stack.Toolbar>
  );
}

const styles = StyleSheet.create({
  title: { minHeight: 44, flexDirection: "row", alignItems: "center", gap: 9, maxWidth: 260 },
  titleText: { flexShrink: 1, minWidth: 0, justifyContent: "center" },
  lineRow: { flexDirection: "row", alignItems: "center", gap: 5 },
  lineText: { flexShrink: 1 },
  dot: { width: 7, height: 7, borderRadius: 3.5 },
});
