"use client";

import { Plus } from "lucide-react";
import * as React from "react";

import { Button, Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@nexus/ui";

import { BuyCreditForm } from "@/components/billing/buy-credit-form";
import { useT } from "@/i18n/client";

/**
 * «Comprar saldo»: the page's one primary action, in a dialog (spec 028). Spec
 * 047: el modal de 480 px del prototipo, con las cantidades rápidas.
 */
export function BuyDialog({
  accountCurrency,
  variant = "default",
  size = "default",
  label,
  iconOnly = false,
}: {
  accountCurrency?: string | null;
  /** El Panel lo pone en «Saldo disponible» como secundario: el primario de la vista es «Nuevo cliente». */
  variant?: "default" | "outline";
  size?: "default" | "sm";
  label?: string;
  /** Solo el «+», con `label` como nombre y como pista (owner, 2026-11-22: en el Panel). */
  iconOnly?: boolean;
}) {
  const t = useT();
  const [open, setOpen] = React.useState(false);
  return (
    <>
      {iconOnly ? (
        <Button
          variant={variant}
          size="icon-sm"
          onClick={() => setOpen(true)}
          data-slot="buy-balance"
          aria-label={label ?? t("membership.credit.title")}
          title={label ?? t("membership.credit.title")}
        >
          <Plus aria-hidden="true" />
        </Button>
      ) : (
        <Button variant={variant} size={size} onClick={() => setOpen(true)} data-slot="buy-balance">
          <Plus aria-hidden="true" />
          {label ?? t("membership.credit.title")}
        </Button>
      )}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("membership.credit.title")}</DialogTitle>
            <DialogDescription>{t("membership.credit.help")}</DialogDescription>
          </DialogHeader>
          <BuyCreditForm accountCurrency={accountCurrency} />
        </DialogContent>
      </Dialog>
    </>
  );
}
