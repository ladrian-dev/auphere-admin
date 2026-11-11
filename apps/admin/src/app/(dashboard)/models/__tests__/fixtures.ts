/**
 * Spec 059: a catalog row as `GET /admin/models/deployments` returns it
 * (`contracts/admin-api.md` §1), for the screen's tests. By default an active
 * model, priced by tokens, on its target, that nobody uses.
 */
import type { DeploymentRow, DeploymentStatus, SaleInfo, SalePolicy } from "@/lib/backend-models";

export const POLICY: SalePolicy = { multiplier: "2.2", floor: "1.5", sell_usd_per_million: "10" };

export const ON_TARGET: SaleInfo = {
  state: "on_target",
  lanes: {
    input: { cost: "4.000000", weight: "0.880000", sale: "8.800000", multiplier: "2.20" },
    cache_read: { cost: "0.400000", weight: "0.088000", sale: "0.880000", multiplier: "2.20" },
    output: { cost: "20.000000", weight: "4.400000", sale: "44.000000", multiplier: "2.20" },
  },
  proposed: { input: "0.880000", cache_read: "0.088000", output: "4.400000" },
};

type Overrides = Partial<Omit<DeploymentRow, "deployment">> & {
  status?: DeploymentStatus;
  retire_after?: string | null;
};

export function row(o: Overrides = {}): DeploymentRow {
  const { status = "active", retire_after = null, ...rest } = o;
  return {
    uuid: "d1",
    display_name: "Terra",
    deployment: {
      id: "openai/gpt-5.6-terra",
      model: "gpt-5.6-terra",
      family: "openai-gpt",
      provider: "openai",
      route: null,
      region: null,
      residency: "us",
      retention: { zero: false, how: null },
      license: null,
      contract: { dpa: true, subprocessor_listed: true },
      status,
      retire_after,
      quota: { tpm: null, rpm: null, verified_at: null },
      capabilities: {},
      prices: [],
      meter_weights: { w_in: 0.88, w_cache: 0.088, w_out: 4.4 },
    },
    current_price: {
      valid_from: "2026-10-01",
      source: "https://openai.com/api/pricing/",
      currency: "USD",
      unit: "per_million_tokens",
      input: 4,
      cache_read: 0.4,
      cache_write: null,
      output: 20,
    },
    certified_tasks: [],
    activation_missing: [],
    activation_messages: {},
    uses: { defaults: [], agents: 0, clients: [], verified: true, problem: null },
    sale: ON_TARGET,
    retirement_blocked_agents: null,
    ...rest,
  };
}

/** Sol: the model the agents answer with, and its fallback. */
export const SOL = row({
  uuid: "sol",
  display_name: "Sol",
  uses: {
    defaults: ["respond", "respond_fallback"],
    agents: 7,
    clients: ["Amigable Cobro", "New Air Climatización"],
    verified: true,
    problem: null,
  },
});

/** Terra after its output cost went up from 20 to 25: the sale lags behind (3.8). */
export const DRIFT = row({
  current_price: {
    valid_from: "2026-11-01",
    source: "https://openai.com/api/pricing/",
    currency: "USD",
    unit: "per_million_tokens",
    input: 4,
    cache_read: 0.4,
    cache_write: null,
    output: 25,
  },
  sale: {
    state: "drift",
    lanes: {
      input: { cost: "4.000000", weight: "0.880000", sale: "8.800000", multiplier: "2.20" },
      cache_read: { cost: "0.400000", weight: "0.088000", sale: "0.880000", multiplier: "2.20" },
      output: { cost: "25.000000", weight: "4.400000", sale: "44.000000", multiplier: "1.76" },
    },
    proposed: { input: "0.880000", cache_read: "0.088000", output: "5.500000" },
  },
});

/** Whisper: priced by the minute, without lanes (3.11). */
export const WHISPER = row({
  uuid: "w1",
  display_name: "Whisper",
  current_price: {
    valid_from: "2026-10-01",
    source: "https://openai.com/api/pricing/",
    currency: "USD",
    unit: "per_minute",
    input: null,
    cache_read: null,
    cache_write: null,
    output: null,
    audio_minute: 0.006,
  },
  sale: { state: "per_minute", lanes: null, proposed: null },
});

/** «Hoy» as the API judges it: the UTC day. */
export const today = () => new Date().toISOString().slice(0, 10);
export const yesterday = () => new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
