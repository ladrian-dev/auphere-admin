import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";

import type { Correction, CorrectionScope } from "@/api/endpoints";
import { ApiError } from "@/api/errors";
import type { MessageKey, T } from "@/i18n/t";
import { useTheme } from "@/theme/theme";
import { Segmented } from "@/ui/bits";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Field } from "@/ui/field";
import { icons } from "@/ui/icon";
import { Text } from "@/ui/text";

import { Notice } from "../business/parts";

/**
 * «Corregir esta respuesta» (spec 047, T176; requirement 52). Three steps on
 * one sheet:
 *
 * 1. **Write** how it should have answered (or the rule) and for whom: the
 *    whole business or only this agent (52.1).
 * 2. **Review**, before anything is saved: whether it is a fact or a
 *    behaviour, and what each means (52.2); the lesson and the paraphrase of
 *    what the customer asked, both editable (52.4); and, if either holds a
 *    customer's personal data, which and where — sending waits until it is
 *    gone (52.5).
 * 3. **Sent**: a fact applies now and can be undone; a behaviour reached the
 *    partner as a proposal.
 */
export type Step = "write" | "review" | "sent" | "undone";

export type PiiItem = { field: "lesson" | "paraphrase"; kind: "email" | "document" | "phone" | "name"; text: string };

/**
 * Where the API found personal data, with the words themselves (they are on
 * this person's phone already). Offsets are the API's, on the texts it has:
 * once the person edits a field they no longer match, and the item says only
 * what and where until the next check.
 */
export function piiItems(c: Pick<Correction, "pii" | "lesson" | "paraphrase">, edited: { lesson: boolean; paraphrase: boolean }): PiiItem[] {
  return c.pii.map((p) => {
    const source = p.field === "lesson" ? c.lesson : (c.paraphrase ?? "");
    const stale = edited[p.field];
    return { field: p.field, kind: p.kind, text: stale ? "" : source.slice(p.start, p.end) };
  });
}

/** A refusal of a correction, in words. `pii_present` is not here: it is shown as the list of what to remove. */
export function correctionErrorText(e: unknown, t: T): string {
  if (e instanceof ApiError) {
    if (e.offline) return t("corregir.offline");
    switch (e.code) {
      case "not_an_agent_reply":
      case "no_agent":
      case "paraphrase_required":
      case "rule_too_long":
      case "not_a_draft":
      case "revision_conflict":
        return t(`corregir.error.${e.code}` as MessageKey);
      case "lesson_too_long":
        return t("corregir.error.lesson_too_long", { max: typeof e.info.max === "number" ? e.info.max : 2000 });
    }
  }
  return t("corregir.error.generic");
}

export function CorrectionForm({
  step,
  answer,
  agentName,
  partner,
  text,
  scope,
  onText,
  onScope,
  correction,
  lesson,
  paraphrase,
  onLesson,
  onParaphrase,
  online,
  busy,
  error,
  onNext,
  onSend,
  onUndo,
  onDone,
  t,
}: {
  step: Step;
  /** The agent's answer being corrected, quoted; `null` when the thread is not loaded. */
  answer: string | null;
  agentName: string | null;
  partner: string;
  text: string;
  scope: CorrectionScope;
  onText: (v: string) => void;
  onScope: (s: CorrectionScope) => void;
  correction: Correction | null;
  lesson: string;
  paraphrase: string;
  onLesson: (v: string) => void;
  onParaphrase: (v: string) => void;
  online: boolean;
  busy: boolean;
  error: string | null;
  onNext: () => void;
  onSend: () => void;
  onUndo: () => void;
  onDone: () => void;
  t: T;
}) {
  const { colors, radius } = useTheme();
  const agent = correction?.agent.name ?? agentName;
  const problems = (
    <>
      {!online ? <Notice tone="warning" icon={icons.offline} text={t("corregir.offline")} /> : null}
      {online && error ? <Notice tone="danger" icon={icons.warning} text={error} /> : null}
    </>
  );

  return (
    <View style={styles.stack}>
      <Text variant="title" accessibilityRole="header">
        {t("corregir.title")}
      </Text>
      {answer ? (
        <View style={[styles.quote, { borderLeftColor: colors.positive, backgroundColor: colors.muted, borderRadius: radius.md }]} accessible>
          <Text variant="footnote" tone="mutedForeground">
            {agent ? t("corregir.answer", { agent }) : t("corregir.answer.agent")}
          </Text>
          <Text variant="callout" numberOfLines={6}>
            {answer}
          </Text>
        </View>
      ) : null}

      {step === "write" ? (
        <>
          <Field label={t("corregir.text")} value={text} onChangeText={onText} multiline maxLength={2000} autoFocus textAlignVertical="top" style={styles.area} />
          <Text variant="footnote" tone="mutedForeground">
            {t("corregir.text.hint")}
          </Text>
          <View style={styles.group}>
            <Text variant="subhead">{t("corregir.scope")}</Text>
            <Segmented
              label={t("corregir.scope")}
              value={scope}
              onChange={onScope}
              options={[
                { value: "business", label: t("corregir.scope.business") },
                { value: "agent", label: t("corregir.scope.agent") },
              ]}
            />
          </View>
          {problems}
          <Button label={t("corregir.next")} full busy={busy} disabled={!online || !text.trim()} onPress={onNext} />
        </>
      ) : null}

      {step === "review" && correction ? (
        <ReviewStep
          correction={correction}
          agent={agent}
          partner={partner}
          lesson={lesson}
          paraphrase={paraphrase}
          onLesson={onLesson}
          onParaphrase={onParaphrase}
          online={online}
          busy={busy}
          problems={problems}
          onSend={onSend}
          t={t}
        />
      ) : null}

      {(step === "sent" || step === "undone") && correction ? (
        <>
          <Card tone={step === "undone" ? undefined : "positive"} testID="correction-sent">
            <Text variant="body" accessibilityRole="alert">
              {step === "undone"
                ? t("corregir.undone", { agent: agent ?? "" })
                : correction.kind === "data"
                  ? t("corregir.sent.data", { agent: agent ?? "" })
                  : t("corregir.sent.behavior", { partner, agent: agent ?? "" })}
            </Text>
          </Card>
          {problems}
          {step === "sent" && correction.kind === "data" ? (
            <Button label={t("corregir.undo")} icon={icons.giveBack} variant="secondary" full busy={busy} disabled={!online} onPress={onUndo} />
          ) : null}
          <Button label={t("corregir.done")} full onPress={onDone} disabled={busy} />
        </>
      ) : null}
    </View>
  );
}

