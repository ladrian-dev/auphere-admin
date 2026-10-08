import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { formatDate, PageHeader } from "@nexus/ui";

import { AgentDraftBars, type AgentDraft } from "@/components/clients/agent-draft-bars";
import { AgentSwitcher } from "@/components/clients/agent-switcher";
import { ClientStatusBadge } from "@/components/clients/status-badge";
import { ClientNav } from "@/components/clients/client-nav";
import { ClientSetup } from "@/components/clients/client-setup";
import { DraftBarClient } from "@/components/clients/draft-bar-client";
import { ClientLifecycleActions } from "@/components/clients/lifecycle-actions";
import { getT } from "@/i18n/server";
import { BackendError } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { getAgentBundleCached, getAgentsCached, getClientCached } from "./data";

export async function generateMetadata({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal();
  const client = await getClientCached(principal, ref).catch(() => null);
  const { t } = await getT();
  return { title: client?.name ?? t("clients.one") };
}

export default async function ClientLayout({ params, children }: { params: Promise<{ ref: string }>; children: React.ReactNode }) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal(`/clients/${ref}`);
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
  const readsAgents = can(principal.role, "agents:read");
  const [bundle, agents] = readsAgents
    ? await Promise.all([getAgentBundleCached(principal, ref), getAgentsCached(principal, ref)])
    : [null, null];
  // Spec 030: con varios agentes, cada uno tiene su borrador. El layout no ve
  // la URL, así que lee todos y la barra elige el del agente de `?agent=`.
  const drafts: AgentDraft[] | null =
    agents && agents.length > 1
      ? await Promise.all(
          agents.map(async (a) => {
            const b = a.is_principal ? bundle : await getAgentBundleCached(principal, ref, a.id);
            return {
              agentId: a.id,
              isPrincipal: a.is_principal,
              screens: b?.draft_screens ?? [],
              version: b?.versions[0]?.version ?? null,
              activeVersion: b?.active_version ?? null,
            };
          }),
        )
      : null;
  const draftScreens = drafts ? [...new Set(drafts.flatMap((d) => d.screens))] : (bundle?.draft_screens ?? []);
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
          <>
            {/* El estado, a la altura del nombre y junto a «Más» (owner,
                2026-09-28). Se queda como insignia —sin hover ni borde de
                botón— para que no se lea como un control más del grupo. */}
            <ClientStatusBadge status={client.status} locale={locale} />
            <ClientLifecycleActions
              layout="menu"
              refId={client.external_client_ref}
              status={client.status}
              name={client.name}
              canWrite={can(principal.role, "clients:write")}
              canDelete={can(principal.role, "clients:delete")}
            />
          </>
        }
        description={
          <span className="flex flex-wrap items-center gap-2">
            {/* Paridad fila 22: solo cuando de verdad atiende. */}
            {client.serving_since ? (
              <span className="text-sm text-muted-foreground">
                {t("clients.servingSince", { date: formatDate(client.serving_since, locale) })}
              </span>
            ) : null}
            {client.health.display_phone_number ? (
              <span className="text-sm text-muted-foreground">{client.health.display_phone_number}</span>
            ) : null}
            {/* Spec 024 (Requisito 3.1): un agente limitado a una lista lo dice
                aquí, con el camino a donde se cambia. */}
            {client.audience?.mode === "list" ? (
              <Link
                href={`/clients/${encodeURIComponent(ref)}/agent`}
                className="text-sm text-muted-foreground underline-offset-4 hover:underline"
                data-slot="client-audience"
              >
                {t("clients.audience.only", { n: client.audience.count })}
              </Link>
            ) : null}
          </span>
        }
      />
      {/* Spec 018 (R6): qué falta para que atienda, con UN solo botón —y
          nada más—. El crédito se fue al Resumen: compartir fila con los
          cuatro pasos es lo que hacía esta tarjeta pesada, y además el
          crédito le sobrevive. Cuando ya atiende, esto desaparece. */}
      <ClientSetup
        refId={client.external_client_ref}
        name={client.name}
        status={client.status}
        role={principal.role}
        setup={client.setup ?? null}
        quota={client.quota ?? null}
        hasAgentVersion={Boolean(bundle?.versions?.length)}
        draftScreens={bundle?.draft_screens?.length ?? 0}
        agentVersion={client.health.agent_version}
        phone={client.health.display_phone_number}
      />
      {/* Spec 017 R2/R3.1: tres grupos por rol, y un punto en la pestaña
          donde vive lo que aún no se ha publicado o lo que está roto. */}
      <ClientNav
        refId={client.external_client_ref}
        role={principal.role}
        draftScreens={draftScreens}
        incidents={client.health.whatsapp_connected ? [] : ["channels"]}
      />
      {/* Spec 030: en las pestañas de UN agente, de cuál —y «Nuevo agente»—. */}
      {readsAgents ? (
        <AgentSwitcher refId={client.external_client_ref} agents={agents ?? []} canWrite={can(principal.role, "agents:write")} />
      ) : null}
      {/* Spec 017 R3: el borrador se ve y se publica desde cualquier
          pestaña. Sin versión no hay nada que publicar. */}
      {/* Se monta siempre que haya agente, aunque no haya borrador: así el
          aviso de «publicado» sobrevive al refresco y su ventana de
          deshacer corre entera. Sin nada que decir, no pinta nada. */}
      {drafts ? (
        <AgentDraftBars refId={client.external_client_ref} drafts={drafts} canPublish={can(principal.role, "agents:write")} />
      ) : bundle && bundle.versions[0] ? (
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
