import type { WithSpringConfig } from "react-native-reanimated";

/**
 * No bounce (brand-system §10: «the brand is not playful»). Critically damped
 * and clamped, so a spring settles inside the budget without overshooting.
 */
export const settle: WithSpringConfig = { damping: 28, stiffness: 320, mass: 1, overshootClamping: true };
