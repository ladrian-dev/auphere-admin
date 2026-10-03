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

/**
 * Spec 017 (R1.6): qué aparece dentro de «Más» en la cabecera de la ficha.
 *
 * Un solo control en el mismo sitio para todos los roles; dentro, solo lo
 * que quien mira puede hacer. Un menú que cambia de forma según el rol
 * obliga a buscar dos veces el mismo sitio.
 */
export type MoreMenuItem = "pause" | "resume" | "activate" | "archive" | "unarchive" | "copyRef" | "delete";

export function moreMenuItems(
  status: string,
  { canWrite, canDelete }: { canWrite: boolean; canDelete: boolean },
): MoreMenuItem[] {
  const items: MoreMenuItem[] = [];
  if (canWrite) {
    if (status === "active") items.push("pause");
    if (status === "paused") items.push("resume");
    if (status === "provisioning") items.push("activate");
    items.push(status === "archived" ? "unarchive" : "archive");
  }
  // Copiar la referencia es leer: no necesita permiso de escritura.
  items.push("copyRef");
  if (deleteIsOffered(status, canDelete)) items.push("delete");
  return items;
}
