"use client";

import * as React from "react";

import { Button } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { AssignDialog } from "./assign-dialog";
import { requestedText } from "./money-model";
import { RequestBalanceDialog, useRequested } from "./request-balance";

export type BalanceMode = "assign" | "request";

/**
 * El botón que abre en el sitio «Asignar saldo a {cliente}» o, para quien no
 * puede asignar, «Pedir saldo» (spec 047, requisitos 45.1 y 45.7). Después de
 * pedir dice «Pedido hace…» y no deja repetirlo ese día.
 */
export function BalanceButton({
  refId,
  name,
  mode,
  label,
  variant = "default",
  size = "sm",
  className,
  defaultOpen = false,
}: {
  refId: string;
  name: string;
  mode: BalanceMode;
  /** Abierto al llegar: los avisos de saldo enlazan al Panel con `?assign=1`. */
  defaultOpen?: boolean;
  label?: string;
  variant?: "default" | "outline" | "secondary" | "ghost" | "link";
  size?: "default" | "xs" | "sm" | "lg";
  className?: string;
}) {
  const t = useT();
  const [open, setOpen] = React.useState(defaultOpen);
  const requested = useRequested(refId);
  const done = mode === "request" && requested !== undefined;
  const text = done ? requestedText(t, requested ?? null) : (label ?? t(mode === "assign" ? "money.assign.cta" : "money.request.cta"));
  return (
    <>
      <Button
        type="button"
        variant={done ? "outline" : variant}
        size={size}
        className={className}
        disabled={done}
        onClick={() => setOpen(true)}
        data-slot={mode === "assign" ? "assign-balance" : "request-balance-button"}
      >
        {text}
      </Button>
      <BalanceDialogs refId={refId} name={name} open={open ? mode : null} onClose={() => setOpen(false)} />
    </>
  );
}

/** Las dos ventanas, para quien abre desde un menú (⋯) y no desde un botón propio. */
export function BalanceDialogs({ refId, name, open, change = false, onClose }: { refId: string; name: string; open: BalanceMode | null; change?: boolean; onClose: () => void }) {
  if (open === "assign") return <AssignDialog refId={refId} name={name} change={change} onOpenChange={(o) => !o && onClose()} />;
  if (open === "request") return <RequestBalanceDialog refId={refId} name={name} onOpenChange={(o) => !o && onClose()} />;
  return null;
}
