import { tokens } from "@/theme/tokens.gen";

/**
 * Spec 031, D24: the motion budget, from the console's tokens. Nothing in the
 * app animates for longer than `MAX`, and nothing loops except «Reconectando».
 */
export const MAX = 300;

export const durations = {
  /** A press, a toggle. */
  fast: tokens.duration.fast,
  /** Something arrives: a row, a bubble, a notice. */
  enter: tokens.duration.enter,
  /** Something leaves: quicker than it came. */
  exit: tokens.duration.exit,
  /** A state change: the composer after «Tomar el control». */
  state: tokens.duration.state,
} as const;

for (const [name, ms] of Object.entries(durations)) {
  if (ms > MAX) throw new Error(`motion: ${name} is ${ms} ms, over the ${MAX} ms budget`);
}
