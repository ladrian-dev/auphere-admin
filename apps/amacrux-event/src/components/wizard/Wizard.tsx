"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";

import { LeadSection } from "@/components/lead/LeadSection";
import { ResultView } from "@/components/result/ResultView";
import { Dialog } from "@/components/ui/Dialog";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { Toast } from "@/components/ui/Toast";
import { RefreshIcon } from "@/components/ui/icons";
import { ALL_QUESTIONS, questionById, questionIndex, remainingSeconds } from "@/domain/questions";
import type { Answers } from "@/domain/types";
import { AnswersSchema } from "@/domain/validation";
import { track } from "@/lib/analytics";
import { readCampaign } from "@/lib/campaign";
import type { LeadRepository } from "@/lib/leads/repository";
import { rulesProvider, validateResult, type RecommendationProvider } from "@/lib/recommendation-provider";
import { clearSession, loadSession, saveSession } from "@/lib/storage";

import { ErrorPanel } from "./ErrorPanel";
import { ProcessingScreen } from "./ProcessingScreen";
import { StepNav } from "./StepNav";
import { StepQuestion } from "./StepQuestion";
import { initialState, isQuestionStep, isScreenComplete, progressFor, toStoredSession, wizardReducer } from "./wizard-reducer";

export interface WizardProps {
  processingMs?: number;
  autoAdvanceMs?: number;
  provider?: RecommendationProvider;
  leadRepository?: LeadRepository;
}

const GENERIC_ERROR = "No hemos podido generar tu resultado. Tus respuestas están a salvo: puedes reintentar o empezar de nuevo.";

