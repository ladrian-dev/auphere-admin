import { SymbolView, type SymbolViewProps } from "expo-symbols";

import { useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";

/**
 * One icon, each platform's own set (R14.8): SF Symbols on iOS, Material
 * Symbols on Android. Decorative by default — the control that holds it
 * carries the accessible name.
 */
type NameObject = Exclude<SymbolViewProps["name"], string>;
/** Checked at compile time against each platform's set: a typo does not build. */
export type IconName = { ios: NonNullable<NameObject["ios"]>; android: NonNullable<NameObject["android"]> };

export function Icon({
  name,
  size = 20,
  tone = "foreground",
}: {
  name: IconName;
  size?: number;
  tone?: keyof Palette;
}) {
  const { colors } = useTheme();
  return (
    <SymbolView
      name={name}
      size={size}
      tintColor={colors[tone]}
      accessible={false}
      importantForAccessibility="no"
    />
  );
}

/** The app's icons, named once so both platforms stay in step. */
export const icons = {
  home: { ios: "house", android: "home" },
  inbox: { ios: "tray", android: "inbox" },
  usage: { ios: "chart.bar", android: "bar_chart" },
  settings: { ios: "person.crop.circle", android: "account_circle" },
  more: { ios: "ellipsis.circle", android: "more_vert" },
  giveBack: { ios: "arrow.uturn.backward", android: "undo" },
  unread: { ios: "envelope.badge", android: "mark_email_unread" },
  reopen: { ios: "arrow.counterclockwise", android: "restart_alt" },
  hand: { ios: "hand.raised", android: "back_hand" },
  wallet: { ios: "creditcard", android: "account_balance_wallet" },
  money: { ios: "dollarsign.circle", android: "paid" },
  chat: { ios: "bubble.left.and.bubble.right", android: "forum" },
  bot: { ios: "sparkles", android: "smart_toy" },
  warning: { ios: "exclamationmark.triangle", android: "warning" },
  check: { ios: "checkmark.circle", android: "check_circle" },
  offline: { ios: "wifi.slash", android: "wifi_off" },
  send: { ios: "arrow.up.circle.fill", android: "send" },
  arrowUp: { ios: "arrow.up", android: "arrow_upward" },
  attach: { ios: "paperclip", android: "attach_file" },
  replies: { ios: "text.bubble", android: "quickreply" },
  image: { ios: "photo", android: "image" },
  document: { ios: "doc.text", android: "description" },
  audio: { ios: "waveform", android: "graphic_eq" },
  video: { ios: "video", android: "videocam" },
  bell: { ios: "bell", android: "notifications" },
  external: { ios: "arrow.up.right.square", android: "open_in_new" },
  chevron: { ios: "chevron.right", android: "chevron_right" },
  close: { ios: "xmark", android: "close" },
  retry: { ios: "arrow.clockwise", android: "refresh" },
  person: { ios: "person", android: "person" },
  show: { ios: "eye", android: "visibility" },
  hide: { ios: "eye.slash", android: "visibility_off" },
  tag: { ios: "tag", android: "sell" },
  failed: { ios: "exclamationmark.circle", android: "error" },
  clock: { ios: "clock", android: "schedule" },
  sent: { ios: "checkmark", android: "check" },
  read: { ios: "checkmark.message", android: "done_all" },
  // Spec 044 (Reservas)
  calendar: { ios: "calendar", android: "event" },
  calendarAdd: { ios: "calendar.badge.plus", android: "calendar_add_on" },
  plus: { ios: "plus", android: "add" },
  walkIn: { ios: "figure.walk.arrival", android: "directions_walk" },
  grid: { ios: "square.grid.3x3", android: "grid_view" },
  list: { ios: "list.bullet", android: "view_list" },
  minus: { ios: "minus", android: "remove" },
  back: { ios: "chevron.left", android: "chevron_left" },
  people: { ios: "person.2", android: "group" },
  waitlist: { ios: "person.badge.clock", android: "pending_actions" },
  sliders: { ios: "slider.horizontal.3", android: "tune" },
  block: { ios: "nosign", android: "block" },
  phone: { ios: "phone", android: "call" },
  google: { ios: "calendar.badge.checkmark", android: "event_available" },
} satisfies Record<string, IconName>;
