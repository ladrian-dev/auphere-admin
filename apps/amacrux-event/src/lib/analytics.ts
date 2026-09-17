import type { AnalyticsEventName } from "@/domain/enums";
import type { AnalyticsEvent, AnalyticsProps } from "@/domain/types";

import { analyticsProvider } from "./env";

export type AnalyticsAdapter = (event: AnalyticsEvent) => void;

declare global {
  interface Window {
    plausible?: (name: string, options?: { props?: Record<string, string | number> }) => void;
  }
}

const noop: AnalyticsAdapter = () => {};

const consoleAdapter: AnalyticsAdapter = (event) => {
  console.info("[analytics]", event.name, event.props);
};

const plausibleQueue: AnalyticsEvent[] = [];
const plausibleAdapter: AnalyticsAdapter = (event) => {
  if (typeof window === "undefined") return;
  if (typeof window.plausible !== "function") {
    if (plausibleQueue.length < 50) plausibleQueue.push(event);
    return;
  }
  while (plausibleQueue.length > 0) {
    const queued = plausibleQueue.shift();
    if (queued) window.plausible(queued.name, { props: toPlausibleProps(queued.props) });
  }
  window.plausible(event.name, { props: toPlausibleProps(event.props) });
};

function toPlausibleProps(props: AnalyticsEvent["props"]): Record<string, string | number> {
  const out: Record<string, string | number> = {};
  for (const [k, v] of Object.entries(props)) if (v !== undefined) out[k] = v;
  return out;
}

let override: AnalyticsAdapter | null = null;

function resolveAdapter(): AnalyticsAdapter {
  if (override) return override;
  switch (analyticsProvider()) {
    case "console":
      return consoleAdapter;
    case "plausible":
      return plausibleAdapter;
    default:
      return noop;
  }
}

/** Para tests y para inyectar un proveedor distinto. `null` restaura el de configuración. */
export function configureAnalytics(adapter: AnalyticsAdapter | null): void {
  override = adapter;
}

function stripUndefined(props: AnalyticsProps): AnalyticsProps {
  const out: AnalyticsProps = {};
  for (const [k, v] of Object.entries(props)) if (v !== undefined) (out as Record<string, unknown>)[k] = v;
  return out;
}

export function track(name: AnalyticsEventName, props: AnalyticsProps = {}): void {
  const event: AnalyticsEvent = { name, props: { ...stripUndefined(props), ts: Date.now() } };
  try {
    resolveAdapter()(event);
  } catch {
    // La analítica nunca rompe la experiencia.
  }
}
