import type { ReactNode } from "react";
import { RefreshControl, ScrollView, StyleSheet, View } from "react-native";

import { useTheme } from "@/theme/theme";

/**
 * A scrolling screen under the native header: `automatic` insets let the iOS
 * large title collapse as it scrolls; pull to refresh re-reads (R14.1).
 */
export function ScrollScreen({
  children,
  refreshing = false,
  onRefresh,
  testID,
}: {
  children: ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
  testID?: string;
}) {
  const { colors } = useTheme();
  return (
    <ScrollView
      testID={testID}
      style={{ backgroundColor: colors.background }}
      contentInsetAdjustmentBehavior="automatic"
      contentContainerStyle={styles.content}
      refreshControl={
        onRefresh ? (
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primaryText} colors={[colors.primaryDeep]} />
        ) : undefined
      }
    >
      {children}
    </ScrollView>
  );
}

/** A plain full-screen container with the theme's background. */
export function Plain({ children }: { children: ReactNode }) {
  const { colors } = useTheme();
  return <View style={[styles.plain, { backgroundColor: colors.background }]}>{children}</View>;
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 16, paddingBottom: 32 },
  plain: { flex: 1 },
});
