"use client";

import { MoreHorizontal } from "lucide-react";
import { useState } from "react";

import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@nexus/ui";
import type { DeploymentRow, SalePolicy } from "@/lib/backend-models";
import { FOCUS_RING_INSET } from "@/lib/focus-ring";

import {
  ActivateDialog,
  CancelRetirementDialog,
  PriceDialog,
  RestoreDialog,
  RetireDialog,
  UnavailableDialog,
  WeightsDialog,
} from "./deployment-dialogs";
import { rowMenu } from "./labels";

type Open = "weights" | "activate" | "cancel" | "restore" | "retire" | "unavailable";

/**
 * Spec 059 (4.2, guías de Apple del dueño): one action in sight per row,
 * «Precio»; the rest in «⋯», with the destructive ones last and apart. A
 * model in use offers neither «Retirar» nor «No disponible» (1.1, 1.2): the
 * absence is designed, not a disabled button.
 */
export function RowActions({
  row,
  policy,
  routerVisible,
}: {
  row: DeploymentRow;
  policy: SalePolicy;
  routerVisible: boolean;
}) {
  const [open, setOpen] = useState<Open | null>(null);
  // Each opening mounts the dialog again, so its form starts from the row as it is now.
  const [nonce, setNonce] = useState(0);
  const menu = rowMenu(row, routerVisible);
  const name = row.display_name ?? row.deployment.id;
  const show = (which: Open) => () => {
    setNonce((n) => n + 1);
    setOpen(which);
  };
  // A dialog stays mounted while it is open, even if the row it changed no
  // longer offers it after the refresh: its confirmation is still on screen.
  const props = (which: Open) => ({
    row,
    open: open === which,
    onOpenChange: (next: boolean) => setOpen(next ? which : null),
  });

  const regular = [
    menu.weights ? { key: "weights" as const, label: "Pesos de venta" } : null,
    menu.activate ? { key: "activate" as const, label: "Activar" } : null,
    menu.cancelRetirement ? { key: "cancel" as const, label: "Cancelar retirada" } : null,
    menu.restore ? { key: "restore" as const, label: "Volver a disponible" } : null,
  ].filter((i) => i !== null);
  const destructive = [
    menu.retire ? { key: "retire" as const, label: "Retirar" } : null,
    menu.unavailable ? { key: "unavailable" as const, label: "No disponible" } : null,
  ].filter((i) => i !== null);

  return (
    <div className="flex items-center justify-end gap-1">
      <PriceDialog row={row} policy={policy} />
      {regular.length || destructive.length ? (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button variant="ghost" size="icon-sm" aria-label={`Más acciones de ${name}`}>
                <MoreHorizontal aria-hidden="true" className="size-4" />
              </Button>
            }
          />
          <DropdownMenuContent align="end" className="min-w-48">
            <DropdownMenuGroup>
              {regular.map((item) => (
                <DropdownMenuItem key={item.key} className={FOCUS_RING_INSET} onClick={show(item.key)}>
                  {item.label}
                </DropdownMenuItem>
              ))}
              {regular.length && destructive.length ? <DropdownMenuSeparator /> : null}
              {destructive.map((item) => (
                <DropdownMenuItem key={item.key} variant="destructive" className={FOCUS_RING_INSET} onClick={show(item.key)}>
                  {item.label}
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : null}
      {menu.weights || open === "weights" ? <WeightsDialog key={`weights-${nonce}`} policy={policy} {...props("weights")} /> : null}
      {menu.activate || open === "activate" ? <ActivateDialog key={`activate-${nonce}`} {...props("activate")} /> : null}
      {menu.cancelRetirement || open === "cancel" ? <CancelRetirementDialog key={`cancel-${nonce}`} {...props("cancel")} /> : null}
      {menu.restore || open === "restore" ? <RestoreDialog key={`restore-${nonce}`} {...props("restore")} /> : null}
      {menu.retire || open === "retire" ? <RetireDialog key={`retire-${nonce}`} {...props("retire")} /> : null}
      {menu.unavailable || open === "unavailable" ? <UnavailableDialog key={`unavailable-${nonce}`} {...props("unavailable")} /> : null}
    </div>
  );
}
