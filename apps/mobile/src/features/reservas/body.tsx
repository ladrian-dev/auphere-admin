import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";

import type { T } from "@/i18n/t";
import { useTheme } from "@/theme/theme";
import { Icon, icons } from "@/ui/icon";
import { EmptyState, ErrorState, OfflineBanner, PartialNotice, Skeleton } from "@/ui/states";
import { Text } from "@/ui/text";

/**
 * The honest states of a Reservas screen (spec 044, R16.1, R18.1;
 * constitution §V): a skeleton the shape of a day while it loads, an error
 * with «Reintentar», what is on screen marked as not updated offline, the part
 * that did not load said once, and — while the API does not exist — «Datos de
 * ejemplo» on every screen that shows them.
 */
export function ReservasBody({
  state,
  offline = false,
  demo,
  offlineSince,
  partial,
  onRetry,
  t,
  children,
}: {
  state: "loading" | "error" | "ready";
  /** No network: with nothing read yet, the reads wait for it — said, not a skeleton forever. */
  offline?: boolean;
  demo: boolean;
  offlineSince: string | null;
  partial: boolean;
  onRetry: () => void;
  t: T;
  children: ReactNode;
}) {
  return (
    <View style={styles.stack}>
      {demo ? <DemoMark t={t} /> : null}
      {offlineSince ? <OfflineBanner since={offlineSince} /> : null}
      {state === "ready" && partial ? <PartialNotice text={t("reservas.partial")} /> : null}
      {state === "loading" && offline ? (
        <EmptyState icon={icons.warning} title={t("reservas.offline.empty")} />
      ) : state === "loading" ? (
        <Skeleton rows={5} label={t("reservas.loading")} />
      ) : state === "error" ? (
        <ErrorState body={t("reservas.error")} onRetry={onRetry} />
      ) : (
        children
      )}
    </View>
  );
}

/**
 * Whether what the queries hold is still the period the person left (they keep
 * it while the next one is read, so the header does not jump): then the
 * content is a skeleton, never the old day passed off as the new one — a
 * false «No hay reservas este día» or Aforo's figures at 0 (gate review).
 */
export function showsOtherPeriod(range: { isPlaceholderData: boolean }, occupancy: { isPlaceholderData: boolean }, needsOccupancy: boolean): boolean {
  return range.isPlaceholderData || (needsOccupancy && occupancy.isPlaceholderData);
}

/** «Datos de ejemplo»: said in words, never only as a colour (R18.1). */
export function DemoMark({ t }: { t: T }) {
  const { colors, radius } = useTheme();
  return (
    <View accessible accessibilityRole="text" style={[styles.demo, { backgroundColor: colors.infoBg, borderRadius: radius.md }]} testID="demo-mark">
      <Icon name={icons.warning} size={16} tone="infoText" />
      <View style={styles.flex}>
        <Text variant="subhead" tone="infoText">
          {t("reservas.demo")}
        </Text>
        <Text variant="caption" tone="infoText">
          {t("reservas.demo.body")}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 12 },
  demo: { flexDirection: "row", alignItems: "flex-start", gap: 8, padding: 10 },
  flex: { flex: 1, minWidth: 0 },
});
