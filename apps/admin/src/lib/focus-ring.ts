/**
 * The panel's focus ring — 2 px of `--ring`, the one `tokens.css` draws for
 * everything focusable (6,1:1 on white, 7,3:1 on ink) — for the `@nexus/ui`
 * controls that drop it with `outline-none` / `outline-hidden`: Input,
 * Textarea, NativeSelect, Checkbox and DropdownMenuItem. Their own focus is a
 * 1 px border, a 30 % halo (1,6:1) or a tint (1,7:1 light, 1,1:1 dark), under
 * the workspace's 2 px and 3:1.
 *
 * `outline-solid` is not redundant: in Tailwind 4 both `outline-none` and
 * `outline-hidden` set `--tw-outline-style: none`, which `outline-2` reads.
 *
 * Goes away the day the primitives keep the ring themselves; they are shared
 * with the partner console, so the fix there is a change of its own.
 */
export const FOCUS_RING =
  "focus-visible:outline-solid focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

/** The same ring drawn inwards, for a menu item: the menu's popup clips whatever goes out (3,5:1 on its tint). */
export const FOCUS_RING_INSET =
  "focus-visible:outline-solid focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring";
