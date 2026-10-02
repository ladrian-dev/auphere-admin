/**
 * Up to this many buttons in a whole list are shown as buttons. Beyond it,
 * every row folds its actions into a «⋯» menu (owner's rule, 2026-10-02):
 * a column of identical green buttons is noise, not a call to action.
 *
 * Lives outside ``row-actions.tsx`` on purpose: a value exported from a
 * ``"use client"`` file reaches a server component as a client reference,
 * not as the number, and every comparison with it is silently false.
 */
export const INLINE_BUTTONS_MAX = 2;

export function foldsIntoMenu(buttons: number): boolean {
  return buttons > INLINE_BUTTONS_MAX;
}
