import { StyleSheet, View } from "react-native";

import type { Counts, Home } from "@/api/endpoints";
import type { Locale, T } from "@/i18n/t";
import { formatNumber } from "@/lib/format";
import { Card } from "@/ui/card";
import { Icon, icons } from "@/ui/icon";
import { ErrorState, PartialNotice } from "@/ui/states";
import { Text } from "@/ui/text";

import { CalmCard, WaitingCard } from "./footer";
import { Latest } from "./latest";
import { balanceAttention, balanceLastsMonth, bizLine, firstWaiting, useCalmOnce, type HomeMe } from "./model";
import type { InboxPeek } from "./reads";
import { askLine, homeTiles, Tiles } from "./tiles";
import type { TodayReservas } from "./today-reservas";

/**
 * Inicio (spec 069, R8; amends 044 R9 and 042 R5): it fits one screen. The
 * business and who answers; four tiles read at a glance, each opening its tab;
 * «Lo último en la Bandeja»; and at the bottom, in the thumb's reach, whoever
 * waits for a person — or, once nobody does, the calm card for 3,2 s. Pure:
 * every state is testable without a request. `home === null` is the whole
 * read failing; `home.errors` lists blocks that did not load (partial). A
 * module the client lacks has no tile, no list and no card (constitution §V).
 */
export function HomeView({
  me,
  home,
  t,
  locale,
  now = new Date(),
  onRetry,
  onAttend,
  onUsage,
  onInbox,
  reservas = null,
  onReservas,
  latest = null,
  waiting = null,
  counts = null,
  onOpenConversation,
  focused = true,
}: {
  me: HomeMe;
  home: Home | null;
  t: T;
  locale: Locale;
  now?: Date;
  onRetry: () => void;
  /** «Atender a …»: the conversation in the Bandeja's tab (`null`: the Bandeja itself). */
  onAttend: (conversationId: string | null) => void;
  onUsage: () => void;
  onInbox?: () => void;
  /** Spec 044, R9.1: today in Reservas; `null` without the module (R8.2). */
  reservas?: TodayReservas | null;
  onReservas?: () => void;
  /** The Bandeja's open conversations and the ones waiting; `null` without the module. */
  latest?: InboxPeek | null;
  waiting?: InboxPeek | null;
  counts?: Counts | null;
  onOpenConversation?: (id: string) => void;
  /** Whether Inicio is the screen in front: the calm card compares what it saw then (R8.5). */
  focused?: boolean;
}) {
  const n = (v: number) => formatNumber(v, locale);
  const modules = me.nav;
  const hasInbox = modules.includes("inbox");
  const waitCount = home && hasInbox && home.waiting ? home.waiting.count : null;
  const trouble = home ? balanceAttention(home) : null;
  const calm = useCalmOnce(waitCount, focused, trouble !== null);

  if (home === null) return <ErrorState body={t("common.error.backend")} onRetry={onRetry} />;

  const tiles = homeTiles({
    home,
    modules,
    today: reservas,
    counts,
    contact: me.balance_contact ?? null,
    t,
    locale,
    now,
    onReservas,
    onInbox,
    onUsage,
  });
  const someoneWaits = (waitCount ?? 0) > 0;
  const first = waiting?.state === "ready" ? firstWaiting(waiting.items, home.waiting?.first_conversation_id) : null;
  // Without Consumo there is no Saldo tile, but a balance in trouble is still said (031 R4.1): the agent may be silent.
  const notice = trouble && !modules.includes("usage") ? trouble : null;

  return (
    <View style={styles.screen}>
      <View style={styles.top}>
        {home.errors.length > 0 ? <PartialNotice text={t("lite.panel.partial")} /> : null}
        <View style={styles.biz} accessible accessibilityRole="text">
          <Icon name={icons.store} size={16} tone="mutedForeground" />
          <Text variant="subhead" tone="mutedForeground" style={styles.flex}>
            {bizLine(me.client.name, me.agents, t)}
          </Text>
        </View>
        {tiles.length > 0 ? <Tiles tiles={tiles} label={t("v13.home.tiles")} /> : null}
        {notice ? (
          <Card tone={notice === "balance_out" ? "danger" : "warning"} testID="home-balance-notice">
            <Text variant="bodyStrong" tone={notice === "balance_out" ? "dangerText" : "warningText"}>
              {t("lite.attention.balance")}
            </Text>
            <Text variant="callout">
              {[
                notice === "balance_out"
                  ? t("lite.attention.balance_out")
                  : t("lite.attention.balance_low", { days: n(Math.floor(home.attention.find((a) => a.kind === "balance_low")?.days_left ?? 0)) }),
                askLine(me.balance_contact ?? null, t),
              ]
                .filter(Boolean)
                .join(". ")}
            </Text>
          </Card>
        ) : null}
        {latest && onOpenConversation ? <Latest peek={latest} someoneWaits={someoneWaits} agents={me.agents} t={t} onOpen={onOpenConversation} /> : null}
      </View>
      <View style={styles.foot}>
        {someoneWaits && hasInbox ? (
          <WaitingCard c={first} count={waitCount ?? 0} firstId={home.waiting?.first_conversation_id ?? null} now={now} t={t} n={n} onAttend={onAttend} />
        ) : calm ? (
          <CalmCard body={balanceLastsMonth(home.balance, now) ? t("v13.home.calm.body") : t("v13.home.calm.body.noBalance")} t={t} />
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  // Grows to the screen's height, so the bottom card sits in the thumb's reach (R8.4).
  screen: { flexGrow: 1, gap: 16 },
  top: { gap: 16 },
  biz: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 4 },
  flex: { flex: 1, minWidth: 0 },
  foot: { marginTop: "auto" },
});