export function Wizard({ processingMs = 1400, autoAdvanceMs = 220, provider = rulesProvider, leadRepository }: WizardProps) {
  const router = useRouter();
  const [state, dispatch] = useReducer(wizardReducer, 0, initialState);
  const [confirmRestart, setConfirmRestart] = useState(false);
  const generationRef = useRef(0);

  // Hidratación desde sessionStorage (una vez).
  useEffect(() => {
    const loaded = loadSession();
    if (loaded.status === "restored") dispatch({ type: "hydrate", session: loaded.session });
    if (loaded.status === "discarded") dispatch({ type: "notice", message: "No pudimos recuperar tu sesión anterior, así que empezamos de cero." });
    dispatch({ type: "hydrated", now: Date.now() });
  }, []);

  // Persistencia en cada cambio relevante (nunca el lead ni el resultado).
  useEffect(() => {
    if (!state.hydrated) return;
    // Un estado vacío en la primera pantalla no merece guardarse (y así "Reiniciar" deja el storage limpio).
    if (state.step === "profile" && Object.keys(state.answers).length === 0) {
      clearSession();
      return;
    }
    saveSession(toStoredSession(state));
  }, [state]);

  const campaign = readCampaign();

  // El resultado se calcula ya en el formulario (para adjuntarlo al contacto) y se muestra tras el procesamiento.
  const needsResult = state.hydrated && !state.result && !state.error && (state.step === "lead" || state.step === "processing" || state.step === "result");
  useEffect(() => {
    if (!needsResult) return;
    const parsed = AnswersSchema.safeParse({ ...state.answers, ...(campaign ? { campaign } : {}) });
    if (!parsed.success) {
      dispatch({ type: "fail", message: "Faltan respuestas para calcular el resultado. Vuelve atrás y revisa las pantallas." });
      return;
    }
    const answers: Answers = parsed.data;
    const id = ++generationRef.current;
    const startedAt = Date.now();
    (async () => {
      try {
        const result = await provider.recommend(answers);
        const check = validateResult(result, answers);
        if (!check.ok) throw new Error(check.violations.join("; "));
        if (id !== generationRef.current) return;
        dispatch({ type: "resultReady", result });
        track("assessment_completed", { profileCategory: result.segment.profile, maturityLevel: result.segment.maturity, intentLevel: result.segment.intent, campaign });
        void startedAt;
      } catch {
        if (id !== generationRef.current) return;
        dispatch({ type: "fail", message: GENERIC_ERROR });
        track("error_shown", { step: state.step, campaign });
      }
    })();
  }, [needsResult, provider, processingMs, state.answers, state.step, campaign]);

  // Pantalla de procesamiento: dura processingMs y pasa al resultado cuando este ya está calculado.
  useEffect(() => {
    if (state.step !== "processing" || !state.result) return;
    const t = window.setTimeout(() => dispatch({ type: "processed" }), processingMs);
    return () => window.clearTimeout(t);
  }, [state.step, state.result, processingMs]);

  const restart = useCallback(() => {
    clearSession();
    dispatch({ type: "restart", now: Date.now() });
    track("assessment_restarted", { step: state.step, campaign });
    setConfirmRestart(false);
    router.push("/");
  }, [router, state.step, campaign]);

  const advanceTimer = useRef<number | null>(null);
  const onNext = useCallback(() => {
    if (advanceTimer.current) {
      window.clearTimeout(advanceTimer.current);
      advanceTimer.current = null;
    }
    if (isQuestionStep(state.step)) track("question_answered", { step: state.step, campaign });
    dispatch({ type: "next" });
    window.scrollTo({ top: 0 });
  }, [state.step, campaign]);
  useEffect(() => () => {
    if (advanceTimer.current) window.clearTimeout(advanceTimer.current);
  }, []);

  const question = isQuestionStep(state.step) ? questionById(state.step) : undefined;
  const progress = progressFor(state.step);
  const minutesLeft = question ? Math.max(1, Math.ceil(remainingSeconds(question.id) / 60)) : 0;

  const onAnswer = (value: string | string[]) => {
    if (!question) return;
    const changed = state.answers[question.id] !== value;
    dispatch({ type: "answer", questionId: question.id, value });
    // Avance automático solo en respuesta única y solo si cambió la respuesta.
    if (question.type !== "multi" && changed && typeof value === "string" && value.length > 0) {
      if (advanceTimer.current) window.clearTimeout(advanceTimer.current);
      advanceTimer.current = window.setTimeout(() => {
        advanceTimer.current = null;
        track("question_answered", { step: question.id, campaign });
        dispatch({ type: "next" });
        window.scrollTo({ top: 0 });
      }, autoAdvanceMs);
    }
  };

  const header = (
    <div className="mb-5 flex items-center gap-3">
      <div className="flex-1">
        <ProgressBar value={progress} label={question ? `Pregunta ${questionIndex(question.id) + 1} de ${ALL_QUESTIONS.length}` : "Tu resultado"} detail={question ? `≈ ${minutesLeft} min` : undefined} />
      </div>
      <button
        type="button"
        onClick={() => setConfirmRestart(true)}
        aria-label="Reiniciar"
        title="Reiniciar"
        className="inline-flex size-11 shrink-0 items-center justify-center rounded-full border border-line bg-surface/70 text-ink transition-colors duration-(--duration-fast) hover:bg-surface"
      >
        <RefreshIcon size={20} />
      </button>
    </div>
  );

  let body: React.ReactNode = null;
  if (!state.hydrated) {
    body = <div className="h-40" aria-busy />;
  } else if (state.error) {
    body = <ErrorPanel message={state.error} onRetry={() => dispatch({ type: "clearError" })} onRestart={restart} />;
  } else if (question) {
    const isLast = questionIndex(question.id) === ALL_QUESTIONS.length - 1;
    body = (
      <div key={question.id} className="fade-up">
        <p className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-accent-deep">{question.eyebrow}</p>
        <StepQuestion question={question} value={state.answers[question.id]} onChange={onAnswer} />
        <StepNav
          canBack={questionIndex(question.id) > 0}
          canNext={isScreenComplete(question.id, state.answers)}
          isLast={isLast}
          autoAdvances={question.type !== "multi"}
          onBack={() => dispatch({ type: "back" })}
          onNext={onNext}
        />
      </div>
    );
  } else if (!state.result || state.step === "processing") {
    body = <ProcessingScreen />;
  } else if (state.step === "lead") {
    body = (
      <LeadSection
        result={state.result}
        answers={state.answers}
        campaign={campaign}
        repository={leadRepository}
        onSubmitted={(d) => {
          dispatch({ type: "submitted", delivered: d });
          window.scrollTo({ top: 0 });
        }}
        onBack={() => dispatch({ type: "back" })}
      />
    );
  } else if (state.step === "result") {
    body = <ResultView result={state.result} delivered={state.delivered} campaign={campaign} onBack={() => dispatch({ type: "back" })} onRestart={() => setConfirmRestart(true)} />;
  }

  return (
    <div>
      {header}
      {body}
      <Dialog
        open={confirmRestart}
        title="¿Reiniciar el diagnóstico?"
        description="Se borrarán todas las respuestas de esta sesión."
        confirmLabel="Sí, reiniciar"
        onConfirm={restart}
        onCancel={() => setConfirmRestart(false)}
      />
      <Toast message={state.notice} onDismiss={() => dispatch({ type: "notice", message: null })} />
    </div>
  );
}
