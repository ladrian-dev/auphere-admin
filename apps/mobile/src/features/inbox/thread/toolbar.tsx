import { Stack } from "expo-router";
import { Platform } from "react-native";

import { useT } from "@/i18n/t";
import { useTheme } from "@/theme/theme";
import type { Action } from "@/ui/actions";
import { icons, type IconName } from "@/ui/icon";

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
};

export type MenuItem = Action & { icon: IconName };

/**
 * The actions of a conversation, in order: give it back first — to the agent
 * by its name — then the contact, unread, and resolve or reopen. Offline,
 * what writes is disabled rather than hidden. One list for both platforms:
 * the iOS bar menu below and Android's action sheet.
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
          <Stack.Toolbar.MenuAction key={a.label} icon={a.icon.ios} disabled={a.disabled} onPress={a.onPress}>
            {a.label}
          </Stack.Toolbar.MenuAction>
        ))}
      </Stack.Toolbar.Menu>
    </Stack.Toolbar>
  );
}
