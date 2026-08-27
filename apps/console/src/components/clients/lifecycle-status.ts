/**
 * Which status transitions need a confirm modal (QA-15).
 * Pause and archive are reversible but not 1-click.
 * Reactivate / unarchive / activate stay 1-click.
 */
export function statusActionNeedsConfirm(next: "active" | "paused" | "archived"): boolean {
  return next === "paused" || next === "archived";
}
