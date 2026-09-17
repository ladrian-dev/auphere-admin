import type { QuestionStep, WizardStep } from "@/domain/enums";
import { QUESTION_STEPS } from "@/domain/enums";
import { ALL_QUESTIONS, questionById, questionIndex, type QuestionId } from "@/domain/questions";
import type { ContactDecision, PartialAnswers, Result, StoredSession } from "@/domain/types";

export interface WizardState {
  step: WizardStep;
  answers: PartialAnswers;
  startedAt: number;
  contactDecision?: ContactDecision;
  /** Resultado del envío del contacto (undefined hasta que se envía). */
  delivered?: boolean;
  result?: Result;
  error: string | null;
  notice: string | null;
  hydrated: boolean;
}

export type WizardAction =
  | { type: "hydrate"; session: StoredSession }
  | { type: "hydrated"; now: number }
  | { type: "notice"; message: string | null }
  | { type: "answer"; questionId: QuestionId; value: string | string[] }
  | { type: "next" }
  | { type: "back" }
  | { type: "resultReady"; result: Result }
  | { type: "processed" }
  | { type: "submitted"; delivered: boolean }
  | { type: "restart"; now: number }
  | { type: "fail"; message: string }
  | { type: "clearError" };

const FIRST = QUESTION_STEPS[0];
const LAST = QUESTION_STEPS[QUESTION_STEPS.length - 1] as QuestionStep;
const FLOW: WizardStep[] = [...QUESTION_STEPS, "lead", "processing", "result"];

export function initialState(now: number): WizardState {
  return { step: FIRST, answers: {}, startedAt: now, error: null, notice: null, hydrated: false };
}

export function isQuestionStep(step: WizardStep): step is QuestionStep {
  return (QUESTION_STEPS as readonly string[]).includes(step);
}

export function isScreenComplete(step: QuestionStep, answers: PartialAnswers): boolean {
  const q = questionById(step);
  const v = answers[q.id];
  if (q.type === "multi") return Array.isArray(v) && v.length > 0;
  return typeof v === "string" && v.length > 0;
}

export function progressFor(step: WizardStep): number {
  if (isQuestionStep(step)) return Math.round((questionIndex(step) / ALL_QUESTIONS.length) * 100);
  return 100;
}

export function nextStep(step: WizardStep): WizardStep {
  const i = FLOW.indexOf(step);
  return FLOW[Math.min(i + 1, FLOW.length - 1)] ?? step;
}

export function prevStep(step: WizardStep): WizardStep {
  if (step === "result" || step === "processing" || step === "lead") return LAST;
  const i = FLOW.indexOf(step);
  return FLOW[Math.max(i - 1, 0)] ?? step;
}

export function toStoredSession(state: WizardState): StoredSession {
  const session: StoredSession = { version: 1, step: state.step, answers: state.answers, startedAt: state.startedAt };
  if (state.contactDecision) session.contactDecision = state.contactDecision;
  return session;
}

export function wizardReducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case "hydrate": {
      const step = action.session.step === "welcome" ? FIRST : action.session.step;
      return { ...state, step, answers: action.session.answers, startedAt: action.session.startedAt, contactDecision: action.session.contactDecision, error: null, hydrated: true };
    }
    case "hydrated":
      return { ...state, hydrated: true, startedAt: state.startedAt || action.now };
    case "notice":
      return { ...state, notice: action.message };
    case "answer": {
      const q = questionById(action.questionId);
      let value: string | string[] = action.value;
      if (q.type === "multi") {
        const arr = Array.isArray(value) ? value : [value];
        value = [...new Set(arr)].slice(0, q.max ?? arr.length);
      } else if (Array.isArray(value)) {
        value = value[0] ?? "";
      }
      return { ...state, answers: { ...state.answers, [action.questionId]: value }, result: undefined };
    }
    case "next": {
      if (isQuestionStep(state.step) && !isScreenComplete(state.step, state.answers)) return state;
      if (!isQuestionStep(state.step)) return state;
      // Quien ya dejó su contacto no vuelve a pasar por el formulario.
      const next = state.step === LAST && state.contactDecision === "submitted" ? "processing" : nextStep(state.step);
      return { ...state, step: next, error: null };
    }
    case "back":
      if (state.step === FIRST) return state;
      return { ...state, step: prevStep(state.step), error: null };
    case "resultReady":
      return { ...state, result: action.result };
    case "processed":
      return state.step === "processing" ? { ...state, step: "result" } : state;
    case "submitted":
      return { ...state, step: "processing", contactDecision: "submitted", delivered: action.delivered };
    case "restart":
      return { ...initialState(action.now), hydrated: true };
    case "fail":
      return { ...state, error: action.message };
    case "clearError":
      return { ...state, error: null };
  }
}
