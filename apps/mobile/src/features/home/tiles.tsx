import { Pressable, StyleSheet, useWindowDimensions, View } from "react-native";

import type { Counts, Home } from "@/api/endpoints";
import { firstName, nameOf } from "@/features/reservas/format";
import type { Locale, T } from "@/i18n/t";
import { formatMoney, formatNumber } from "@/lib/format";
import { trendDelta } from "@/lib/panel-model";
import { arrivingNextHour, daySummary, hhmm, insideAt, upcoming } from "@/lib/reservas-model";
import { CARD_RADIUS, RADII, useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";
import { Icon, icons, type IconName } from "@/ui/icon";
import { Text } from "@/ui/text";

import { balanceAttention, lasting, lastingText } from "./model";
import type { TodayReservas } from "./today-reservas";

/**
 * The four tiles of Inicio (spec 069, R8.1, R8.2): Hoy, Conversaciones,
 * Saldo, Este mes — read at a glance, each opening its tab. A tile exists only
 * with its module (Hoy ↔ Reservas, Conversaciones ↔ Bandeja, Saldo and Este
 * mes ↔ Consumo, constitution §V), and the rest fill the space: two per row,
 * an odd one across the whole row, one per row with large text. Hoy wears the
 * mint frame — the tile the owner looks for first (log, decision 2).
 */
export type TileSpec = {
  key: "today" | "conversations" | "balance" | "month";
  icon: IconName;
  kicker: string;
  /** The figure, in the display face; `null` while it loads. */
  value: string | null;
  valueTone?: keyof Palette;
  /** Words after the figure, in the text face («reservas», «en 7 días»). */
  unit?: string;
  sub?: string;
  subTone?: keyof Palette;
  extra?: string;
  extraTone?: keyof Palette;
  highlight?: boolean;
  onPress: () => void;
};

/** Past this text size the tiles go one per row: a figure never shrinks to fit half a phone (R1.7). */
const ONE_COLUMN_AT = 1.5;

export function Tiles({ tiles, label }: { tiles: TileSpec[]; label: string }) {
  const { fontScale } = useWindowDimensions();
  const perRow = fontScale >= ONE_COLUMN_AT ? 1 : 2;
  const rows: TileSpec[][] = [];
  for (let i = 0; i < tiles.length; i += perRow) rows.push(tiles.slice(i, i + perRow));
  return (
    <View accessibilityLabel={label} testID="home-tiles" style={styles.grid}>
      {rows.map((row) => (
        <View key={row.map((r) => r.key).join("-")} style={styles.row}>
          {row.map((tile) => (
            <Tile key={tile.key} tile={tile} />
          ))}
        </View>
      ))}
    </View>
  );
}

function Tile({ tile }: { tile: TileSpec }) {
  const { colors } = useTheme();
  const spoken = [
    tile.value === null ? tile.kicker : `${tile.kicker}: ${tile.value}${tile.unit ? ` ${tile.unit}` : ""}`,
    tile.sub,
    tile.extra,
  ]
    .filter(Boolean)
    .join(". ");
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={spoken}
      onPress={tile.onPress}
      android_ripple={{ color: colors.muted }}
      testID={`tile-${tile.key}`}
      style={({ pressed }) => [
        styles.tile,
        {
          backgroundColor: pressed ? colors.muted : colors.card,
          borderColor: tile.highlight ? colors.highlight : colors.border,
        },
      ]}
    >
      {/* The mint ground sits on the card's own white, so it reads the same in light and dark. */}
      {tile.highlight ? <View testID="tile-highlight" pointerEvents="none" style={[StyleSheet.absoluteFill, { backgroundColor: colors.highlightSoft }]} /> : null}
      {tile.highlight ? <View pointerEvents="none" style={[styles.dot, { backgroundColor: colors.highlight }]} /> : null}
      <View style={styles.kicker}>
        <Icon name={tile.icon} size={15} tone="mutedForeground" />
        {/* Half a phone wide, with large text a long word («Conversaciones») may not fit: it breaks with a hyphen, never bare. */}
        <Text variant="subhead" tone="mutedForeground" style={styles.flex} android_hyphenationFrequency="normal">
          {tile.kicker}
        </Text>
      </View>
      {tile.value === null ? (
        <View style={[styles.placeholder, { backgroundColor: colors.muted }]} />
      ) : (
        <Text variant="figureLarge" tone={tile.valueTone ?? "foreground"} numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.6}>
          {tile.value}
          {tile.unit ? (
            <Text variant="subhead" tone="mutedForeground">
              {` ${tile.unit}`}
            </Text>
          ) : null}
        </Text>
      )}
      {tile.sub ? (
        <Text variant="footnote" tone={tile.subTone ?? "mutedForeground"}>
          {tile.sub}
        </Text>
      ) : null}
      {tile.extra ? (
        <Text variant="footnote" tone={tile.extraTone ?? "mutedForeground"}>
          {tile.extra}
        </Text>
      ) : null}
    </Pressable>
  );
}

