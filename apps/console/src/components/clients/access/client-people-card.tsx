"use client";

import { Copy, MoreHorizontal, UserPlus, Users } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  Callout,
  ConfirmDialog,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  EmptyState,
  ErrorState,
  Field,
  Input,
  Section,
  StatusBadge,
  formatDateTime,
} from "@nexus/ui";

import {
  inviteClientMemberAction,
  resendClientMemberAction,
  revokeClientMemberAction,
} from "@/app/(console)/clients/[ref]/access/actions";
import { useLocale, useT } from "@/i18n/client";
import type { Locale } from "@/i18n/messages";
import type { ClientAccess, ClientAccessMember, ClientInvitation } from "@/lib/backend/client-access";

import { accessErrorKey, personRowLayout, personStatus, revokeCopy } from "./access-model";

type Props = {
  refId: string;
  /** `null`: no se pudo leer (el estado de error, con Reintentar). */
  access: ClientAccess | null;
  onMembers: (members: ClientAccessMember[]) => void;
  onRetry: () => void;
  retrying?: boolean;
};

/** Lo que vuelve una invitación: la fila pendiente que la lista enseña. */
function invitationRow(inv: ClientInvitation, name: string | null): ClientAccessMember {
  return { id: inv.id, kind: "invitation", email: inv.email, name, status: inv.status, expires_at: inv.expires_at };
}

/**
 * Una invitación nueva retira la anterior viva del mismo correo (la API lo hace
 * así): en la lista, la de antes pasa a revocada y la nueva entra arriba.
 */
export function withInvitation(members: readonly ClientAccessMember[], inv: ClientInvitation, name: string | null): ClientAccessMember[] {
  const rest = members.map((m) =>
    m.kind === "invitation" && m.email === inv.email && (m.status === "pending" || m.status === "expired") ? { ...m, status: "revoked" } : m,
  );
  return [invitationRow(inv, name), ...rest];
}

/**
 * Spec 056 (requisitos 3.4 a 3.7) — «Personas»: quién entra en la consola del
 * cliente y en qué estado está. Cada fila tiene una sola acción a la vista, la
 * principal para su estado (Reenviar a una invitada o caducada); el resto va en
 * «⋯», con «Revocar» al final, en rojo y con confirmación (guías de Apple,
 * `connector-model.rowLayout`). El enlace de una invitación se enseña una sola
 * vez, en un aviso que vive en la memoria de la página.
 *
 * Los cinco estados: cargando (`loading.tsx` de la ruta y la fila ocupada),
 * vacío (nadie todavía), error (Reintentar), parcial (con la consola apagada se
 * ve la lista pero no se invita) e ideal.
 */
