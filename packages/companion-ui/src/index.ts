/**
 * `@nexus/companion-ui` — el hilo del Companion como paquete (spec 003, T021–T023).
 *
 * Lo consumen la consola (el cajón) y la aplicación de escritorio (la pantalla
 * de operar). Nada de aquí sabe de rutas ni de `next/*`; la red entra por
 * `Transport`, los textos por `CompanionLocaleProvider`.
 */
export * from "./types";
export * from "./state";
export type {
  CompanionAction as CompanionActionDto,
  CompanionBudget,
  CompanionDecision,
  CompanionEnabled,
  CompanionEvent,
  CompanionEvents,
  CompanionResumed,
  CompanionRunStarted,
  CompanionRunSummary,
  CompanionThread,
  CompanionThreadRuns,
} from "./wire";
export { SseParser, parseBlock, type SseEvent } from "./sse";
export { cacheRunIds, loadRunIds, rememberRunId } from "./storage";
export {
  type CompanionClient,
  type Err,
  type Ok,
  type PageContext,
  type RequestInitLite,
  type Result,
  type Transport,
  createFetchTransport,
  makeCompanionClient,
} from "./transport";
export { useCompanion, type CompanionController, type Status } from "./use-companion";
export {
  CompanionLocaleProvider,
  type LinkProps,
  type MessageKey,
  type RenderLink,
  optionalKey,
  useLocale,
  useRenderLink,
  useT,
} from "./i18n";
export { type CompanionMessageKey, type Locale, companionMessages, formatMessage } from "./messages";
export { Composer, MAX_PROMPT } from "./components/composer";
export { ConfirmCard } from "./components/confirm-card";
export { IntakeCard } from "./components/intake-card";
export { Meters } from "./components/meters";
export { PlanCard } from "./components/plan-card";
export { SupportProposal, TicketRef } from "./components/support";
export { Thinking } from "./components/thinking";
export { Timeline } from "./components/timeline";
export { ToolCard } from "./components/tool-card";
export { TrialPanel } from "./components/trial-panel";
export { VerifyTable } from "./components/verify-table";
