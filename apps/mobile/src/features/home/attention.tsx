import { StyleSheet, View } from "react-native";

import type { Home, Me } from "@/api/endpoints";
import type { T } from "@/i18n/t";
import { useTheme } from "@/theme/theme";
import { Divider, RowButton } from "@/ui/bits";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

/**
 * «Necesita tu atención» (spec 030 R4.5–R4.7, here R4.1; spec 042 R5.1, R5.2):
 * what waits for a person goes first, with its way in, within reach of the
 * thumb; a short balance says for how long it lasts and whom to ask — there
 * is no buy button (R4.4). Nothing pending is one calm line. The number of
 * conversations waiting appears once, in its row, and nothing counts
 * anything else next to the title (H13).
 */
export function Attention({
  home,
  contact,
  modules,
  t,
  n,
  onAttend,
  onUsage,
}: {
  home: Home;
  contact: Me["balance_contact"] | null;
  modules: readonly string[];
  t: T;
  n: (v: number) => string;
  onAttend: (conversationId: string | null) => void;
  onUsage: () => void;
}) {
  const { colors } = useTheme();
  const hasInbox = modules.includes("inbox");
  const ask = contact ? (contact.kind === "auphere" ? t("lite.attention.ask.auphere") : t("lite.attention.ask.partner", { name: contact.name })) : null;

  if (home.attention.length === 0) {
    if (home.errors.length > 0) return null;
    const balanceKnown = home.balance?.assigned === true;
    const line = balanceKnown ? (hasInbox ? t("lite.ok.withInbox") : t("lite.ok")) : hasInbox ? t("lite.ok.noBalance.withInbox") : null;
    if (!line) return null;
    return (
      <Card tone="positive" style={styles.ok}>
        <View style={styles.okRow} accessible accessibilityRole="text">
          <Icon name={icons.check} size={20} tone="positiveText" />
          <Text variant="callout" style={styles.flex}>
            {line}
          </Text>
        </View>
      </Card>
    );
  }

  return (
    <Card tone="danger">
      <View style={styles.title}>
        <Icon name={icons.warning} size={18} tone="dangerText" />
        <Text variant="headline" accessibilityRole="header" style={styles.flex}>
          {t("lite.attention.title")}
        </Text>
      </View>
      {home.attention.map((item, i) => {
        const divider = i > 0 ? <Divider /> : null;
        if (item.kind === "waiting") {
          const count = item.count ?? 0;
          return (
            <View key="waiting" style={styles.item}>
              {divider}
              {/* The sentence already names the inbox; a «Bandeja de entrada» label above it said it twice (R5.1). */}
              <Text variant="bodyStrong">
                {count === 1 ? t("lite.attention.waiting.one") : t("lite.attention.waiting", { count: n(count) })}
              </Text>
              {hasInbox ? (
                <Button
                  label={t("lite.attention.attend")}
                  icon={icons.hand}
                  full
                  onPress={() => onAttend(home.waiting?.first_conversation_id ?? null)}
                />
              ) : null}
            </View>
          );
        }
        const body =
          item.kind === "balance_out"
            ? t("lite.attention.balance_out")
            : t("lite.attention.balance_low", { days: n(Math.floor(item.days_left ?? 0)) });
        return (
          <View key={item.kind} style={styles.item}>
            {divider}
            <Text variant="bodyStrong" style={{ color: item.kind === "balance_out" ? colors.dangerText : colors.warningText }}>
              {t("lite.attention.balance")}
            </Text>
            <Text variant="callout" tone="mutedForeground">
              {ask ? `${body}. ${ask}` : body}
            </Text>
            {modules.includes("usage") ? (
              <View style={styles.bleed}>
                <RowButton title={t("lite.spend.see")} tone="primaryText" kind="push" onPress={onUsage} />
              </View>
            ) : null}
          </View>
        );
      })}
    </Card>
  );
}

const styles = StyleSheet.create({
  ok: { paddingVertical: 12 },
  okRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  flex: { flex: 1, minWidth: 0 },
  title: { flexDirection: "row", alignItems: "center", gap: 8 },
  item: { gap: 6, paddingTop: 4 },
  // The row's press tint reaches the card's edges, past the card's own padding.
  bleed: { marginHorizontal: -16 },
});