function ReviewStep({
  correction,
  agent,
  partner,
  lesson,
  paraphrase,
  onLesson,
  onParaphrase,
  online,
  busy,
  problems,
  onSend,
  t,
}: {
  correction: Correction;
  agent: string | null;
  partner: string;
  lesson: string;
  paraphrase: string;
  onLesson: (v: string) => void;
  onParaphrase: (v: string) => void;
  online: boolean;
  busy: boolean;
  problems: ReactNode;
  onSend: () => void;
  t: T;
}) {
  const edited = { lesson: lesson !== correction.lesson, paraphrase: paraphrase !== (correction.paraphrase ?? "") };
  const items = piiItems(correction, edited);
  // Personal data blocks sending until a field that holds it is edited; the edit is checked again on sending (52.5).
  const blocked = items.some((p) => !edited[p.field]);
  const data = correction.kind === "data";
  const where = correction.scope === "business" ? t("corregir.kind.data.scope.business") : t("corregir.kind.data.scope.agent", { agent: agent ?? "" });
  return (
    <>
      <Card testID={`correction-kind-${correction.kind}`}>
        <Text variant="headline" accessibilityRole="header">
          {data ? t("corregir.kind.data") : t("corregir.kind.behavior")}
        </Text>
        <Text variant="callout" tone="mutedForeground">
          {data ? t("corregir.kind.data.body", { scope: where }) : t("corregir.kind.behavior.body", { partner })}
        </Text>
      </Card>
      <Field label={t("corregir.lesson")} value={lesson} onChangeText={onLesson} multiline maxLength={2000} textAlignVertical="top" style={styles.area} />
      <View style={styles.group}>
        <Field label={t("corregir.paraphrase")} value={paraphrase} onChangeText={onParaphrase} multiline maxLength={300} textAlignVertical="top" />
        <Text variant="footnote" tone="mutedForeground">
          {t("corregir.paraphrase.hint", { partner })}
        </Text>
      </View>
      {items.length > 0 ? (
        <Card tone="danger" testID="correction-pii">
          <Text variant="headline" accessibilityRole="header">
            {t("corregir.pii.title")}
          </Text>
          {items.map((p, i) => (
            <Text key={i} variant="callout" accessibilityRole="text">
              {`• ${t("corregir.pii.item", {
                kind: t(`corregir.pii.kind.${p.kind}` as MessageKey),
                field: p.field === "lesson" ? t("corregir.lesson") : t("corregir.paraphrase"),
                text: p.text || "…",
              })}`}
            </Text>
          ))}
          {edited.lesson || edited.paraphrase ? (
            <Text variant="footnote" tone="mutedForeground">
              {t("corregir.pii.edited")}
            </Text>
          ) : null}
        </Card>
      ) : null}
      {problems}
      <Button label={t("corregir.send")} full busy={busy} disabled={!online || blocked || !lesson.trim()} onPress={onSend} />
    </>
  );
}

const styles = StyleSheet.create({
  stack: { gap: 16 },
  group: { gap: 8 },
  quote: { borderLeftWidth: 3, paddingHorizontal: 12, paddingVertical: 10, gap: 4 },
  area: { minHeight: 96 },
});
