import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { PageHeader } from "@nexus/ui";

import { ClientStatusBadge } from "@/components/clients/status-badge";
import { ClientTabs } from "@/components/clients/client-tabs";
import { getT } from "@/i18n/server";
import { BackendError } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

import { getClientCached } from "./data";

export async function generateMetadata({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  const client = await getClientCached(principal, ref).catch(() => null);
  return { title: client?.name ?? "Cliente" };
}

export default async function ClientLayout({ params, children }: { params: Promise<{ ref: string }>; children: React.ReactNode }) {
  const { ref } = await params;
  const principal = await requirePrincipal(`/clients/${ref}`);
  if (!can(principal.role, "clients:read")) redirect("/");
  const { t, locale } = await getT(principal.locale);
  let client;
  try {
    client = await getClientCached(principal, ref);
  } catch (err) {
    if (err instanceof BackendError && err.status === 404) notFound();
    throw err;
  }
  return (
    <>
      <PageHeader
        context={
          <nav aria-label="Breadcrumb" className="font-mono text-xs uppercase">
            <Link href="/clients" className="hover:underline">
              {t("nav.clients")}
            </Link>
            <span aria-hidden="true"> / </span>
            <span className="text-foreground">{client.external_client_ref}</span>
          </nav>
        }
        title={client.name}
        description={
          <span className="flex flex-wrap items-center gap-2">
            <ClientStatusBadge status={client.status} locale={locale} />
            <span className="font-mono text-xs">{client.timezone}</span>
            {client.health.display_phone_number ? <span className="font-mono text-xs">{client.health.display_phone_number}</span> : null}
          </span>
        }
      />
      <ClientTabs refId={client.external_client_ref} />
      {children}
    </>
  );
}
