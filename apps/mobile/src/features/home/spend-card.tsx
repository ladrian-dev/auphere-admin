import { StyleSheet, View } from "react-native";

import type { Home } from "@/api/endpoints";
import type { Locale, T } from "@/i18n/t";
import { formatMoney } from "@/lib/format";
import { shares } from "@/lib/panel-model";
import { useTheme } from "@/theme/theme";
import type { Palette } from "@/theme/tokens.gen";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { icons } from "@/ui/icon";
import { Text } from "@/ui/text";

const SLICES: (keyof Palette)[] = ["primary", "primaryDeep", "accentDeep", "subtle", "info"];

/**
 * «Gasto del mes» (R4.1): the same money the console shows for this client.
 * With more than one agent it splits by agent; with one, a single slice says
 * nothing, so it is just the amount.
 */
export function SpendCard({
  spend,
  t,
  locale,
  onUsage,
}: {
  spend: NonNullable<Home["spend_month"]>;
  t: T;
  locale: Locale;
  onUsage?: () => void;
}) {
  const { colors, radius } = useTheme();
  const byAgent = spend.by_agent && spend.by_agent.length > 1 ? spend.by_agent : null;
  const pcts = byAgent ? shares(byAgent.map((a) => a.cents)) : [];
  return (
    <Card>
      <View style={styles.head}>
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header" style={styles.flex}>
          {t("lite.spend.title")}
        </Text>
        {onUsage ? <Button label={t("lite.spend.see")} variant="ghost" compact icon={icons.usage} onPress={onUsage} /> : null}
      </View>
      <Text variant="figure">{formatMoney(spend.total_cents, locale)}</Text>
      {byAgent ? (
        <>
          <View style={styles.bar} accessible={false} importantForAccessibility="no-hide-descendants">
            {byAgent.map((a, i) => (
              <View
                key={a.agent_id}
                style={{ flex: Math.max(a.cents, 1), backgroundColor: colors[SLICES[i % SLICES.length]!], borderRadius: radius.sm }}
              />
            ))}
          </View>
          {byAgent.map((a, i) => (
            <View key={a.agent_id} style={styles.row} accessible accessibilityLabel={`${a.name}: ${formatMoney(a.cents, locale)}, ${pcts[i]} %`}>
              <View style={[styles.dot, { backgroundColor: colors[SLICES[i % SLICES.length]!] }]} />
              <Text variant="callout" style={styles.flex} numberOfLines={2}>
                {a.name}
              </Text>
              <Text variant="callout" tone="mutedForeground">
                {pcts[i]} %
              </Text>
              <Text variant="callout" style={styles.amount}>
                {formatMoney(a.cents, locale)}
              </Text>
            </View>
          ))}
        </>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  flex: { flex: 1, minWidth: 0 },
  bar: { flexDirection: "row", height: 10, gap: 3, marginTop: 4 },
  row: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap" },
  dot: { width: 8, height: 8, borderRadius: 2 },
  amount: { fontVariant: ["tabular-nums"], fontWeight: "600" },
});
