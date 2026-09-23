import { PageHeader } from "@nexus/ui";

import { NotificationsList } from "@/components/notifications/notifications-list";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";
import { pageTitle } from "@/i18n/metadata";

export const generateMetadata = () => pageTitle("nav.notifications");

/** Notification centre (CP-29). Every member of the partner may read (partner:read). */
export default async function NotificationsPage({ searchParams }: { searchParams: Promise<{ unread?: string }> }) {
  const principal = await requirePrincipal("/notifications");
  const { t } = await getT(principal.locale);
  const sp = await searchParams;
  const unreadOnly = sp.unread === "1" || sp.unread === "true";
  const api = backendFor(principal);
  const [page, clients] = await Promise.all([
    api.listNotifications({ unread: unreadOnly ? true : undefined, limit: 20 }),
    can(principal.role, "clients:read") ? api.listClients({ limit: 200 }).catch(() => null) : null,
  ]);
  const clientNames = Object.fromEntries((clients?.items ?? []).map((c) => [c.external_client_ref, c.name]));
  return (
    <>
      <PageHeader eyebrow={principal.partnerName} title={t("notif.title")} description={t("notif.subtitle")} />
      <NotificationsList initial={page} initialFilter={unreadOnly ? "unread" : "all"} clientNames={clientNames} />
    </>
  );
}
