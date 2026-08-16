import { PageHeader } from "@nexus/ui";

import { NotificationsList } from "@/components/notifications/notifications-list";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { requirePrincipal } from "@/lib/principal";

export const metadata = { title: "Notificaciones" };

/** Notification centre (CP-29). Every member of the partner may read (partner:read). */
export default async function NotificationsPage({ searchParams }: { searchParams: Promise<{ unread?: string }> }) {
  const principal = await requirePrincipal("/notifications");
  const { t } = await getT(principal.locale);
  const sp = await searchParams;
  const unreadOnly = sp.unread === "1" || sp.unread === "true";
  const page = await backendFor(principal).listNotifications({ unread: unreadOnly ? true : undefined, limit: 20 });
  return (
    <>
      <PageHeader eyebrow={principal.partnerName} title={t("notif.title")} description={t("notif.subtitle")} />
      <NotificationsList initial={page} initialFilter={unreadOnly ? "unread" : "all"} />
    </>
  );
}
