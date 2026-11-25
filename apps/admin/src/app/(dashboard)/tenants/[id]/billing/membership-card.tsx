"use client";

import { Check, Copy, MoreHorizontal, RefreshCw } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  EmptyState,
  ErrorState,
  Input,
  Label,
  StatusBadge,
} from "@nexus/ui";
import type { MembershipChargeOut, MembershipOut, MembershipPayer } from "@/lib/backend";
import { formatCents, longDate, relativeTime } from "@/lib/format";
import { parseUsdToCents } from "@/lib/money";
import { DEFAULT_MEMBERSHIP_CENTS, PAYER_LABEL } from "@/lib/send-only";

import {
  archiveMembershipAction,
  cancelMembershipAction,
  chargeMembershipAction,
  membershipCheckoutAction,
  putMembershipAction,
  refreshMembershipAction,
} from "./membership-actions";
import { chargeStatus, membershipView } from "./membership-view";

export type MembershipState =
  | { kind: "none" }
  | { kind: "error" }
  | { kind: "ok"; membership: MembershipOut; charges: MembershipChargeOut[] | null };

type Partner = { id: string; name: string | null } | null;

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
 * Spec 077 (T027): the client's monthly membership in Facturación. Without
 * one, it says the client's sends depend on no payment, as today, and offers
 * to require it. With one: its state as the API reads it, who pays, the
 * payment link with its expiry, and the charges. «Del saldo del partner»,
 * never «bolsa» (that word names a client's pool since spec 047).
 */
export function MembershipCard({
  tenantId,
  tenantName,
  partner,
  state,
}: {
  tenantId: string;
  tenantName: string;
  partner: Partner;
  state: MembershipState;
}) {
  const router = useRouter();
  const [formOpen, setFormOpen] = useState(false);
  // «Quitar membresía» removes the menu it was opened from; once the page
  // reloads without a membership, focus lands on «Exigir membresía».
  const requireButton = useRef<HTMLButtonElement>(null);
  const focusRequire = useRef(false);
  useEffect(() => {
    if (state.kind === "none" && focusRequire.current) {
      focusRequire.current = false;
      requireButton.current?.focus();
    }
  }, [state.kind]);

  if (state.kind === "error") {
    return (
      <ErrorState
        title="No se pudo leer la membresía"
        description="La API no respondió. Sin leerla, el panel no dice si sus envíos salen."
        onRetry={() => router.refresh()}
        retryLabel="Reintentar"
      />
    );
  }
  if (state.kind === "none") {
    return (
      <>
        <EmptyState
          title="Sin membresía"
          description="Sus envíos no dependen de ningún pago, como hoy."
          action={
            <Button ref={requireButton} onClick={() => setFormOpen(true)}>
              Exigir membresía
            </Button>
          }
        />
        {/* Mounted only while open: it starts from the defaults every time. */}
        {formOpen ? (
          <MembershipForm
            open
            onOpenChange={setFormOpen}
            tenantId={tenantId}
            tenantName={tenantName}
            partner={partner}
            current={null}
          />
        ) : null}
      </>
    );
  }
  return (
    <MembershipDetail
      tenantId={tenantId}
      tenantName={tenantName}
      partner={partner}
      membership={state.membership}
      charges={state.charges}
      onArchived={() => {
        focusRequire.current = true;
      }}
    />
  );
}

function MembershipDetail({
  tenantId,
  tenantName,
  partner,
  membership: m,
  charges,
  onArchived,
}: {
  tenantId: string;
  tenantName: string;
  partner: Partner;
  membership: MembershipOut;
  charges: MembershipChargeOut[] | null;
  onArchived: () => void;
}) {
  const router = useRouter();
  const view = membershipView(m);
  const [busy, setBusy] = useState<string | null>(null);
  const [dialog, setDialog] = useState<"amount" | "cancel" | "archive" | "charge" | "link" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const payerName = m.partner_name ?? partner?.name ?? "su partner";

  /** A dialog opens clean: a failure of another action is not its own. */
  function openDialog(d: "amount" | "cancel" | "archive" | "charge" | "link") {
    setError(null);
    setDialog(d);
  }

  async function act(key: string, fn: () => Promise<{ ok: true } | { ok: false; error: string }>, done: string) {
    setBusy(key);
    setError(null);
    const res = await fn();
    setBusy(null);
    if (!res.ok) {
      setError(res.error);
      toast.error("No se pudo hacer", { description: res.error });
      return false;
    }
    toast.success(done);
    setDialog(null);
    router.refresh();
    return true;
  }

  const amount = formatCents(m.amount_cents);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge tone={view.pill.tone}>{view.pill.label}</StatusBadge>
            <span className="text-base font-semibold tabular-nums">
              {amount} <span className="text-sm font-normal text-muted-foreground">al mes</span>
            </span>
          </div>
          <p className="text-sm text-pretty text-muted-foreground">{view.sub}</p>
          {view.pendingAmount ? (
            <p className="text-sm text-pretty text-muted-foreground">Desde el próximo periodo: {view.pendingAmount} al mes.</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {view.canRefresh ? (
            <>
              <span className="text-xs text-muted-foreground">
                {m.last_synced_at ? `Stripe, ${relativeTime(m.last_synced_at)}` : "Sin leer de Stripe todavía"}
              </span>
              <Button
                variant="outline"
                size="sm"
                loading={busy === "refresh"}
                disabled={busy !== null}
                onClick={() => void act("refresh", () => refreshMembershipAction(tenantId), "Estado leído de Stripe")}
              >
                <RefreshCw aria-hidden="true" />
                Actualizar
              </Button>
            </>
          ) : null}
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button variant="outline" size="icon-sm" aria-label="Opciones de la membresía" disabled={busy !== null}>
                  <MoreHorizontal aria-hidden="true" />
                </Button>
              }
            />
            <DropdownMenuContent align="end" className="min-w-48">
              <DropdownMenuItem disabled={view.amountLocked !== null} onClick={() => openDialog("amount")}>
                Cambiar importe…
              </DropdownMenuItem>
              {view.canCancel ? (
                <DropdownMenuItem variant="destructive" onClick={() => openDialog("cancel")}>
                  Cancelar membresía…
                </DropdownMenuItem>
              ) : null}
              {view.canArchive ? (
                <DropdownMenuItem variant="destructive" onClick={() => openDialog("archive")}>
                  Quitar membresía…
                </DropdownMenuItem>
              ) : null}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
      {view.amountLocked ? <p className="text-xs text-pretty text-muted-foreground">{view.amountLocked}</p> : null}

      <dl className="grid gap-4 sm:grid-cols-2">
        <div className="grid gap-1">
          <dt className="text-xs text-muted-foreground">Quién la paga</dt>
          <dd className="text-sm">
            {PAYER_LABEL[m.payer] ?? m.payer}
            {m.payer === "partner_wallet" ? <span className="text-muted-foreground"> · {payerName}</span> : null}
          </dd>
        </div>
        {m.billing_email ? (
          <div className="grid min-w-0 gap-1">
            <dt className="text-xs text-muted-foreground">Correo de facturación</dt>
            <dd className="text-sm wrap-anywhere">{m.billing_email}</dd>
          </div>
        ) : null}
      </dl>

      <Callout
        tone={view.noticeTone === "muted" ? "neutral" : view.noticeTone}
        action={
          view.canCharge ? (
            <Button size="sm" disabled={busy !== null} onClick={() => openDialog("charge")}>
              Cobrar ahora
            </Button>
          ) : undefined
        }
      >
        {view.notice}
      </Callout>

      {view.link.kind === "live" ? (
        // Keyed by the link: a new one starts with «Copiar enlace», never with the last «Copiado».
        <PaymentLink
          key={view.link.url}
          url={view.link.url}
          expiresAt={view.link.expiresAt}
          busy={busy !== null}
          onCreateAnother={() => openDialog("link")}
        />
      ) : view.link.kind === "expired" || view.link.kind === "create" ? (
        <div className="flex flex-wrap items-center gap-3">
          <Button
            loading={busy === "link"}
            disabled={busy !== null}
            onClick={() =>
              void act("link", () => membershipCheckoutAction(tenantId), "Enlace de pago creado: cópialo y envíaselo")
            }
          >
            {view.link.kind === "create" ? view.link.label : "Crear enlace nuevo"}
          </Button>
          <p className="text-xs text-pretty text-muted-foreground">
            {view.link.kind === "expired"
              ? `El enlace anterior caducó${view.link.expiredAt ? ` el ${longDate(view.link.expiredAt)}` : ""}.`
              : "Stripe lo caduca a las 24 horas."}
          </p>
        </div>
      ) : null}

      <ChargesTable charges={charges} isStripe={view.isStripe} onRetry={() => router.refresh()} />

      {/* Mounted only while open: it starts from the membership as it is now. */}
      {dialog === "amount" ? (
        <MembershipForm
          open
          onOpenChange={(open) => setDialog(open ? "amount" : null)}
          tenantId={tenantId}
          tenantName={tenantName}
          partner={partner}
          current={m}
        />
      ) : null}
      <ConfirmDialog
        open={dialog === "link"}
        onOpenChange={(open) => {
          if (!open) {
            setDialog(null);
            setError(null);
          }
        }}
        title="¿Crear otro enlace de pago?"
        description="El enlace actual caduca al momento: si ya se lo enviaste, ese deja de servir y hay que mandarle el nuevo."
        confirmLabel="Crear otro"
        onConfirm={async () => {
          await act("link", () => membershipCheckoutAction(tenantId), "Enlace nuevo creado; el anterior ya no sirve");
        }}
        error={error ?? undefined}
      />
      <ConfirmDialog
        open={dialog === "charge"}
        onOpenChange={(open) => {
          if (!open) {
            setDialog(null);
            setError(null);
          }
        }}
        title={`¿Cobrar ${amount} del saldo de ${payerName}?`}
        description={`Se descuenta ahora del saldo de ${payerName} (dentro de su línea de crédito, si la tiene). Si no alcanza, no se descuenta nada y la membresía sigue impagada.`}
        confirmLabel="Cobrar ahora"
        onConfirm={async () => {
          await act("charge", () => chargeMembershipAction(tenantId), "Cobro hecho");
        }}
        error={error ?? undefined}
      />
      <ConfirmDialog
        open={dialog === "cancel"}
        onOpenChange={(open) => {
          if (!open) {
            setDialog(null);
            setError(null);
          }
        }}
        title={`¿Cancelar la membresía de ${tenantName}?`}
        description={
          view.isStripe
            ? "Se cancela la suscripción en Stripe y no se cobra nada más. Sus envíos se cortan ahora mismo: la API responde 402."
            : "No se cobra nada más del saldo del partner. Sus envíos se cortan ahora mismo: la API responde 402."
        }
        confirmLabel="Cancelar membresía"
        cancelLabel="Volver"
        destructive
        onConfirm={async () => {
          await act("cancel", () => cancelMembershipAction(tenantId), "Membresía cancelada");
        }}
        error={error ?? undefined}
      />
      <ConfirmDialog
        open={dialog === "archive"}
        onOpenChange={(open) => {
          if (!open) {
            setDialog(null);
            setError(null);
          }
        }}
        title={`¿Quitar la membresía de ${tenantName}?`}
        description="Deja de exigirse: sus envíos ya no dependen de ningún pago. La membresía y sus cobros quedan archivados, no se borran."
        confirmLabel="Quitar membresía"
        cancelLabel="Volver"
        destructive
        onConfirm={async () => {
          if (await act("archive", () => archiveMembershipAction(tenantId), "Membresía quitada")) onArchived();
        }}
        error={error ?? undefined}
      />
    </div>
  );
}

/** The live payment link. Its own component so «Copiado» belongs to this link only. */
function PaymentLink({
  url,
  expiresAt,
  busy,
  onCreateAnother,
}: {
  url: string;
  expiresAt: string | null;
  busy: boolean;
  onCreateAnother: () => void;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      toast.success("Enlace copiado");
    } catch {
      toast.error("No se pudo copiar: selecciona el enlace y cópialo a mano");
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor="pay-link">Enlace de pago</Label>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          id="pay-link"
          readOnly
          value={url}
          onFocus={(e) => e.currentTarget.select()}
          className="min-w-0 flex-1 basis-72 font-mono text-xs"
        />
        <Button type="button" onClick={() => void copy()}>
          {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
          {copied ? "Copiado" : "Copiar enlace"}
        </Button>
        <Button type="button" variant="outline" disabled={busy} onClick={onCreateAnother}>
          Crear otro
        </Button>
      </div>
      <p className="text-xs text-pretty text-muted-foreground">
        {expiresAt ? `Caduca ${relativeTime(expiresAt)}. ` : ""}Crear otro caduca este.
      </p>
    </div>
  );
}

function ChargesTable({
  charges,
  isStripe,
  onRetry,
}: {
  charges: MembershipChargeOut[] | null;
  isStripe: boolean;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">Cobros</h3>
      {charges === null ? (
        <ErrorState
          className="py-8"
          title="No se pudieron leer los cobros"
          description="La API no respondió. El estado de la membresía, arriba, sí se pudo leer."
          onRetry={onRetry}
          retryLabel="Reintentar"
        />
      ) : charges.length === 0 ? (
        <EmptyState className="py-8" title="Aún no hay cobros" description="Aparecen con el primer cobro." readonly />
      ) : (
        <div className="overflow-x-auto rounded-md ring-1 ring-border">
          <table className="w-full min-w-[32rem] text-sm">
            <caption className="sr-only">Cobros de la membresía</caption>
            <thead className="bg-muted/50 text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">
                  Periodo
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Importe
                </th>
                <th scope="col" className="px-3 py-2 font-medium">
                  Estado
                </th>
                <th scope="col" className="px-4 py-2 font-medium">
                  Factura
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {charges.map((c, i) => {
                const s = chargeStatus(c.status);
                return (
                  <tr key={`${c.period_start ?? "x"}-${i}`}>
                    <td className="px-4 py-2 tabular-nums">
                      {c.period_start ? longDate(c.period_start) : "—"} – {c.period_end ? longDate(c.period_end) : "—"}
                    </td>
                    <td className="px-3 py-2 tabular-nums">{formatCents(c.amount_cents)}</td>
                    <td className="px-3 py-2">
                      <StatusBadge tone={s.tone}>{s.label}</StatusBadge>
                    </td>
                    <td className="px-4 py-2">
                      {c.url ? (
                        <a
                          href={c.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary-deep underline-offset-4 hover:underline"
                        >
                          Ver factura<span className="sr-only"> (se abre en otra pestaña)</span>
                        </a>
                      ) : (
                        <span className="text-muted-foreground">{isStripe ? "—" : "Del saldo"}</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/**
 * Require a membership, or change its amount. Who pays: the client by card
 * (Stripe, needs a billing e-mail) or the partner's balance — offered only
 * when the client has a partner. With the balance, saving charges it at once.
 */
function MembershipForm({
  open,
  onOpenChange,
  tenantId,
  tenantName,
  partner,
  current,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tenantId: string;
  tenantName: string;
  partner: Partner;
  current: MembershipOut | null;
}) {
  const router = useRouter();
  const [payer, setPayer] = useState<MembershipPayer>(current?.payer ?? "stripe");
  const [amount, setAmount] = useState(((current?.pending_amount_cents ?? current?.amount_cents ?? DEFAULT_MEMBERSHIP_CENTS) / 100).toFixed(2).replace(".", ","));
  const [email, setEmail] = useState(current?.billing_email ?? "");
  const [touched, setTouched] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const editing = current !== null;
  const cents = parseUsdToCents(amount);
  // Changing the amount keeps the e-mail it has; only a new Stripe membership asks for one.
  const emailOk = payer !== "stripe" || editing || EMAIL_RE.test(email.trim());
  const valid = cents !== null && emailOk;
  const partnerName = partner?.name ?? "su partner";

  async function submit() {
    setTouched(true);
    if (!valid || cents === null) return;
    setPending(true);
    setError(null);
    const res = await putMembershipAction(tenantId, {
      payer,
      amount_cents: cents,
      ...(payer === "stripe" && email.trim() ? { billing_email: email.trim() } : {}),
    });
    setPending(false);
    if (!res.ok) return void setError(res.error);
    toast.success(editing ? "Importe cambiado" : "Membresía exigida");
    onOpenChange(false);
    router.refresh();
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !pending && onOpenChange(o)}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? "Cambiar importe" : `Exigir membresía a ${tenantName}`}</DialogTitle>
          <DialogDescription>
            {editing
              ? current.payer === "partner_wallet"
                ? "El importe nuevo se cobra desde el próximo periodo."
                : "El próximo enlace de pago usa el importe nuevo."
              : "Sin la membresía activa, su API no envía. Lo de Meta lo paga el cliente aparte, en su cuenta."}
          </DialogDescription>
        </DialogHeader>
        <form
          noValidate
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          {editing ? null : (
            <fieldset className="grid gap-2">
              <legend className="mb-1 text-sm font-medium">Quién la paga</legend>
              <div className="grid gap-2 sm:grid-cols-2">
                <PayerOption
                  value="stripe"
                  checked={payer === "stripe"}
                  onSelect={setPayer}
                  title="El cliente, con tarjeta"
                  help="Paga por un enlace de Stripe y se renueva cada mes."
                />
                {partner ? (
                  <PayerOption
                    value="partner_wallet"
                    checked={payer === "partner_wallet"}
                    onSelect={setPayer}
                    title="Del saldo del partner"
                    help={`Se descuenta cada mes del saldo de ${partnerName}. Sin saldo, se corta.`}
                  />
                ) : null}
              </div>
              {partner ? null : (
                <p className="text-xs text-pretty text-muted-foreground">
                  Sin partner solo puede pagarla el cliente: no hay saldo de partner del que cobrar.
                </p>
              )}
            </fieldset>
          )}
          <div className="grid gap-1">
            <Label htmlFor="membership-amount">Importe mensual (USD)</Label>
            <Input
              id="membership-amount"
              inputMode="decimal"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              aria-invalid={touched && cents === null ? true : undefined}
              aria-describedby="membership-amount-help"
              className="max-w-40 tabular-nums"
            />
            <p id="membership-amount-help" className={touched && cents === null ? "text-xs text-destructive" : "text-xs text-muted-foreground"}>
              {touched && cents === null ? "Escribe un importe, por ejemplo 40,00." : "40,00 por defecto."}
            </p>
          </div>
          {payer === "stripe" && !editing ? (
            <div className="grid gap-1">
              <Label htmlFor="membership-email">Correo de facturación</Label>
              <Input
                id="membership-email"
                type="email"
                autoComplete="off"
                placeholder="facturacion@empresa.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                aria-invalid={touched && !emailOk ? true : undefined}
                aria-describedby="membership-email-help"
              />
              <p id="membership-email-help" className={touched && !emailOk ? "text-xs text-destructive" : "text-xs text-muted-foreground"}>
                {touched && !emailOk ? "Escribe un correo válido." : "Stripe le manda aquí sus facturas."}
              </p>
            </div>
          ) : null}
          {payer === "partner_wallet" && !editing && cents !== null ? (
            <Callout tone="info">
              Al guardar se cobran {formatCents(cents)} del saldo de {partnerName} en el acto. Si no alcanza, queda impagada y
              se reintenta sola.
            </Callout>
          ) : null}
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <DialogFooter>
            <Button type="button" variant="outline" disabled={pending} onClick={() => onOpenChange(false)}>
              Cancelar
            </Button>
            <Button type="submit" loading={pending} disabled={pending}>
              {editing ? "Guardar importe" : payer === "partner_wallet" ? "Exigir y cobrar" : "Exigir membresía"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function PayerOption({
  value,
  checked,
  onSelect,
  title,
  help,
}: {
  value: MembershipPayer;
  checked: boolean;
  onSelect: (v: MembershipPayer) => void;
  title: string;
  help: string;
}) {
  return (
    <label className="flex min-w-0 cursor-pointer items-start gap-3 rounded-md border border-input p-3 text-sm transition-colors has-[:checked]:border-primary has-[:checked]:ring-1 has-[:checked]:ring-primary has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring motion-reduce:transition-none">
      <input
        type="radio"
        name="membership-payer"
        value={value}
        checked={checked}
        onChange={() => onSelect(value)}
        className="mt-1 size-4 shrink-0 accent-primary"
      />
      <span className="grid min-w-0 gap-1">
        <span className="font-medium">{title}</span>
        <span className="text-xs text-pretty text-muted-foreground">{help}</span>
      </span>
    </label>
  );
}
