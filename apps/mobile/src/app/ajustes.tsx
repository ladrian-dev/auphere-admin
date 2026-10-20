import { useQueryClient } from "@tanstack/react-query";
import * as WebBrowser from "expo-web-browser";
import { useState } from "react";
import { Alert, Linking, ScrollView, StyleSheet, Switch, View } from "react-native";

import { endpoints, type NoticeKind } from "@/api/endpoints";
import { useMe, useNotices } from "@/api/hooks";
import { keys } from "@/api/query";
import { useSession } from "@/auth/session";
import { APP_VERSION, CONSOLE_URL, VARIANT } from "@/config";
import { versionLabel } from "@/lib/version";
import { kindsFor } from "@/features/notices";
import { useT } from "@/i18n/t";
import { haptics } from "@/motion/haptics";
import { usePush } from "@/push/provider";
import { TOUCH, useTheme } from "@/theme/theme";
import { Divider, RowButton } from "@/ui/bits";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { icons } from "@/ui/icon";
import { useOnline } from "@/ui/online";
import { Text } from "@/ui/text";

/**
 * Ajustes (spec 031, R11): who you are here, this phone's notices, the web
 * console, signing out of this phone and asking for the account's deletion.
 * A notice switch exists only when the system lets notices through (R10.3).
 */
export default function Ajustes() {
  const t = useT();
  const { colors } = useTheme();
  const online = useOnline();
  const me = useMe();
  const { signOut } = useSession();
  const push = usePush();
  const qc = useQueryClient();
  const granted = push.permission === "granted";
  const notices = useNotices(granted);
  const [saveFailed, setSaveFailed] = useState(false);
  const [deletion, setDeletion] = useState<"idle" | "sending" | "sent" | "failed">("idle");
  const kinds = kindsFor(me.data?.nav ?? []);
  const on = new Set<NoticeKind>((notices.data?.kinds ?? []) as NoticeKind[]);

  const toggle = async (kind: NoticeKind, value: boolean) => {
    const next = [...kinds.map((k) => k.kind).filter((k) => (k === kind ? value : on.has(k)))];
    const before = notices.data;
    qc.setQueryData(keys.notices, { kinds: next });
    setSaveFailed(false);
    try {
      qc.setQueryData(keys.notices, await endpoints.setNotices(next));
      haptics.light();
    } catch {
      qc.setQueryData(keys.notices, before);
      setSaveFailed(true);
    }
  };

  const confirmSignOut = () =>
    Alert.alert(t("app.signOut.confirm"), t("app.signOut.body"), [
      { text: t("app.cancel"), style: "cancel" },
      { text: t("app.signOut"), style: "destructive", onPress: () => void signOut() },
    ]);

  const confirmDeletion = () =>
    Alert.alert(t("app.deletion.confirm"), t("app.deletion.body"), [
      { text: t("app.cancel"), style: "cancel" },
      {
        text: t("app.deletion"),
        style: "destructive",
        onPress: () => {
          setDeletion("sending");
          void endpoints
            .requestDeletion()
            .then(() => setDeletion("sent"))
            .catch(() => setDeletion("failed"));
        },
      },
    ]);

  return (
    <ScrollView style={{ backgroundColor: colors.background }} contentContainerStyle={styles.content} contentInsetAdjustmentBehavior="automatic">
      <Card>
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
          {t("app.account")}
        </Text>
        <Text variant="headline">{me.data?.user.name ?? ""}</Text>
        <Text variant="callout" tone="mutedForeground" selectable>
          {me.data?.user.email ?? ""}
        </Text>
        <Divider />
        <Line label={t("app.account.business")} value={me.data?.client.name ?? ""} />
        <Line label={t("app.account.role")} value={t("app.account.role.client")} />
      </Card>

      <Card>
        <Text variant="subhead" tone="mutedForeground" accessibilityRole="header">
          {t("app.notices.section")}
        </Text>
        {granted ? (
          kinds.map((k, i) => (
            <View key={k.kind}>
              {i > 0 ? <Divider /> : null}
              <View style={styles.switchRow}>
                <View style={styles.flex}>
                  <Text variant="body">{t(k.label)}</Text>
                  <Text variant="footnote" tone="mutedForeground">
                    {t(k.hint)}
                  </Text>
                </View>
                <Switch
                  accessibilityLabel={t(k.label)}
                  value={on.has(k.kind)}
                  disabled={!online || !notices.data}
                  onValueChange={(v) => void toggle(k.kind, v)}
                  trackColor={{ true: colors.primary, false: colors.muted }}
                  thumbColor={colors.card}
                  ios_backgroundColor={colors.muted}
                />
              </View>
            </View>
          ))
        ) : push.permission === "denied" ? (
          <>
            <Text variant="callout">{t("app.notices.denied")}</Text>
            <Button label={t("app.notices.denied.open")} variant="secondary" onPress={() => void Linking.openSettings()} />
          </>
        ) : (
          <>
            <Text variant="callout">{t("app.notices.off")}</Text>
            <Button label={t("app.notices.allow")} onPress={() => void push.enable()} />
          </>
        )}
        {saveFailed ? (
          <Text variant="footnote" tone="dangerText" accessibilityRole="alert">
            {t("app.notices.saveFailed")}
          </Text>
        ) : null}
        <Text variant="footnote" tone="mutedForeground">
          {t("app.notices.privacy")}
        </Text>
      </Card>

      <Card>
        <RowButton title={t("app.web")} icon={icons.external} tone="primaryText" onPress={() => void WebBrowser.openBrowserAsync(CONSOLE_URL)} />
      </Card>

      <Card>
        <RowButton title={t("app.signOut")} tone="destructive" chevron={false} onPress={confirmSignOut} />
        <Divider />
        <RowButton
          title={t("app.deletion")}
          tone="destructive"
          chevron={false}
          onPress={confirmDeletion}
          accessibilityHint={t("app.deletion.body")}
        />
        {deletion !== "idle" ? (
          <Text
            variant="footnote"
            tone={deletion === "failed" ? "dangerText" : "mutedForeground"}
            accessibilityRole="alert"
          >
            {deletion === "sending" ? t("app.loading") : deletion === "sent" ? t("app.deletion.sent") : t("app.deletion.failed")}
          </Text>
        ) : null}
      </Card>

      <Text variant="caption" tone="mutedForeground" style={styles.version}>
        {t("app.version", { version: versionLabel(APP_VERSION, VARIANT) })}
      </Text>
    </ScrollView>
  );
}

function Line({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.line} accessible accessibilityLabel={`${label}: ${value}`}>
      <Text variant="callout" tone="mutedForeground">
        {label}
      </Text>
      <Text variant="callout" style={styles.value}>
        {value}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: 16, gap: 16, paddingBottom: 40 },
  switchRow: { flexDirection: "row", alignItems: "center", gap: 12, minHeight: TOUCH, paddingVertical: 8 },
  flex: { flex: 1, minWidth: 0, gap: 2 },
  line: { flexDirection: "row", justifyContent: "space-between", gap: 12, flexWrap: "wrap", minHeight: 32, alignItems: "center" },
  value: { flexShrink: 1, textAlign: "right" },
  version: { textAlign: "center" },
});
