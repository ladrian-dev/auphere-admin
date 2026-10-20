/**
 * The few things the network layer tells the session (spec 031, R7.2, R13.1):
 * this phone was closed, or this version must update. A tiny emitter keeps the
 * API client free of React.
 */
export type SessionEvent =
  | { type: "closed"; reason: string | null }
  | { type: "update-required"; minimum: string | null; reason: string | null };

type Listener = (e: SessionEvent) => void;
const listeners = new Set<Listener>();

export function onSessionEvent(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function emitSessionEvent(e: SessionEvent): void {
  for (const l of [...listeners]) l(e);
}
