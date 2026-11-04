"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  Button,
  Callout,
  ConfirmDialog,
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  Input,
  Section,
  StatusBadge,
} from "@nexus/ui";

import type { OwnerInvitationResult, PartnerOwnerState } from "@/lib/backend";

import {
  inviteOwnerAction,
  resendOwnerInvitationAction,
  revokeOwnerInvitationAction,
} from "../../_invitation/actions";
import { InvitationResult } from "../../_invitation/invitation-result";
import {
  DEAD_INVITATION_CODES,
  FIELD_OF_CODE,
  OWNER_EMAIL_BAD_SHAPE,
  OWNER_EMAIL_REQUIRED,
  SENDING_HINT,
} from "../../_invitation/messages";

/** A live invitation of Auphere, with its dates already in words: they are
 *  written on the server, so hydrating cannot change them. */
export type AuphereInvitationRow = {
  id: string;
  email: string;
  expiresOn: string;
  sentAgo: string | null;
};

type Shown = { result: OwnerInvitationResult; replaced: boolean };
type Notice = { tone: "positive" | "info" | "danger"; text: string };

const schema = z.object({
  email: z.string().trim().min(1, OWNER_EMAIL_REQUIRED).max(255).email(OWNER_EMAIL_BAD_SHAPE),
});
type Values = z.infer<typeof schema>;

/**
 * Spec 052: invitar, reenviar y revocar al propietario desde la pestaña Equipo.
 *
 * **Mientras hay un enlace en pantalla no se refresca nada ni se ofrece nada más.**
 * Es el único ejemplar: refrescar puede fallar y desmontar la pestaña, y una
 * negativa en otra fila se lo llevaría por delante. Se refresca al salir, y
 * también tras cualquier aviso, cuando ya no hay enlace que perder.
 *
 * Lo que no se puede hacer no se pinta apagado: se dice por qué y dónde se resuelve
 * (constitución §V).
 */
export function OwnerInvitationPanel({
  partnerId,
  partnerName,
  owner,
  invitations,
  expiredOn,
}: {
  partnerId: string;
  partnerName: string;
  owner: PartnerOwnerState;
  invitations: AuphereInvitationRow[];
  expiredOn: string | null;
}) {
  const router = useRouter();
  const [shown, setShown] = useState<Shown | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const noticeRef = useRef<HTMLDivElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  // La fila de la que venía el foco puede haber desaparecido.
  useEffect(() => {
    if (notice) noticeRef.current?.focus();
  }, [notice]);

  function show(result: OwnerInvitationResult, replaced: boolean) {
    setNotice(null);
    setShown({ result, replaced });
  }

  function say(next: Notice) {
    setShown(null);
    setNotice(next);
    router.refresh();
  }

  function leaveResult() {
    setShown(null);
    router.refresh();
    // El botón desaparece con la vista: el foco no se queda en el vacío.
    wrapRef.current?.focus();
  }

  const nothingToSay = owner.has_active_owner && invitations.length === 0 && !shown && !notice;
  if (nothingToSay) return null;

  const content = shown ? (
    <Section title="Propietario">
      <InvitationResult
        partnerId={partnerId}
        partnerName={partnerName}
        result={shown.result}
        replacedPrevious={shown.replaced}
        onReplaced={(next) => show(next, true)}
        onDead={(message) => say({ tone: "info", text: message })}
      >
        <Button type="button" variant="outline" onClick={leaveResult}>
          Entendido
        </Button>
      </InvitationResult>
    </Section>
  ) : (
    <Section
      title="Propietario"
      description={
        owner.has_active_owner
          ? "Ya tiene propietario activo: su equipo lo gestiona él."
          : "Quién administra la consola de este partner. Todavía no ha entrado nadie con ese rol."
      }
    >
      {notice ? (
        <div
          ref={noticeRef}
          tabIndex={-1}
          className="rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          <Callout tone={notice.tone}>
            <span className="wrap-anywhere">{notice.text}</span>
          </Callout>
        </div>
      ) : null}

      {invitations.length > 0 ? (
        <LiveInvitations
          partnerId={partnerId}
          owner={owner}
          invitations={invitations}
          onResent={(result) => show(result, true)}
          onNotice={say}
        />
      ) : null}

      {owner.expired_email ? (
        <Callout tone="warning" title="La invitación caducó">
          <span className="wrap-anywhere">
            La invitación a {owner.expired_email} caducó el {expiredOn}, y su enlace ya no sirve.
          </span>
        </Callout>
      ) : null}

      {!owner.has_active_owner && invitations.length === 0 ? (
        <BlockedInvite partnerId={partnerId} block={owner.block} />
      ) : null}

      {owner.can_invite ? (
        <InviteForm
          key={owner.suggested_email ?? ""}
          partnerId={partnerId}
          suggested={owner.suggested_email}
          fromExpired={Boolean(owner.expired_email)}
          onResult={(result) => show(result, false)}
          onNotice={say}
        />
      ) : null}
    </Section>
  );

  return (
    <div ref={wrapRef} tabIndex={-1} className="min-w-0 rounded-md">
      {content}
    </div>
  );
}