export function ClientPeopleCard({ refId, access, onMembers, onRetry, retrying = false }: Props) {
  const t = useT();
  const locale = useLocale();
  const [notices, setNotices] = React.useState<ClientInvitation[]>([]);
  const [busy, setBusy] = React.useState<string | null>(null);
  const [revoking, setRevoking] = React.useState<ClientAccessMember | null>(null);
  const [revokeError, setRevokeError] = React.useState<string | null>(null);
  const emailInput = React.useRef<HTMLInputElement>(null);
  const heading = React.useRef<HTMLDivElement>(null);

  if (!access) {
    return (
      <Section title={t("clientAccess.people.title")} data-slot="client-people-card" data-state="error">
        <ErrorState
          title={t("clientAccess.load.error")}
          description={t("clientAccess.load.error.hint")}
          onRetry={retrying ? undefined : onRetry}
          retryLabel={t("clientAccess.retry")}
        />
      </Section>
    );
  }

  const members = access.members;
  const closed = !access.enabled || !access.eligible;
  const state = closed ? "partial" : members.length === 0 ? "empty" : "ideal";

  function notice(inv: ClientInvitation) {
    setNotices((prev) => [inv, ...prev.filter((n) => n.email !== inv.email)]);
  }

  async function resend(m: ClientAccessMember) {
    setBusy(m.id);
    const res = await resendClientMemberAction({ ref: refId, member: m.id });
    setBusy(null);
    if (!res.ok) {
      toast.error(t(accessErrorKey(res.code)));
      return;
    }
    onMembers(withInvitation(members, res.data, m.name));
    notice(res.data);
  }

  async function revoke() {
    const m = revoking;
    if (!m) return;
    setRevokeError(null);
    const res = await revokeClientMemberAction({ ref: refId, member: m.id });
    if (!res.ok) {
      // El diálogo se queda abierto con su error: nada ha cambiado.
      setRevokeError(t(accessErrorKey(res.code)));
      return;
    }
    setRevoking(null);
    onMembers(members.map((x) => (x.id === m.id ? res.data.member : x)));
    setNotices((prev) => prev.filter((n) => n.email !== m.email));
    toast.success(m.kind === "member" ? t("clientAccess.revoked.member", { email: m.email }) : t("clientAccess.revoked.invitation"));
  }

  return (
    <Section
      title={t("clientAccess.people.title")}
      description={t("clientAccess.people.description")}
      data-slot="client-people-card"
      data-state={state}
    >
      <div ref={heading} tabIndex={-1} className="sr-only">
        {t("clientAccess.people.title")}
      </div>
      {closed ? (
        <Callout tone="neutral">{access.eligible ? t("clientAccess.people.closed") : t("clientAccess.people.ineligible")}</Callout>
      ) : (
        <InviteForm
          refId={refId}
          inputRef={emailInput}
          onInvited={(inv, name) => {
            onMembers(withInvitation(members, inv, name));
            notice(inv);
          }}
        />
      )}
      {notices.length > 0 ? (
        <div className="grid min-w-0 gap-3">
          {notices.map((n) => (
            <InvitationNotice key={n.id} invitation={n} locale={locale} onDismiss={() => setNotices((prev) => prev.filter((x) => x.id !== n.id))} />
          ))}
        </div>
      ) : null}
      {members.length === 0 ? (
        <EmptyState icon={Users} title={t("clientAccess.people.empty")} description={t("clientAccess.people.empty.hint")} readonly={closed} />
      ) : (
        <ul className="grid min-w-0 divide-y divide-border rounded-md border border-border" aria-label={t("clientAccess.people.list")}>
          {members.map((m) => (
            <PersonRow
              key={m.id}
              member={m}
              locale={locale}
              busy={busy === m.id}
              onResend={() => resend(m)}
              onRevoke={() => {
                setRevokeError(null);
                setRevoking(m);
              }}
            />
          ))}
        </ul>
      )}
      <ConfirmDialog
        open={revoking !== null}
        onOpenChange={(open) => {
          if (!open) setRevoking(null);
        }}
        title={revoking ? t(revokeCopy(revoking).title) : ""}
        description={revoking ? t(revokeCopy(revoking).body, { email: revoking.email }) : null}
        confirmLabel={t("clientAccess.revoke")}
        cancelLabel={t("clientAccess.cancel")}
        destructive
        onConfirm={revoke}
        error={revokeError ?? undefined}
        // La fila revocada se queda sin acciones: el foco vuelve al correo o a la tarjeta.
        returnFocus={() => emailInput.current ?? heading.current}
      />
    </Section>
  );
}

