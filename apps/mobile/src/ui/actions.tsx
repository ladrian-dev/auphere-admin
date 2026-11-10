import { createContext, use, useCallback, useState, type ReactNode } from "react";
import { ActionSheetIOS, Modal, Platform, Pressable, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useT } from "@/i18n/t";
import { SHEET_RADIUS, TOUCH, useTheme } from "@/theme/theme";

import { Text } from "./text";

/**
 * A menu of actions in each platform's own shape (R14.8): the iOS action
 * sheet, and a bottom sheet on Android. Each action is a plain button — no
 * gesture is the only way to do anything (R14.5).
 */
export type Action = { label: string; onPress: () => void; destructive?: boolean; disabled?: boolean };
type Show = (title: string | undefined, actions: Action[]) => void;

const Ctx = createContext<Show | null>(null);

export function ActionsProvider({ children }: { children: ReactNode }) {
  const t = useT();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [sheet, setSheet] = useState<{ title?: string; actions: Action[] } | null>(null);

  const show = useCallback<Show>(
    (title, actions) => {
      const usable = actions.filter((a) => !a.disabled);
      if (Platform.OS === "ios") {
        const destructive = usable.map((a, i) => (a.destructive ? i : -1)).filter((i) => i >= 0);
        ActionSheetIOS.showActionSheetWithOptions(
          {
            title,
            options: [...usable.map((a) => a.label), t("app.cancel")],
            cancelButtonIndex: usable.length,
            destructiveButtonIndex: destructive,
          },
          (i) => usable[i]?.onPress(),
        );
        return;
      }
      setSheet({ title, actions: usable });
    },
    [t],
  );

  const close = () => setSheet(null);
  return (
    <Ctx value={show}>
      {children}
      {Platform.OS !== "ios" ? (
        <Modal visible={sheet !== null} transparent animationType="slide" onRequestClose={close} statusBarTranslucent navigationBarTranslucent>
          <Pressable accessibilityLabel={t("app.close")} style={[styles.scrim, { backgroundColor: colors.scrim }]} onPress={close} />
          <View
            accessibilityViewIsModal
            style={[styles.sheet, { backgroundColor: colors.card, borderTopLeftRadius: SHEET_RADIUS, borderTopRightRadius: SHEET_RADIUS, paddingBottom: insets.bottom + 8 }]}
          >
            {sheet?.title ? (
              <Text variant="subhead" tone="mutedForeground" style={styles.title} accessibilityRole="header">
                {sheet.title}
              </Text>
            ) : null}
            {sheet?.actions.map((a) => (
              <Pressable
                key={a.label}
                accessibilityRole="button"
                onPress={() => {
                  close();
                  a.onPress();
                }}
                android_ripple={{ color: colors.muted }}
                style={({ pressed }) => [styles.item, pressed ? { backgroundColor: colors.muted } : null]}
              >
                <Text variant="body" tone={a.destructive ? "destructive" : "foreground"}>
                  {a.label}
                </Text>
              </Pressable>
            ))}
            <Pressable
              accessibilityRole="button"
              onPress={close}
              android_ripple={{ color: colors.muted }}
              style={({ pressed }) => [styles.item, pressed ? { backgroundColor: colors.muted } : null]}
            >
              <Text variant="bodyStrong" tone="mutedForeground">
                {t("app.cancel")}
              </Text>
            </Pressable>
          </View>
        </Modal>
      ) : null}
    </Ctx>
  );
}

export function useActions(): Show {
  const show = use(Ctx);
  if (!show) throw new Error("useActions outside ActionsProvider");
  return show;
}

const styles = StyleSheet.create({
  scrim: { flex: 1 },
  sheet: { paddingTop: 8, paddingHorizontal: 8 },
  title: { paddingHorizontal: 16, paddingVertical: 12 },
  item: { minHeight: TOUCH + 4, justifyContent: "center", paddingHorizontal: 16 },
});