/**
 * The tiles a client has, in the design's order. `today` is `null` without
 * Reservas; a block the API could not read (`home.errors`) is `null` too and
 * has no tile — the partial notice says it once.
 */
export function homeTiles(p: {
  home: Home;
  modules: readonly string[];
  today: TodayReservas | null;
  counts: Counts | null;
  contact: { kind: "partner" | "auphere"; name: string } | null;
  t: T;
  locale: Locale;
  now: Date;
  onReservas?: () => void;
  onInbox?: () => void;
  onUsage: () => void;
}): TileSpec[] {
  const { home, modules, today, counts, contact, t, locale, now } = p;
  const n = (v: number) => formatNumber(v, locale);
  const out: TileSpec[] = [];

  if (today && p.onReservas) out.push(todayTile(today, t, p.onReservas));

  const conv = home.conversations ?? null;
  if (conv && modules.includes("inbox") && p.onInbox) {
    const delta = trendDelta(conv.last_7d, conv.prev_7d ?? null);
    const sub =
      conv.last_7d === 0 && (!counts || counts.unread === 0)
        ? t("v13.home.tile.conversations.none")
        : counts
          ? counts.unread === 0
            ? t("v13.home.tile.conversations.allRead")
            : counts.unread === 1
              ? t("v13.home.tile.conversations.unread.one")
              : t("v13.home.tile.conversations.unread", { n: n(counts.unread) })
          : delta.kind === "none"
            ? undefined
            : t(`hu.home.kpi.delta.${delta.kind}`, { pct: n(delta.pct) });
    // The week against the one before stays (042 R5): under the unread when the counts are there, as the line itself when not.
    const trend = counts && delta.kind !== "none" ? t(`hu.home.kpi.delta.${delta.kind}`, { pct: n(delta.pct) }) : undefined;
    out.push({
      key: "conversations",
      icon: icons.message,
      kicker: t("lite.kpi.conversations"),
      value: n(conv.last_7d),
      unit: t("v13.home.tile.conversations.unit"),
      sub,
      ...(trend ? { extra: trend } : {}),
      onPress: p.onInbox,
    });
  }

  const hasUsage = modules.includes("usage");
  const balance = home.balance ?? null;
  if (balance && hasUsage) {
    const trouble = balanceAttention(home);
    const out_ = balance.assigned === true && (balance.remaining_cents ?? 0) <= 0;
    const ask = trouble || out_ ? askLine(contact, t) : undefined;
    const sub = !balance.assigned
      ? t("lite.kpi.balance.unassigned")
      : out_
        ? t("lite.kpi.balance.out")
        : balance.days_left == null
          ? t("lite.kpi.balance.noSpend")
          : lastingText(
              lasting(balance.days_left),
              {
                months: "v13.home.tile.balance.months",
                days: "v13.home.tile.balance.days",
                day: "v13.home.tile.balance.day",
                lessThanDay: "v13.home.tile.balance.lessThanDay",
              },
              t,
              n,
            );
    out.push({
      key: "balance",
      icon: icons.wallet,
      kicker: t("v13.home.tile.balance"),
      value: balance.assigned && balance.remaining_cents != null ? formatMoney(balance.remaining_cents, locale, balance.currency) : "—",
      valueTone: out_ ? "dangerText" : "foreground",
      sub,
      subTone: out_ ? "dangerText" : trouble === "balance_low" ? "warningText" : "mutedForeground",
      ...(ask ? { extra: ask } : {}),
      onPress: p.onUsage,
    });
  }

  const spend = home.spend_month ?? null;
  if (spend && hasUsage) {
    const month = now.toLocaleDateString(locale, { month: "long" });
    out.push({
      key: "month",
      icon: icons.money,
      kicker: t("v13.home.tile.month"),
      // Spec 069, R21.1: the bag's currency — without it `formatMoney` said US$ for a bag in EUR.
      value: formatMoney(spend.total_cents, locale, spend.currency),
      sub: spend.total_cents > 0 ? t("v13.home.tile.month.since", { month }) : t("lite.usage.month.none"),
      onPress: p.onUsage,
    });
  }
  return out;
}