function BlockedInvite({ partnerId, block }: { partnerId: string; block: PartnerOwnerState["block"] }) {
  if (block === "console_off") {
    return (
      <Callout tone="warning" title="La consola de este partner está apagada">
        Hay que encenderla en <Link href={`/partners/${partnerId}/modules`}>Módulos</Link> para poder invitar a su
        propietario.
      </Callout>
    );
  }
  if (block === "suspended") {
    return (
      <Callout tone="warning" title="Este partner está suspendido">
        No se puede invitar a su propietario mientras siga así.
      </Callout>
    );
  }
  return null;
}

function resendBlockedReason(partnerId: string, owner: PartnerOwnerState): ReactNode {
  if (owner.can_resend) return null;
  if (owner.has_active_owner) {
    return (
      <Callout tone="info">
        Este partner ya tiene propietario activo: esta invitación se puede revocar, pero no reenviar.
      </Callout>
    );
  }
  if (owner.block === "console_off") {
    return (
      <Callout tone="warning" title="La consola de este partner está apagada">
        Quien acepte ahora verá que no tiene acceso. Para poder reenviar, enciéndela en{" "}
        <Link href={`/partners/${partnerId}/modules`}>Módulos</Link>. Revocar sigue disponible.
      </Callout>
    );
  }
  return (
    <Callout tone="warning" title="Este partner está suspendido">
      Quien acepte ahora verá que no tiene acceso, y no se puede reenviar. Revocar sigue disponible.
    </Callout>
  );
}

