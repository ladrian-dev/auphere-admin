"use client";

import { Copy } from "lucide-react";
import { toast } from "sonner";

import { Button, Callout, Input } from "@nexus/ui";
import type { ClientInvitationOut } from "@/lib/backend";
import { fullDateTime } from "@/lib/format";

/**
 * What came of each invitation sent from this page: whether the e-mail went out
 * and the link to pass on by hand. It is the only moment the link exists in the
 * clear, so it lives in this page's memory and never in its address.
 *
 * A notice stays until the operator closes it, or until a new link or a
 * revocation kills the one it shows. A failure is an alert, never a toast: a
 * toast is gone before anyone can act on it.
 *
 * The link sits outside the live region on purpose: a screen reader announces
 * the sentence and the operator reaches the link with the keyboard, instead of
 * having a token spelled out.
 */
export function InvitationNotices({
  notices,
  onDismiss,
}: {
  notices: ClientInvitationOut[];
  onDismiss: (email: string) => void;
}) {
  if (notices.length === 0) return null;
  return (
    <div className="grid min-w-0 gap-3">
      {notices.map((invitation) => (
        <Notice key={invitation.id} invitation={invitation} onDismiss={() => onDismiss(invitation.email)} />
      ))}
    </div>
  );
}

function Notice({ invitation, onDismiss }: { invitation: ClientInvitationOut; onDismiss: () => void }) {
  const { email, accept_url: url, email_sent: sent } = invitation;
  const until = fullDateTime(invitation.expires_at);

  async function copy() {
    try {
      await navigator.clipboard.writeText(url);
      toast.success("Enlace copiado");
    } catch {
      toast.error("No se pudo copiar: selecciona el enlace a mano");
    }
  }

  return (
    <div className="grid min-w-0 gap-2">
      <Callout
        tone={sent ? "positive" : "warning"}
        title={<span className="break-words">{sent ? `Invitación enviada a ${email}` : `El correo a ${email} no salió`}</span>}
        dismissible
        dismissLabel={`Cerrar el aviso de ${email}`}
        onDismiss={onDismiss}
      >
        {sent
          ? `Si no le llega, pásale este enlace. Vale hasta el ${until} y no se volverá a mostrar.`
          : `La invitación está creada y este enlace vale hasta el ${until}: pásaselo por otro medio o pulsa Reenviar para intentarlo con uno nuevo. No se volverá a mostrar: si recargas la página, tendrás que reenviar.`}
      </Callout>
      <div className="flex min-w-0 gap-2">
        <Input
          readOnly
          value={url}
          aria-label={`Enlace de invitación de ${email}`}
          className="min-w-0 flex-1 font-mono text-xs"
          onFocus={(e) => e.currentTarget.select()}
        />
        <Button type="button" variant="outline" onClick={copy} aria-label={`Copiar el enlace de ${email}`}>
          <Copy aria-hidden="true" />
          Copiar
        </Button>
      </div>
    </div>
  );
}
