import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import type { T } from "@/i18n/t";
import { useNowMs } from "@/lib/use-now";
import { Button } from "@/ui/button";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import { agoText, waitingReasonText, type ComposerMode } from "../model";

/** How many lines of the agent's reason the foot shows before «Leer más» (R2.3). */
const REASON_LINES = 2;

/**
 * What the foot says when this person does not answer yet (R6.1 of the 031;
 * spec 042 R2.3, R2.4, R2.9; spec 044 R11.1, R11.3). Content only — the
 * surface is `ThreadFoot`'s.
 * Waiting: why, said BEFORE the action, in two lines, with «Leer más» when it
 * does not fit; then «Tomar el control» under the thumb and «Devolver al
 * agente». When the agent or another person answers: who, and the same
 * action. Resolved: it says so, and «Reabrir».
 */
export function ControlCard({
  mode,
  busy,
  online,
  t,
  onTakeOver,
  onGiveBack,
  onReopen,
  onReadMore,
}: {
  mode: Exclude<ComposerMode, { kind: "mine" }>;
  busy: boolean;
  online: boolean;
  t: T;
  onTakeOver: () => void;
  onGiveBack: () => void;
  onReopen: () => void;
  onReadMore?: () => void;
}) {
  const [overflows, setOverflows] = useState(false);
  const now = useNowMs();
  const off = busy || !online;

  if (mode.kind === "resolved") {
    return (
      <View style={styles.stack}>
        <Text variant="callout" tone="mutedForeground">
          {t("inbox.composer.resolved")}
        </Text>
        <Button label={t("inbox.action.reopen")} variant="secondary" full busy={busy} disabled={!online} onPress={onReopen} testID="reopen" />
      </View>
    );
  }

  if (mode.kind === "waiting") {
    // Spec 047 (50.7): why it waits, by its code («Agente en pausa»); the agent's own words under it. With a
    // code and no words, the code says it — never «El agente no dijo por qué» for a pause.
    const why = waitingReasonText(mode.code, t);
    const reason = mode.reason ?? (why ? null : t("inbox.composer.waiting.noReason"));
    return (
      <View style={styles.stack} testID="waiting-card">
        <View style={styles.head}>
          <Icon name={icons.hand} size={18} tone="warningText" />
          <Text variant="bodyStrong" style={styles.flex} accessibilityRole="header">
            {t("inbox.composer.waiting.title")}
          </Text>
        </View>
        {mode.since ? (
          // Spec 044, R11.1: since when, and who asked — before the action.
          <Text variant="footnote" tone="warningText">
            {mode.agent
              ? t("app.inbox.waitingSince", { time: agoText(mode.since, now, t), agent: mode.agent })
              : t("app.inbox.waitingSince.noAgent", { time: agoText(mode.since, now, t) })}
          </Text>
        ) : null}
        {why ? (
          <Text variant="subhead" tone="warningText" testID="waiting-code">
            {why}
          </Text>
        ) : null}
        {reason ? (
          <>
            <Text variant="callout" numberOfLines={REASON_LINES} testID="waiting-reason">
              {reason}
            </Text>
            {/* The same words laid out without a limit, only to know whether they fit; nobody sees or hears them. */}
            <Text
              variant="callout"
              accessible={false}
              importantForAccessibility="no-hide-descendants"
              pointerEvents="none"
              style={styles.measure}
              testID="waiting-reason-measure"
              onTextLayout={(e) => setOverflows(e.nativeEvent.lines.length > REASON_LINES)}
            >
              {reason}
            </Text>
          </>
        ) : null}
        {reason && overflows && onReadMore ? (
          <Pressable accessibilityRole="button" onPress={onReadMore} hitSlop={8} style={styles.more}>
            <Text variant="subhead" tone="primaryText">
              {t("app.inbox.readMore")}
            </Text>
          </Pressable>
        ) : null}
        <Button label={t("inbox.composer.takeover")} full busy={busy} disabled={!online} onPress={onTakeOver} testID="take-over" />
        <Button label={t("inbox.composer.giveBack")} variant="ghost" full disabled={off} onPress={onGiveBack} />
      </View>
    );
  }

  return (
    <View style={styles.stack}>
      <View style={styles.head}>
        <Icon name={icons.bot} size={18} tone="primaryText" />
        <Text variant="callout" tone="mutedForeground" style={styles.flex}>
          {mode.kind === "agent"
            ? mode.agent
              ? t("app.inbox.agentAnswers", { agent: mode.agent })
              : t("app.inbox.agentAnswers.noAgent")
            : t("inbox.composer.other", { name: mode.name ?? t("inbox.who.someone") })}
        </Text>
      </View>
      <Button label={t("inbox.composer.takeover")} variant="secondary" full busy={busy} disabled={!online} onPress={onTakeOver} testID="take-over" />
    </View>
  );
}

const styles = StyleSheet.create({
  stack: { padding: 16, gap: 10 },
  head: { flexDirection: "row", alignItems: "center", gap: 8 },
  flex: { flex: 1, minWidth: 0 },
  measure: { position: "absolute", left: 16, right: 16, top: 0, opacity: 0 },
  more: { alignSelf: "flex-start", minHeight: 32, justifyContent: "center" },
});
