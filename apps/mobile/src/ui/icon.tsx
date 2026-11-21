import type { LucideIcon } from "lucide-react-native";
// One import per icon: Metro does not prune the package barrel (spec 069, R22.2).
import Archive from "lucide-react-native/icons/archive";
import ArrowRightLeft from "lucide-react-native/icons/arrow-right-left";
import ArrowUp from "lucide-react-native/icons/arrow-up";
import AudioLines from "lucide-react-native/icons/audio-lines";
import BadgeCheck from "lucide-react-native/icons/badge-check";
import Ban from "lucide-react-native/icons/ban";
import Bell from "lucide-react-native/icons/bell";
import BellOff from "lucide-react-native/icons/bell-off";
import BellRing from "lucide-react-native/icons/bell-ring";
import Bot from "lucide-react-native/icons/bot";
import Building2 from "lucide-react-native/icons/building-2";
import CalendarCheck from "lucide-react-native/icons/calendar-check";
import CalendarClock from "lucide-react-native/icons/calendar-clock";
import CalendarDays from "lucide-react-native/icons/calendar-days";
import CalendarPlus from "lucide-react-native/icons/calendar-plus";
import CalendarX from "lucide-react-native/icons/calendar-x";
import ChartColumn from "lucide-react-native/icons/chart-column";
import Check from "lucide-react-native/icons/check";
import CheckCheck from "lucide-react-native/icons/check-check";
import ChevronLeft from "lucide-react-native/icons/chevron-left";
import ChevronRight from "lucide-react-native/icons/chevron-right";
import CircleAlert from "lucide-react-native/icons/circle-alert";
import CircleCheck from "lucide-react-native/icons/circle-check";
import CircleUser from "lucide-react-native/icons/circle-user";
import Clock from "lucide-react-native/icons/clock";
import Coins from "lucide-react-native/icons/coins";
import DoorOpen from "lucide-react-native/icons/door-open";
import Ellipsis from "lucide-react-native/icons/ellipsis";
import Eraser from "lucide-react-native/icons/eraser";
import ExternalLink from "lucide-react-native/icons/external-link";
import Eye from "lucide-react-native/icons/eye";
import EyeOff from "lucide-react-native/icons/eye-off";
import FileText from "lucide-react-native/icons/file-text";
import Globe from "lucide-react-native/icons/globe";
import Hand from "lucide-react-native/icons/hand";
import Hourglass from "lucide-react-native/icons/hourglass";
import House from "lucide-react-native/icons/house";
import ImageIcon from "lucide-react-native/icons/image";
import Inbox from "lucide-react-native/icons/inbox";
import Info from "lucide-react-native/icons/info";
import LayoutGrid from "lucide-react-native/icons/layout-grid";
import LifeBuoy from "lucide-react-native/icons/life-buoy";
import List from "lucide-react-native/icons/list";
import Lock from "lucide-react-native/icons/lock";
import LogOut from "lucide-react-native/icons/log-out";
import Mail from "lucide-react-native/icons/mail";
import MailCheck from "lucide-react-native/icons/mail-check";
import MessageCircle from "lucide-react-native/icons/message-circle";
import MessageSquareQuote from "lucide-react-native/icons/message-square-quote";
import MessageSquareText from "lucide-react-native/icons/message-square-text";
import MessagesSquare from "lucide-react-native/icons/messages-square";
import Minus from "lucide-react-native/icons/minus";
import Moon from "lucide-react-native/icons/moon";
import Paperclip from "lucide-react-native/icons/paperclip";
import Pencil from "lucide-react-native/icons/pencil";
import Phone from "lucide-react-native/icons/phone";
import Plus from "lucide-react-native/icons/plus";
import RefreshCw from "lucide-react-native/icons/refresh-cw";
import RotateCcw from "lucide-react-native/icons/rotate-ccw";
import RotateCw from "lucide-react-native/icons/rotate-cw";
import Search from "lucide-react-native/icons/search";
import Shield from "lucide-react-native/icons/shield";
import SlidersHorizontal from "lucide-react-native/icons/sliders-horizontal";
import Smartphone from "lucide-react-native/icons/smartphone";
import Sparkles from "lucide-react-native/icons/sparkles";
import Store from "lucide-react-native/icons/store";
import Sun from "lucide-react-native/icons/sun";
import Tag from "lucide-react-native/icons/tag";
import Trash2 from "lucide-react-native/icons/trash-2";
import TriangleAlert from "lucide-react-native/icons/triangle-alert";
import Undo2 from "lucide-react-native/icons/undo-2";
import User from "lucide-react-native/icons/user";
import Users from "lucide-react-native/icons/users";
import Video from "lucide-react-native/icons/video";
import Wallet from "lucide-react-native/icons/wallet";
import WifiOff from "lucide-react-native/icons/wifi-off";
import X from "lucide-react-native/icons/x";
import type { SymbolViewProps } from "expo-symbols";
import { View } from "react-native";

import { useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";

/**
 * One icon family in the whole app (spec 069, D1, R1.3): Lucide, drawn by the
 * app, at the design's 1.75 stroke. Each entry also names its system symbol
 * (SF Symbols on iOS, Material Symbols on Android) for the system's own chrome
 * — tab bar, bar buttons, native menus — where the app does not draw and the
 * system asks for a symbol (`.ios` / `.android`). Decorative by default: the
 * control that holds it carries the accessible name.
 */
type NameObject = Exclude<SymbolViewProps["name"], string>;
/** Checked at compile time: a Lucide component and each platform's symbol. A typo does not build. */
export type IconName = {
  lucide: LucideIcon;
  ios: NonNullable<NameObject["ios"]>;
  android: NonNullable<NameObject["android"]>;
};

/** A system symbol only, for the system's own chrome (the tab bar's selected state). */
export type SymbolName = Omit<IconName, "lucide">;

/** The design's stroke (app.css, «icons: Lucide, stroke 1.75»). */
export const ICON_STROKE = 1.75;

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
  const Glyph = name.lucide;
  return (
    <View accessible={false} importantForAccessibility="no-hide-descendants" pointerEvents="none">
      <Glyph size={size} color={colors[tone]} strokeWidth={ICON_STROKE} />
    </View>
  );
}

