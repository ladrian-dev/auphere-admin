"use client";

/**
 * The billing e-mail, editable by the partner (owner, 2026-10-20).
 *
 * Until now only Auphere could set it and the screen said «escríbenos». The
 * 3D Secure notice («Confirma el cobro de tu tarjeta») goes to this address,
 * so a partner who cannot set it may never confirm a charge. Who can only
 * read it sees where notices go today — the contact e-mail when it is empty.
 */

import * as React from "react";
import { toast } from "sonner";

import { Button, Card, CardContent, Input, Label } from "@nexus/ui";

import { setBillingEmailAction } from "@/app/(console)/billing/actions";
import { useT } from "@/i18n/client";
import { actionErrorText } from "@/lib/action-error";

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function BillingEmailForm({
  email,
  contactEmail,
  canManage,
}: {
  email: string | null;
  contactEmail: string | null;
  canManage: boolean;
}) {
  const t = useT();
  const [editing, setEditing] = React.useState(false);
  const [value, setValue] = React.useState(email ?? "");
  const [pending, start] = React.useTransition();

  const empty = email
    ? email
    : contactEmail
      ? t("billing.email.fallback", { email: contactEmail })
      : t("billing.notSet");

  function save(event: React.FormEvent) {
    event.preventDefault();
    const next = value.trim();
    if (next && !EMAIL.test(next)) {
      toast.error(t("billing.email.invalid"));
      return;
    }
    start(async () => {
      const res = await setBillingEmailAction({ billing_email: next || null });
      if (!res.ok) return void toast.error(res.status === 422 ? t("billing.email.invalid") : actionErrorText(res, t));
      toast.success(t("billing.email.saved"));
      setEditing(false);
    });
  }

  // Spec 047 (prototipo): una tarjeta con «Añadir» o «Cambiar» en su cabecera,
  // el correo (o adónde van hoy los avisos) y la nota de para qué sirve.
  return (
    <Card data-slot="billing-email">
      <CardContent className="grid min-w-0 gap-3">
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
          <h2 id="billing-email-h" className="text-base font-semibold">
            {t("billing.email")}
          </h2>
          {canManage && !editing ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                setValue(email ?? "");
                setEditing(true);
              }}
            >
              {t(email ? "billing.email.change" : "billing.email.add")}
            </Button>
          ) : null}
        </div>
        {editing ? (
          <form onSubmit={save} noValidate className="flex min-w-0 flex-wrap items-center gap-2">
            <Label htmlFor="billing-email" className="sr-only">
              {t("billing.email")}
            </Label>
            <Input
              id="billing-email"
              type="email"
              autoComplete="email"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={contactEmail ?? "facturas@tuempresa.com"}
              className="min-w-0 flex-1"
              aria-describedby="billing-email-help"
              autoFocus
            />
            <Button type="submit" size="sm" disabled={pending}>
              {pending ? t("card.saving") : t("card.save")}
            </Button>
            <Button type="button" variant="ghost" size="sm" disabled={pending} onClick={() => setEditing(false)}>
              {t("billing.email.cancel")}
            </Button>
          </form>
        ) : (
          <p className={email ? "truncate font-mono text-sm" : "text-sm text-pretty text-muted-foreground"} title={email ?? undefined}>
            {empty}
          </p>
        )}
        <p id="billing-email-help" className="text-sm text-pretty text-muted-foreground">
          {t("billing.email.help")}
        </p>
      </CardContent>
    </Card>
  );
}