/** Whom to ask for more balance, as words (R18.2): there is no button to buy. */
export function askLine(contact: { kind: "partner" | "auphere"; name: string } | null, t: T): string | undefined {
  if (!contact) return undefined;
  return contact.kind === "auphere" ? t("lite.attention.ask.auphere") : t("lite.attention.ask.partner", { name: contact.name });
}

function todayTile(today: TodayReservas, t: T, onPress: () => void): TileSpec {
  const base = { key: "today" as const, icon: icons.calendar, kicker: t("v13.home.tile.today"), highlight: true, onPress };
  if (today.state === "loading") return { ...base, value: null, sub: t("reservas.loading") };
  if (today.state === "error") return { ...base, value: "—", sub: t("reservas.error") };
  const { config, items, now, waitlist } = today;
  const day = items.filter((r) => r.date === now.date);
  const cap = config.capacity;
  if (cap) {
    const arriving = arrivingNextHour(day, now);
    return {
      ...base,
      value: String(insideAt(day, now.date, now.minutes, cap.stayMin)),
      unit: t("v13.home.tile.today.inside", { capacity: cap.capacity }),
      sub:
        waitlist !== null
          ? t("app.home.today.arriving", { n: arriving, unit: cap.unit, w: waitlist })
          : t("app.home.today.arriving.noWait", { n: arriving, unit: cap.unit }),
    };
  }
  const sum = daySummary(day);
  const next = upcoming(day, now, 1)[0];
  return {
    ...base,
    value: String(sum.total),
    unit: sum.total === 1 ? t("v13.home.tile.today.unit.one") : t("v13.home.tile.today.unit"),
    // An empty day is not «no more»: that would say some were (review H16).
    sub: next
      ? t("v13.home.tile.today.next", { time: hhmm(next.start), name: firstName(nameOf(next, t)) })
      : sum.total === 0
        ? t("v13.home.tile.today.empty")
        : t("v13.home.tile.today.none"),
    ...(sum.unconfirmed > 0 ? { extra: t("v13.home.tile.today.unconfirmed", { n: sum.unconfirmed }), extraTone: "warningText" as const } : {}),
  };
}

const styles = StyleSheet.create({
  grid: { gap: 10 },
  row: { flexDirection: "row", gap: 10, alignItems: "stretch" },
  tile: {
    flex: 1,
    minWidth: 0,
    padding: 14,
    gap: 4,
    borderRadius: CARD_RADIUS,
    borderWidth: StyleSheet.hairlineWidth * 2,
    overflow: "hidden",
  },
  kicker: { flexDirection: "row", alignItems: "center", gap: 6, paddingRight: 10 },
  flex: { flex: 1, minWidth: 0 },
  dot: { position: "absolute", top: 12, right: 12, width: 8, height: 8, borderRadius: 4 },
  placeholder: { height: 30, width: "60%", borderRadius: RADII.sm, marginVertical: 2 },
});
