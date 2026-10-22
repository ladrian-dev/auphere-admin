import { tokens } from "@/theme/tokens.gen";
import { switchColors } from "@/ui/switch-colors";

/**
 * Spec 044, gate review (WCAG 1.4.11): an «off» switch has to be seen against
 * its row — the muted track was 1.1:1 in dark and 1.2:1 in light.
 */
const channels = (hex: string) => {
  const h = hex.replace("#", "");
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16)).concat(h.length === 8 ? parseInt(h.slice(6, 8), 16) / 255 : 1);
};
const over = (fg: string, bg: string) => {
  const [r, g, b, a] = channels(fg) as [number, number, number, number];
  const [R, G, B] = channels(bg) as [number, number, number];
  return [r * a + R * (1 - a), g * a + G * (1 - a), b * a + B * (1 - a)];
};
const luminance = ([r, g, b]: number[]) =>
  [r!, g!, b!].map((c) => (c / 255 <= 0.03928 ? c / 255 / 12.92 : ((c / 255 + 0.055) / 1.055) ** 2.4)).reduce((sum, c, i) => sum + c * [0.2126, 0.7152, 0.0722][i]!, 0);
const contrast = (a: number[], b: number[]) => {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
};

it.each(["light", "dark"] as const)("the off track reads at 3:1 or more on a card (%s)", (scheme) => {
  const colors = tokens[scheme];
  const card = over(colors.card, colors.background);
  expect(contrast(over(switchColors(colors).trackColor.false, colors.card), card)).toBeGreaterThanOrEqual(3);
});
