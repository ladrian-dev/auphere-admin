import type { UseQueryResult } from "@tanstack/react-query";
import { StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import type { Me } from "@/api/endpoints";
import { ApiError } from "@/api/errors";
import { useSession } from "@/auth/session";
import { useT } from "@/i18n/t";
import { useTheme } from "@/theme/theme";
import { Button } from "@/ui/button";
import { icons } from "@/ui/icon";
import { EmptyState, ErrorState, Skeleton } from "@/ui/states";

/**
 * What the signed-in app shows before it knows the client's modules (`/me`):
 * loading, the read failing (with retry), or no access at all — a 403 on
 * `/me`, or a client whose modules this app cannot show (R1.5, R3.7).
 */
export function MeGateState({ query }: { query: UseQueryResult<Me> }) {
  const t = useT();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const { signOut } = useSession();
  const forbidden = query.error instanceof ApiError && query.error.status === 403;
  const noModules = query.data !== undefined;
  return (
    <View style={[styles.fill, { backgroundColor: colors.background, paddingTop: insets.top + 24, paddingBottom: insets.bottom }]}>
      {forbidden || noModules ? (
        <>
          <EmptyState icon={icons.warning} title={t("app.noAccess.title")} body={t("app.noAccess.body")} />
          <View style={styles.actions}>
            <Button label={t("app.signOut")} variant="secondary" onPress={() => void signOut()} />
          </View>
        </>
      ) : query.isError ? (
        <ErrorState onRetry={() => void query.refetch()} />
      ) : (
        <View style={styles.pad}>
          <Skeleton rows={3} />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
  pad: { padding: 16 },
  actions: { alignItems: "center" },
});