/** The app's icons, named once so both platforms stay in step. */
export const icons = {
  home: { lucide: House, ios: "house", android: "home" },
  inbox: { lucide: Inbox, ios: "tray", android: "inbox" },
  usage: { lucide: ChartColumn, ios: "chart.bar", android: "bar_chart" },
  settings: { lucide: CircleUser, ios: "person.crop.circle", android: "account_circle" },
  more: { lucide: Ellipsis, ios: "ellipsis.circle", android: "more_vert" },
  giveBack: { lucide: Undo2, ios: "arrow.uturn.backward", android: "undo" },
  unread: { lucide: Mail, ios: "envelope.badge", android: "mark_email_unread" },
  reopen: { lucide: RotateCcw, ios: "arrow.counterclockwise", android: "restart_alt" },
  hand: { lucide: Hand, ios: "hand.raised", android: "back_hand" },
  wallet: { lucide: Wallet, ios: "creditcard", android: "account_balance_wallet" },
  money: { lucide: Coins, ios: "dollarsign.circle", android: "paid" },
  chat: { lucide: MessagesSquare, ios: "bubble.left.and.bubble.right", android: "forum" },
  bot: { lucide: Bot, ios: "sparkles", android: "smart_toy" },
  warning: { lucide: TriangleAlert, ios: "exclamationmark.triangle", android: "warning" },
  check: { lucide: CircleCheck, ios: "checkmark.circle", android: "check_circle" },
  offline: { lucide: WifiOff, ios: "wifi.slash", android: "wifi_off" },
  send: { lucide: ArrowUp, ios: "arrow.up.circle.fill", android: "send" },
  arrowUp: { lucide: ArrowUp, ios: "arrow.up", android: "arrow_upward" },
  attach: { lucide: Plus, ios: "paperclip", android: "attach_file" },
  replies: { lucide: MessageSquareQuote, ios: "text.bubble", android: "quickreply" },
  image: { lucide: ImageIcon, ios: "photo", android: "image" },
  document: { lucide: FileText, ios: "doc.text", android: "description" },
  audio: { lucide: AudioLines, ios: "waveform", android: "graphic_eq" },
  video: { lucide: Video, ios: "video", android: "videocam" },
  bell: { lucide: Bell, ios: "bell", android: "notifications" },
  external: { lucide: ExternalLink, ios: "arrow.up.right.square", android: "open_in_new" },
  chevron: { lucide: ChevronRight, ios: "chevron.right", android: "chevron_right" },
  close: { lucide: X, ios: "xmark", android: "close" },
  retry: { lucide: RotateCw, ios: "arrow.clockwise", android: "refresh" },
  person: { lucide: User, ios: "person", android: "person" },
  show: { lucide: Eye, ios: "eye", android: "visibility" },
  hide: { lucide: EyeOff, ios: "eye.slash", android: "visibility_off" },
  tag: { lucide: Tag, ios: "tag", android: "sell" },
  failed: { lucide: CircleAlert, ios: "exclamationmark.circle", android: "error" },
  clock: { lucide: Clock, ios: "clock", android: "schedule" },
  sent: { lucide: Check, ios: "checkmark", android: "check" },
  read: { lucide: CheckCheck, ios: "checkmark.message", android: "done_all" },
  // Spec 044 (Reservas)
  calendar: { lucide: CalendarDays, ios: "calendar", android: "event" },
  calendarAdd: { lucide: CalendarPlus, ios: "calendar.badge.plus", android: "calendar_add_on" },
  plus: { lucide: Plus, ios: "plus", android: "add" },
  walkIn: { lucide: DoorOpen, ios: "figure.walk.arrival", android: "directions_walk" },
  grid: { lucide: LayoutGrid, ios: "square.grid.3x3", android: "grid_view" },
  list: { lucide: List, ios: "list.bullet", android: "view_list" },
  minus: { lucide: Minus, ios: "minus", android: "remove" },
  back: { lucide: ChevronLeft, ios: "chevron.left", android: "chevron_left" },
  people: { lucide: Users, ios: "person.2", android: "group" },
  waitlist: { lucide: Hourglass, ios: "person.badge.clock", android: "pending_actions" },
  sliders: { lucide: SlidersHorizontal, ios: "slider.horizontal.3", android: "tune" },
  block: { lucide: Ban, ios: "nosign", android: "block" },
  phone: { lucide: Phone, ios: "phone", android: "call" },
  google: { lucide: CalendarCheck, ios: "calendar.badge.checkmark", android: "event_available" },
  // Spec 047 (corrections); the agents' and Negocio's left with them (spec 056, 2.6)
  edit: { lucide: Pencil, ios: "pencil", android: "edit" },
  // Spec 069: the design's icons that the app had not used yet.
  search: { lucide: Search, ios: "magnifyingglass", android: "search" },
  store: { lucide: Store, ios: "storefront", android: "storefront" },
  calendarX: { lucide: CalendarX, ios: "calendar.badge.exclamationmark", android: "event_busy" },
  calendarClock: { lucide: CalendarClock, ios: "calendar.badge.clock", android: "pending_actions" },
  bellOff: { lucide: BellOff, ios: "bell.slash", android: "notifications_off" },
  bellRing: { lucide: BellRing, ios: "bell.badge", android: "notifications_active" },
  logOut: { lucide: LogOut, ios: "rectangle.portrait.and.arrow.right", android: "logout" },
  trash: { lucide: Trash2, ios: "trash", android: "delete" },
  globe: { lucide: Globe, ios: "globe", android: "language" },
  sun: { lucide: Sun, ios: "sun.max", android: "light_mode" },
  moon: { lucide: Moon, ios: "moon", android: "dark_mode" },
  smartphone: { lucide: Smartphone, ios: "iphone", android: "smartphone" },
  badge: { lucide: BadgeCheck, ios: "checkmark.seal", android: "verified" },
  mail: { lucide: Mail, ios: "envelope", android: "mail" },
  mailCheck: { lucide: MailCheck, ios: "envelope.badge", android: "mark_email_read" },
  lock: { lucide: Lock, ios: "lock", android: "lock" },
  info: { lucide: Info, ios: "info.circle", android: "info" },
  sparkles: { lucide: Sparkles, ios: "sparkles", android: "auto_awesome" },
  message: { lucide: MessageCircle, ios: "message", android: "chat_bubble" },
  messageText: { lucide: MessageSquareText, ios: "text.bubble", android: "chat" },
  refresh: { lucide: RefreshCw, ios: "arrow.triangle.2.circlepath", android: "sync" },
  building: { lucide: Building2, ios: "building.2", android: "business" },
  privacy: { lucide: Shield, ios: "hand.raised.square", android: "shield" },
  support: { lucide: LifeBuoy, ios: "lifepreserver", android: "support" },
  archive: { lucide: Archive, ios: "archivebox", android: "archive" },
  clear: { lucide: Eraser, ios: "eraser", android: "backspace" },
  move: { lucide: ArrowRightLeft, ios: "arrow.left.arrow.right", android: "swap_horiz" },
  circleCheck: { lucide: CircleCheck, ios: "checkmark.circle", android: "check_circle" },
  checkmark: { lucide: Check, ios: "checkmark", android: "check" },
  attachFile: { lucide: Paperclip, ios: "paperclip", android: "attach_file" },
} satisfies Record<string, IconName>;