function LiveInvitations({
  partnerId,
  owner,
  invitations,
  onResent,
  onNotice,
}: {
  partnerId: string;
  owner: PartnerOwnerState;
  invitations: AuphereInvitationRow[];
  onResent: (result: OwnerInvitationResult) => void;
  onNotice: (notice: Notice) => void;
}) {
  const [pending, start] = useTransition();
  const [resending, setResending] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<AuphereInvitationRow | null>(null);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  function resend(row: AuphereInvitationRow) {
    setResending(row.id);
    start(async () => {
      const r = await resendOwnerInvitationAction(partnerId, row.id);
      setResending(null);
      if (r.ok) {
        onResent(r.data);
        return;
      }
      onNotice({ tone: r.code && DEAD_INVITATION_CODES.has(r.code) ? "info" : "danger", text: r.error });
    });
  }

  async function revoke() {
    if (!revoking) return;
    const row = revoking;
    setRevokeError(null);
    const r = await revokeOwnerInvitationAction(partnerId, row.id);
    if (!r.ok) {
      if (r.code && DEAD_INVITATION_CODES.has(r.code)) {
        setRevoking(null);
        onNotice({ tone: "info", text: r.error });
        return;
      }
      setRevokeError(r.error);
      return;
    }
    setRevoking(null);
    onNotice(
      r.data.changed
        ? {
            tone: "positive",
            text: `Invitación a ${r.data.email} revocada: ese enlace ya no sirve. A esa persona no se le ha avisado.`,
          }
        : {
            // Puede que otra persona acabe de reenviarla: entonces hay otro
            // enlace vivo, y decir que «ya no sirve» sería falso.
            tone: "info",
            text: "Esa invitación ya no estaba viva, así que no ha cambiado nada. Revisa abajo si queda otra.",
          },
    );
  }

  return (
    <div className="grid min-w-0 gap-3">
      {resendBlockedReason(partnerId, owner)}
      <ul className="grid min-w-0 gap-3">
        {invitations.map((row) => (
          <li
            key={row.id}
            className="flex min-w-0 flex-wrap items-start justify-between gap-3 rounded-md border border-border p-3"
          >
            <div className="grid min-w-0 flex-1 basis-56 gap-1">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="min-w-0 font-medium wrap-anywhere">{row.email}</span>
                {row.sentAgo ? (
                  <StatusBadge tone="positive">Enviada {row.sentAgo}</StatusBadge>
                ) : (
                  <StatusBadge tone="warning">No consta el envío</StatusBadge>
                )}
              </div>
              <p className="text-sm text-muted-foreground">Propietario · caduca el {row.expiresOn}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {owner.can_resend ? (
                <Button type="button" variant="outline" size="sm" onClick={() => resend(row)} loading={resending === row.id} disabled={pending}>
                  {resending === row.id ? "Reenviando…" : "Reenviar"}
                </Button>
              ) : null}
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={pending}
                onClick={() => {
                  setRevokeError(null);
                  setRevoking(row);
                }}
              >
                Revocar
              </Button>
            </div>
          </li>
        ))}
      </ul>
      <p className="text-xs text-pretty text-muted-foreground">
        «Enviada» quiere decir que el proveedor de correo la aceptó: no sabemos si ha llegado a su bandeja.
      </p>
      {resending ? (
        <p role="status" className="text-xs text-pretty text-muted-foreground">
          {SENDING_HINT}
        </p>
      ) : null}
      <ConfirmDialog
        open={revoking !== null}
        onOpenChange={(open) => {
          if (!open) setRevoking(null);
        }}
        title="¿Revocar esta invitación?"
        description={
          <span className="wrap-anywhere">
            El enlace enviado a {revoking?.email} dejará de servir al momento. A esa persona no se le avisa.
          </span>
        }
        confirmLabel="Revocar invitación"
        cancelLabel="Cancelar"
        destructive
        error={revokeError}
        onConfirm={revoke}
      />
    </div>
  );
}

function InviteForm({
  partnerId,
  suggested,
  fromExpired,
  onResult,
  onNotice,
}: {
  partnerId: string;
  suggested: string | null;
  fromExpired: boolean;
  onResult: (result: OwnerInvitationResult) => void;
  onNotice: (notice: Notice) => void;
}) {
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { email: suggested ?? "" } });

  async function onSubmit(values: Values) {
    const r = await inviteOwnerAction(partnerId, values.email);
    if (r.ok) {
      onResult(r.data);
      return;
    }
    if (r.code && FIELD_OF_CODE[r.code] === "email") {
      form.setError("email", { message: r.error }, { shouldFocus: true });
      return;
    }
    onNotice({ tone: "danger", text: r.error });
  }

  let hint = "Recibirá una invitación como propietaria. Vale 21 días.";
  if (suggested && fromExpired) hint = `Es la dirección de la invitación caducada. Revísala: no sale nada hasta que pulses «Invitar». ${hint}`;
  else if (suggested) hint = `Es el correo de contacto del partner. Revísalo: no sale nada hasta que pulses «Invitar». ${hint}`;

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="grid min-w-0 gap-3" noValidate>
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem className="md:max-w-sm">
              <FormLabel>Correo del propietario</FormLabel>
              <FormControl>
                <Input {...field} type="email" inputMode="email" autoComplete="off" placeholder="persona@negocio.com" />
              </FormControl>
              <FormDescription>{hint}</FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />
        <div>
          <Button type="submit" loading={form.formState.isSubmitting}>
            {form.formState.isSubmitting ? "Invitando…" : "Invitar"}
          </Button>
        </div>
        {form.formState.isSubmitting ? (
          <p role="status" className="text-xs text-pretty text-muted-foreground">
            {SENDING_HINT}
          </p>
        ) : null}
      </form>
    </Form>
  );
}
