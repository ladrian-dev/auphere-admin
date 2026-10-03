"use client";

import * as React from "react";

import { Button, Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@nexus/ui";

import { BuyCreditForm } from "@/components/billing/buy-credit-form";
import { useT } from "@/i18n/client";

/** «Comprar saldo»: the page's one primary action, in a dialog (spec 028). */
export function BuyDialog() {
  const t = useT();
  const [open, setOpen] = React.useState(false);
  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        {t("membership.credit.title")}
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("membership.credit.title")}</DialogTitle>
            <DialogDescription>{t("membership.credit.help")}</DialogDescription>
          </DialogHeader>
          <BuyCreditForm />
        </DialogContent>
      </Dialog>
    </>
  );
}
