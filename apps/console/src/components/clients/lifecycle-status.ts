/**
 * Which status transitions need a confirm modal (QA-15).
 * Pause and archive are reversible but not 1-click.
 * Reactivate / unarchive / activate stay 1-click.
 */
export function statusActionNeedsConfirm(next: "active" | "paused" | "archived"): boolean {
  return next === "paused" || next === "archived";
}

/**
 * Delete is offered only once the client is archived (the API refuses it
 * otherwise). A red button that answers "archive first" when pressed is a
 * trap, not an affordance.
 */
export function deleteIsOffered(status: string, canDelete: boolean): boolean {
  return canDelete && status === "archived";
}
