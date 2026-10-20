import type { NoticeKind } from "@/api/endpoints";
import type { MessageKey } from "@/i18n/t";
import { icons, type IconName } from "@/ui/icon";

/**
 * The three kinds of notice (R8.1), and which ones a person can get: the
 * inbox ones only with the Bandeja (R9.3). Same words in the permission
 * screen and in Ajustes.
 */
export const NOTICE_KINDS: { kind: NoticeKind; label: MessageKey; hint: MessageKey; icon: IconName; needs: string | null }[] = [
  { kind: "inbox.waiting", label: "app.notices.kind.inbox.waiting", hint: "app.notices.kind.inbox.waiting.hint", icon: icons.hand, needs: "inbox" },
  {
    kind: "inbox.message_for_you",
    label: "app.notices.kind.inbox.message_for_you",
    hint: "app.notices.kind.inbox.message_for_you.hint",
    icon: icons.chat,
    needs: "inbox",
  },
  { kind: "client.balance", label: "app.notices.kind.client.balance", hint: "app.notices.kind.client.balance.hint", icon: icons.wallet, needs: null },
];

export function kindsFor(modules: readonly string[]) {
  return NOTICE_KINDS.filter((k) => k.needs === null || modules.includes(k.needs));
}
