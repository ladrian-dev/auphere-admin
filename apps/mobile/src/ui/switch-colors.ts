import type { Palette } from "@/theme/tokens.gen";

/**
 * The colours of a switch, one source for every screen (spec 044, gate
 * review): «off» on the faint ink, which reads at 3:1 or more on a card in
 * both themes (WCAG 1.4.11); the muted track was 1.1–1.2:1.
 */
export function switchColors(colors: Palette) {
  return {
    trackColor: { true: colors.primary, false: colors.subtle },
    ios_backgroundColor: colors.subtle,
    thumbColor: colors.card,
  };
}
