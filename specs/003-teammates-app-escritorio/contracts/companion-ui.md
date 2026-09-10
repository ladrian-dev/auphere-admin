# Contrato — `@nexus/companion-ui`

Paquete del workspace raíz, React 19 + `@nexus/ui`, **sin `next`**. Lo consumen
`apps/console` (el cajón) y `apps/desktop` (la pantalla).

## Exporta

```ts
// estado
export { companionReducer, emptyCompanionState, pendingAction, isBusy, thinkingToolCount, trialClientRef } from "./state";
export type { CompanionState, CompanionAction, TimelineItem, ActionItem, ToolItem, WireEvent, RunStatus, BudgetMeter, CostMeter, ContextMeter } from "./types";

// transporte — lo implementa cada app
export interface Transport {
  request<T>(path: string, init?: { method?: string; body?: unknown }): Promise<Result<T>>;
  openStream(runId: string, sinceSeq: number, onEvent: (e: WireEvent) => void): () => void;
}
export function useCompanion(transport: Transport, threadId: string | null): CompanionApi;

// componentes
export { Timeline, ConfirmCard, Composer, Meters, Thinking, VerifyTable, IntakeCard, PlanCard, ToolCard, SupportCard };

// textos
export { CompanionMessagesProvider, useCompanionText } ;  // recibe `t(key)`; el paquete trae messages/{es,en}.ts con sus claves
```

## Reglas

- Cero `hex` inline, tokens de `@nexus/ui` solo; los cinco estados por
  componente se conservan con sus tests (los 12 existentes se mueven con el
  código).
- Ningún componente sabe de rutas (`next/link`, `usePathname`): los enlaces se
  reciben como *render props* o callbacks (`onOpenClient(ref)`).
- `Transport` es lo único que toca red; en el escritorio es IPC.
- Versionado: el paquete no se publica; es `workspace:*`.

## Lo que se queda en la consola

`drawer.tsx`, `companion-launcher.tsx`, `trial-panel.tsx`, `page-context.ts`, y
la implementación de `Transport` sobre `fetch` + `EventSource`.
