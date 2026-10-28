import { useQueryClient } from "@tanstack/react-query";
import * as Crypto from "expo-crypto";
import { router, useLocalSearchParams } from "expo-router";
import { useMemo, useRef, useState } from "react";
import { StyleSheet } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";

import { endpoints, type Correction, type CorrectionScope } from "@/api/endpoints";
import { ApiError } from "@/api/errors";
import { useConversation, useMe, useThread } from "@/api/hooks";
import { keys } from "@/api/query";
import { correctionErrorText, CorrectionForm, type Step } from "@/features/inbox/correction";
import { useT } from "@/i18n/t";
import { partnerOf } from "@/lib/agents-model";
import { useDraft } from "@/lib/drafts";
import { haptics } from "@/motion/haptics";
import { glassAvailable } from "@/theme/glass";
import { useTheme } from "@/theme/theme";
import { useOnline } from "@/ui/online";

/**
 * «Corregir esta respuesta», as a sheet over the conversation (spec 047,
 * T176; requirement 52). The params are the conversation and the agent's
 * message. What is typed is a draft in memory (50.5): without a connection
 * nothing is sent, and closing the sheet and coming back finds it. The
 * draft's key is fixed for what was typed, so a retry of the same thing is
 * the same draft on the API (`Idempotency-Key`).
 */
type Typed = { text: string; scope: CorrectionScope; key?: string };

export default function CorregirRoute() {
  const { id, message } = useLocalSearchParams<{ id: string; message: string }>();
  const t = useT();
  const online = useOnline();
  const { colors } = useTheme();
  const qc = useQueryClient();
  const me = useMe();
  const detail = useConversation(id);
  const thread = useThread(id);
  const [typed, setTyped] = useDraft<Typed>(`corregir.${message}`);
  const text = typed?.text ?? "";
  const scope = typed?.scope ?? "business";
  const [step, setStep] = useState<Step>("write");
  const [correction, setCorrection] = useState<Correction | null>(null);
  const [lesson, setLesson] = useState("");
  const [paraphrase, setParaphrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sendKey = useRef<string | null>(null);

  const answer = useMemo(() => {
    for (const page of thread.data?.pages ?? []) {
      const hit = page.items.find((i) => i.id === message);
      if (hit) return hit.text ?? null;
    }
    return null;
  }, [thread.data, message]);
  const agentName = detail.data?.handled_by_agent?.name ?? detail.data?.agent?.name ?? null;
  const partner = partnerOf(me.data?.balance_contact);

  const take = (c: Correction) => {
    setCorrection(c);
    setLesson(c.lesson);
    setParaphrase(c.paraphrase ?? "");
  };

  const next = async () => {
    if (!online) return setError(t("corregir.offline"));
    // One key per thing typed, kept with it: reopening the sheet and continuing again is the same draft.
    const key = typed?.key ?? Crypto.randomUUID();
    if (!typed?.key) setTyped({ text, scope, key });
    setBusy(true);
    setError(null);
    try {
      take(await endpoints.draftCorrection(id, message, { text: text.trim(), scope }, key));
      setStep("review");
    } catch (e) {
      haptics.warning();
      setError(correctionErrorText(e, t));
    } finally {
      setBusy(false);
    }
  };

  const send = async () => {
    if (!correction) return;
    if (!online) return setError(t("corregir.offline"));
    setBusy(true);
    setError(null);
    try {
      let current = correction;
      const edits: { lesson?: string; paraphrase?: string } = {};
      if (lesson !== current.lesson) edits.lesson = lesson.trim();
      if (paraphrase !== (current.paraphrase ?? "")) edits.paraphrase = paraphrase.trim();
      if (Object.keys(edits).length > 0) {
        // The edit is checked again by the API: personal data still there stops it here, nothing saved (52.5).
        current = await endpoints.editCorrection(current.id, edits, current.revision);
        take(current);
        if (current.pii.length > 0) {
          haptics.warning();
          return;
        }
      }
      sendKey.current ??= Crypto.randomUUID();
      const sent = await endpoints.sendCorrection(current.id, current.revision, sendKey.current);
      setCorrection(sent);
      setTyped(null);
      setStep("sent");
      haptics.success();
      // A fact lands in the business's profile or knowledge at once: Negocio reads it again.
      if (sent.kind === "data") void qc.invalidateQueries({ queryKey: keys.business });
    } catch (e) {
      haptics.warning();
      if (e instanceof ApiError && e.code === "pii_present" && Array.isArray(e.info.pii)) {
        setCorrection((c) => (c ? { ...c, pii: e.info.pii as Correction["pii"] } : c));
      } else if (e instanceof ApiError && e.code === "revision_conflict" && e.info.current) {
        take(e.info.current as Correction);
        setError(correctionErrorText(e, t));
      } else setError(correctionErrorText(e, t));
    } finally {
      setBusy(false);
    }
  };

  const undo = async () => {
    if (!correction) return;
    setBusy(true);
    setError(null);
    try {
      setCorrection(await endpoints.undoCorrection(correction.id, Crypto.randomUUID()));
      setStep("undone");
      haptics.success();
      void qc.invalidateQueries({ queryKey: keys.business });
    } catch (e) {
      haptics.warning();
      setError(e instanceof ApiError && e.offline ? t("corregir.offline") : t("corregir.error.undo"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <KeyboardAwareScrollView
      testID="corregir"
      style={glassAvailable() ? undefined : { backgroundColor: colors.background }}
      contentContainerStyle={styles.content}
      contentInsetAdjustmentBehavior="automatic"
      keyboardShouldPersistTaps="handled"
      bottomOffset={24}
    >
      <CorrectionForm
        step={step}
        answer={answer}
        agentName={agentName}
        partner={partner}
        text={text}
        scope={scope}
        onText={(v) => {
          setTyped({ text: v, scope });
          setError(null);
        }}
        onScope={(s) => setTyped({ text, scope: s })}
        correction={correction}
        lesson={lesson}
        paraphrase={paraphrase}
        onLesson={(v) => {
          setLesson(v);
          setError(null);
        }}
        onParaphrase={(v) => {
          setParaphrase(v);
          setError(null);
        }}
        online={online}
        busy={busy}
        error={error}
        onNext={() => void next()}
        onSend={() => void send()}
        onUndo={() => void undo()}
        onDone={() => router.back()}
        t={t}
      />
    </KeyboardAwareScrollView>
  );
}

const styles = StyleSheet.create({
  content: { padding: 20, paddingTop: 28, paddingBottom: 48 },
});
