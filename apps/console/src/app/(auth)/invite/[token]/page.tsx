import { EmptyState, formatDate } from "@nexus/ui";

import { roleKey } from "@/i18n/messages";
import { getT } from "@/i18n/server";
import { consoleService } from "@/lib/backend";
import { getSession } from "@/lib/session";

import { AcceptForm } from "./accept-form";

export const metadata = { title: "Invitación" };

export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const { t, locale } = await getT();
  const invitation = /^[A-Za-z0-9_-]{16,128}$/.test(token) ? await consoleService.lookupInvitation(token) : null;
  if (!invitation) {
    return <EmptyState title={t("invite.invalid")} description={t("invite.invalid.body")} readonly />;
  }
  const session = await getSession();
  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">{t("invite.title")}</h1>
        <p className="text-pretty text-muted-foreground">
          {t("invite.body", { partner: invitation.partner_name, role: t(roleKey(invitation.role)) })}
        </p>
        <p className="text-sm text-muted-foreground">
          {t("invite.expires", { date: formatDate(invitation.expires_at, locale) })}
        </p>
      </div>
      <AcceptForm
        token={token}
        email={invitation.email}
        alreadySignedInAs={session?.user.email ?? null}
      />
    </section>
  );
}
