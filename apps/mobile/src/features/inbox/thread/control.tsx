import { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";

import { useLocale, type T } from "@/i18n/t";
import { useNowMs } from "@/lib/use-now";
import { Button } from "@/ui/button";
import { Icon, icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import { agoText, reasonText, waitingReasonText, type ComposerMode } from "../model";

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
  contactName,
}: {
  mode: Exclude<ComposerMode, { kind: "mine" }>;
  busy: boolean;
  online: boolean;
  t: T;
  onTakeOver: () => void;
  onGiveBack: () => void;
  onReopen: () => void;
  onReadMore?: () => void;
  /** Spec 069 (R11.2): who waits, so the action says «Atender a {nombre}» (their first name). */
  contactName?: string | null;
}) {
  const [overflows, setOverflows] = useState(false);
  const now = useNowMs();
  const locale = useLocale();
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
    // Spec 056 (7.1): the words under it go through the table too, and are not said twice.
    const said = mode.reason ? reasonText(mode.reason, t) : null;
    const reason = said ? (said === why ? null : said) : why ? null : t("inbox.composer.waiting.noReason");
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
        <Button
          label={firstName(contactName) ? t("v13.conv.attend", { name: firstName(contactName) as string }) : t("inbox.composer.takeover")}
          icon={icons.hand}
          full
          busy={busy}
          disabled={!online}
          onPress={onTakeOver}
          testID="take-over"
        />
        <Button label={t("inbox.composer.giveBack")} variant="ghost" full disabled={off} onPress={onGiveBack} />
      </View>
    );
  }

  // Spec 069 (R11.5): once the agent can no longer answer, the strip says until when a person can — never «Responde …».
  const expired = mode.kind === "agent" && (mode.windowClosed || mode.personUntil);
  const line =
    mode.kind === "agent"
      ? mode.personUntil
        ? mode.agent
          ? t("v13.conv.window.personOnly", { agent: mode.agent, until: untilLabel(mode.personUntil, locale) })
          : t("inbox.composer.agent_person_only", { until: untilLabel(mode.personUntil, locale) })
        : mode.windowClosed
          ? // Named as the header names it (review H23); the console's words without a name.
            mode.agent
            ? t("v13.conv.window.closed", { agent: mode.agent })
            : t("inbox.composer.agent_window_closed")
          : mode.agent
            ? t("app.inbox.agentAnswers", { agent: mode.agent })
            : t("app.inbox.agentAnswers.noAgent")
      : t("inbox.composer.other", { name: mode.name ?? t("inbox.who.someone") });
  return (
    <View style={styles.stack}>
      <View style={styles.head}>
        <Icon name={expired ? icons.clock : icons.bot} size={20} tone={expired ? "warningText" : "highlightInk"} />
        <Text variant="callout" tone={expired ? "foreground" : "mutedForeground"} style={styles.flex} testID={expired ? "agent-window" : undefined}>
          {line}
        </Text>
      </View>
      <Button label={t("inbox.composer.takeover")} icon={icons.hand} full busy={busy} disabled={!online} onPress={onTakeOver} testID="take-over" />
    </View>
  );
}

/** The first word of a contact's name that is a word (not a number): «Atender a Lucía». */
export function firstName(name: string | null | undefined): string | null {
  const word = (name ?? "").split(/\s+/).find((p) => /^\p{L}/u.test(p));
  return word ?? null;
}

/** «el jueves 27 de noviembre, 10:00»: until when a person can still answer (the console's `untilLabel`). */
export function untilLabel(at: string, locale: string): string {
  return new Date(at).toLocaleString(locale, { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
}

const styles = StyleSheet.create({
  stack: { padding: 16, gap: 10 },
  head: { flexDirection: "row", alignItems: "center", gap: 8 },
  flex: { flex: 1, minWidth: 0 },
  measure: { position: "absolute", left: 16, right: 16, top: 0, opacity: 0 },
  more: { alignSelf: "flex-start", minHeight: 32, justifyContent: "center" },
});