function PersonRow({
  member: m,
  locale,
  busy,
  onResend,
  onRevoke,
}: {
  member: ClientAccessMember;
  locale: Locale;
  busy: boolean;
  onResend: () => void;
  onRevoke: () => void;
}) {
  const t = useT();
  const { primary, menu } = personRowLayout(m);
  const status = personStatus(m);
  const who = m.name || m.email;
  const until = m.kind === "invitation" && m.status === "pending" && m.expires_at ? formatDateTime(m.expires_at, locale) : null;
  return (
    <li className="flex min-w-0 flex-wrap items-center gap-3 px-4 py-3" data-slot="client-person" data-status={m.status} aria-busy={busy || undefined}>
      <div className="grid min-w-0 flex-1 basis-56 gap-1">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="min-w-0 font-medium break-words">{who}</span>
          <StatusBadge tone={status.tone}>{t(status.key)}</StatusBadge>
        </div>
        {m.name || until ? (
          <p className="min-w-0 text-sm text-pretty break-words text-muted-foreground">
            {[m.name ? m.email : null, until ? t("clientAccess.person.until", { date: until }) : null].filter(Boolean).join(" · ")}
          </p>
        ) : null}
      </div>
      <div className="flex max-w-full shrink-0 flex-wrap items-center gap-2">
        {primary === "resend" ? (
          <Button size="sm" variant="outline" onClick={onResend} loading={busy} disabled={busy} aria-label={t("clientAccess.resend.named", { email: m.email })}>
            {t("clientAccess.resend")}
          </Button>
        ) : null}
        {menu.length ? (
          <DropdownMenu>
            <DropdownMenuTrigger
              aria-label={t("clientAccess.more.named", { name: who })}
              disabled={busy}
              className="inline-flex size-8 shrink-0 items-center justify-center rounded-sm hover:bg-muted focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50"
              data-slot="client-person-more"
            >
              <MoreHorizontal aria-hidden="true" className="size-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-56">
              {menu.map((kind) =>
                kind === "revoke" ? (
                  <DropdownMenuItem key={kind} variant="destructive" onClick={onRevoke}>
                    {m.kind === "member" ? t("clientAccess.revoke.member") : t("clientAccess.revoke.invitation")}
                  </DropdownMenuItem>
                ) : null,
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
      </div>
    </li>
  );
}

function InviteForm({
  refId,
  inputRef,
  onInvited,
}: {
  refId: string;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onInvited: (inv: ClientInvitation, name: string | null) => void;
}) {
  const t = useT();
  const [email, setEmail] = React.useState("");
  const [name, setName] = React.useState("");
  const [error, setError] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const address = email.trim();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(address)) {
      setError(t("clientAccess.invite.error.email"));
      inputRef.current?.focus();
      return;
    }
    setError(null);
    startTransition(async () => {
      const res = await inviteClientMemberAction({ ref: refId, email: address, name: name.trim() || null });
      if (!res.ok) {
        setError(t(accessErrorKey(res.code)));
        return;
      }
      onInvited(res.data, name.trim() || null);
      setEmail("");
      setName("");
    });
  }

  return (
    <form onSubmit={submit} noValidate className="grid min-w-0 gap-3 @container" aria-label={t("clientAccess.invite.title")}>
      <div className="grid min-w-0 gap-3 @md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] @md:items-end">
        <Field label={t("clientAccess.invite.email")} error={error ?? undefined} required>
          {(a11y) => (
            <Input
              {...a11y}
              ref={inputRef}
              type="email"
              inputMode="email"
              autoComplete="off"
              maxLength={254}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t("clientAccess.invite.email.placeholder")}
            />
          )}
        </Field>
        <Field label={t("clientAccess.invite.name")} optionalLabel={t("clientAccess.optional")}>
          {(a11y) => <Input {...a11y} autoComplete="off" maxLength={120} value={name} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Button type="submit" loading={pending} disabled={pending}>
          <UserPlus aria-hidden="true" />
          {t("clientAccess.invite.send")}
        </Button>
      </div>
      <p className="text-xs text-pretty text-muted-foreground">{t("clientAccess.invite.hint")}</p>
    </form>
  );
}

/**
 * Lo que salió de cada invitación: si el correo se fue y el enlace para pasarlo a
 * mano. Es el único momento en que el enlace existe en claro: vive en la memoria
 * de la página, nunca en su dirección, y no vuelve al recargar.
 */
function InvitationNotice({ invitation, locale, onDismiss }: { invitation: ClientInvitation; locale: Locale; onDismiss: () => void }) {
  const t = useT();
  const { email, accept_url: url, email_sent: sent } = invitation;
  const until = formatDateTime(invitation.expires_at, locale);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      toast.success(t("clientAccess.link.copied"));
    } catch {
      toast.error(t("clientAccess.link.copyFailed"));
    }
  }

  return (
    <div className="grid min-w-0 gap-2" data-slot="client-invitation-notice">
      <Callout
        tone={sent ? "positive" : "warning"}
        title={<span className="break-words">{sent ? t("clientAccess.link.sent", { email }) : t("clientAccess.link.notSent", { email })}</span>}
        dismissible
        dismissLabel={t("clientAccess.link.dismiss", { email })}
        onDismiss={onDismiss}
      >
        {sent ? t("clientAccess.link.sent.hint", { date: until }) : t("clientAccess.link.notSent.hint", { date: until })}
      </Callout>
      <div className="flex min-w-0 gap-2">
        <Input
          readOnly
          value={url}
          aria-label={t("clientAccess.link.label", { email })}
          className="min-w-0 flex-1 font-mono text-xs"
          onFocus={(e) => e.currentTarget.select()}
        />
        <Button type="button" variant="outline" onClick={copy} aria-label={t("clientAccess.link.copy.named", { email })}>
          <Copy aria-hidden="true" />
          {t("clientAccess.link.copy")}
        </Button>
      </div>
    </div>
  );
}
