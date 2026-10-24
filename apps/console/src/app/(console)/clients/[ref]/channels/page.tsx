import { MessageCircle, Plus, Stethoscope } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Alert, AlertDescription, AlertTitle, Button, EmptyState } from "@nexus/ui";

import { ChannelsList } from "@/components/channels/channels-list";
import { TemplatesSection } from "@/components/channels/templates-section";
import { f2ChannelCounter, f2VisibleChannels } from "@/components/channels/visible-channels";
import { PendingSignupLinks } from "@/components/channels/pending-signup-links";
import { getT } from "@/i18n/server";
import { BackendError, backendFor } from "@/lib/backend";
import type { TemplateList } from "@/lib/backend/channels";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { agentChoice } from "../data";

/**
 * Channels centre (CP-17/18). WhatsApp cards, quality + roles, templates,
 * diagnostics link. Spec 046: «Añadir canal» opens the wizard
 * (`channels/new`), where Meta's window, the link to the owner and the
 * desktop app's «continue in the browser» live (spec 016 R1, spec 040).
 */
export default async function ChannelsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePartnerPrincipal();
  if (!can(principal.role, "channels:read")) redirect(`/clients/${ref}`);
  const { t } = await getT(principal.locale);
  const manage = can(principal.role, "channels:write");
  const api = backendFor(principal);

  const [overview, { agents }, signupLinks] = await Promise.all([
    api.channelsOverview(ref),
    agentChoice(principal, ref, undefined),
    // Spec 040 (owner, 2026-10-20): the link sent to the owner, if one still
    // works. A read that fails hides the line; the page does not depend on it.
    api.whatsappSignupLinks(ref).catch(() => []),
  ]);
  // Spec 030: who answers on each number — its agent, or the principal.
  const principalAgent = agents.find((a) => a.is_principal)?.id;
  const agentOf: Record<string, string> = {};
  for (const ch of overview.channels) {
    const owner = agents.find((a) => a.channels.some((c) => c.id === ch.id))?.id ?? principalAgent;
    if (owner) agentOf[ch.id] = owner;
  }
  const visible = f2VisibleChannels(overview.channels);
  const { n, m } = f2ChannelCounter(overview.channels);
  // Templates are a partial state: a 409 (not connected) is "no list", any
  // other failure is shown inline with retry — the cards still render.
  let templates: TemplateList | null = null;
  let templatesError: string | null = null;
  if (overview.meta_connected) {
    try {
      templates = await api.listTemplates(ref);
    } catch (err) {
      if (err instanceof BackendError && err.status === 409) templates = null;
      else if (err instanceof BackendError) templatesError = t("common.error.backend");
      else throw err;
    }
  }
  const base = `/clients/${encodeURIComponent(ref)}`;
  // Spec 046: connecting is the «Añadir canal» wizard — the same four steps
  // as the operator panel. The link to the owner, Meta's window and the
  // desktop app's «continue in the browser» live in its step 2 now.
  const connect = overview.can_connect ? (
    <Button nativeButton={false} render={<Link href={`${base}/channels/new`} />}>
      <Plus aria-hidden="true" />
      {t("chw.add")}
    </Button>
  ) : (
    <p className="max-w-xs text-xs text-muted-foreground text-pretty">{t("ch.quota.full", { used: n, max: m })}</p>
  );

  return (
    <div className="flex min-w-0 flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex flex-col gap-1">
          <h1 className="text-base font-medium">{t("ch.title")}</h1>
          <p className="text-xs text-muted-foreground tabular-nums">{t("ch.quota", { used: n, max: m })}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button nativeButton={false} render={<Link href={`${base}/channels/diagnostics`} />} variant="outline" size="sm">
            <Stethoscope aria-hidden="true" />
            {t("ch.links.diagnostics")}
          </Button>
          {manage && visible.length > 0 ? connect : null}
        </div>
      </div>
      {!manage ? <p className="text-xs text-muted-foreground">{t("ch.forbidden.write")}</p> : null}
      <PendingSignupLinks refId={ref} links={signupLinks} manage={manage} />
      {overview.roles_required ? (
        <Alert>
          <AlertTitle>{t("ch.roles.required.title")}</AlertTitle>
          <AlertDescription>{t("ch.roles.required.body")}</AlertDescription>
        </Alert>
      ) : null}
      {/* Spec 018 (R4): el mismo patrón de navegación que Habilidades y
          Conectores. Los canales que todavía no se pueden conectar no están
          en `visible`, así que tampoco están en la lista: §V, la ausencia se
          diseña y no se enseña apagada. */}
      <ChannelsList
        refId={ref}
        channels={visible}
        manage={manage}
        agents={agents}
        agentOf={agentOf}
        empty={
          <EmptyState
            icon={MessageCircle}
            title={t("ch.empty.title")}
            description={t("ch.empty.description")}
            action={manage ? connect : undefined}
            readonly={!manage}
          />
        }
      />
      <TemplatesSection refId={ref} list={templates} error={templatesError} manage={manage} />
    </div>
  );
}
