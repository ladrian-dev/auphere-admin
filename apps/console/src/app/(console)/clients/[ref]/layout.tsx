import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { formatDate, PageHeader } from "@nexus/ui";

import { ClientStatusBadge } from "@/components/clients/status-badge";
import { ClientNav } from "@/components/clients/client-nav";
import { ClientSetup } from "@/components/clients/client-setup";
import { DraftBarClient } from "@/components/clients/draft-bar-client";
import { ClientLifecycleActions } from "@/components/clients/lifecycle-actions";
import { getT } from "@/i18n/server";
import { BackendError } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

import { getAgentBundleCached, getClientCached } from "./data";

export async function generateMetadata({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  const client = await getClientCached(principal, ref).catch(() => null);
  const { t } = await getT();
  return { title: client?.name ?? t("clients.one") };
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
  // Solo quien puede leer el agente puede saber que hay un borrador.
  const bundle = can(principal.role, "agents:read") ? await getAgentBundleCached(principal, ref) : null;
  return (
    <>
      <PageHeader
        context={
          <nav aria-label="Breadcrumb" className="text-xs">
            <Link href="/clients" className="underline decoration-muted-foreground/50 underline-offset-4 hover:text-foreground">
              {t("nav.clients")}
            </Link>
            <span aria-hidden="true"> / </span>
            <span className="text-foreground">{client.name}</span>
          </nav>
        }
        title={client.name}
        /* Spec 017 R1.6: un solo «Más», en el mismo sitio para todos los
           roles; dentro, solo lo que quien mira puede hacer. */
        actions={
          <ClientLifecycleActions
            layout="menu"
            refId={client.external_client_ref}
            status={client.status}
            name={client.name}
            canWrite={can(principal.role, "clients:write")}
            canDelete={can(principal.role, "clients:delete")}
          />
        }
        description={
          <span className="flex flex-wrap items-center gap-2">
            <ClientStatusBadge status={client.status} locale={locale} />
            {/* Paridad fila 22: solo cuando de verdad atiende. */}
            {client.serving_since ? (
              <span className="text-sm text-muted-foreground">
                {t("clients.servingSince", { date: formatDate(client.serving_since, locale) })}
              </span>
            ) : null}
            {client.health.display_phone_number ? (
              <span className="text-sm text-muted-foreground">{client.health.display_phone_number}</span>
            ) : null}
          </span>
        }
      />
      {/* Spec 017 R1: qué falta para que atienda, con UN solo botón, y el
          crédito al lado. Cuando ya atiende, la puesta en marcha se va. */}
      <ClientSetup
        refId={client.external_client_ref}
        name={client.name}
        status={client.status}
        role={principal.role}
        setup={client.setup ?? null}
        quota={client.quota ?? null}
        agentVersion={client.health.agent_version}
        phone={client.health.display_phone_number}
      />
      {/* Spec 017 R2/R3.1: tres grupos por rol, y un punto en la pestaña
          donde vive lo que aún no se ha publicado o lo que está roto. */}
      <ClientNav
        refId={client.external_client_ref}
        role={principal.role}
        draftScreens={bundle?.draft_screens ?? []}
        incidents={client.health.whatsapp_connected ? [] : ["channels"]}
      />
      {/* Spec 017 R3: el borrador se ve y se publica desde cualquier
          pestaña. Sin versión no hay nada que publicar. */}
      {/* Se monta siempre que haya agente, aunque no haya borrador: así el
          aviso de «publicado» sobrevive al refresco y su ventana de
          deshacer corre entera. Sin nada que decir, no pinta nada. */}
      {bundle && bundle.versions[0] ? (
        <DraftBarClient
          refId={client.external_client_ref}
          screens={bundle.draft_screens}
          version={bundle.versions[0].version}
          activeVersion={bundle.active_version}
          canPublish={can(principal.role, "agents:write")}
        />
      ) : null}
      {children}
    </>
  );
}
