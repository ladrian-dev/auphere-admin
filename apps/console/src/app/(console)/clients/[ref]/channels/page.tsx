import { Stethoscope, MessageCircle } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Alert, AlertDescription, AlertTitle, Button, EmptyState } from "@nexus/ui";

import { ChannelsList } from "@/components/channels/channels-list";
import { TemplatesSection } from "@/components/channels/templates-section";
import { f2ChannelCounter, f2VisibleChannels } from "@/components/channels/visible-channels";
import { connectChoice, metaSignupConfig } from "@/components/channels/connect-choice";
import { MetaSocialConnect } from "@/components/channels/meta-social-connect";
import { WhatsAppConnect } from "@/components/channels/whatsapp-connect";
import { PendingSignupLinks } from "@/components/channels/pending-signup-links";
import { WhatsAppShareLink } from "@/components/channels/whatsapp-share-link";
import { WhatsAppConnectByAuphere } from "@/components/channels/whatsapp-connect-by-auphere";
import { WhatsAppContinueInBrowser } from "@/components/channels/whatsapp-continue-in-browser";
import { getT } from "@/i18n/server";
import { BackendError, backendFor } from "@/lib/backend";
import type { TemplateList } from "@/lib/backend/channels";
import { env } from "@/lib/env";
import { can, requirePartnerPrincipal } from "@/lib/principal";
import { isDesktopShell } from "@/lib/shell";

import { agentChoice } from "../data";

/**
 * Channels centre (CP-17/18). WhatsApp cards, quality + roles, templates,
 * diagnostics link. Spec 016 (R1): the real Embedded Signup button when the
 * environment has Meta configured; the «lo conecta Auphere» note when it
 * does not; «continue in the browser» inside the desktop shell.
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
  const liveLink = signupLinks.some((l) => l.state === "valid");
  // Spec 030: who answers on each number — its agent, or the principal.
  const principalAgent = agents.find((a) => a.is_principal)?.id;
  const agentOf: Record<string, string> = {};
  for (const ch of overview.channels) {
    const owner = agents.find((a) => a.channels.some((c) => c.id === ch.id))?.id ?? principalAgent;
    if (owner) agentOf[ch.id] = owner;
  }
  // Spec 049: Instagram / Messenger exist on this page only for the partners
  // Auphere switched on — the API sends `meta_social` to nobody else.
  const social = overview.meta_social ?? null;
  const visible = f2VisibleChannels(overview.channels, social ? social.channels.map((c) => c.kind) : []);
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
  // Spec 002, R12.7: dentro de la aplicación de escritorio la ventana emergente
  // de Meta no vuelve, así que el control **no existe** ahí y en su lugar se
  // ofrece continuar en el navegador. Es la única bifurcación por cáscara de
  // toda la consola; `shell-detect.test.ts` lo vigila.
  const meta = metaSignupConfig(env());
  const choice = connectChoice({ manage, meta });
  // Spec 040: the link the business owner opens on their own device. It works
  // in the desktop app too, where Meta's popup does not.
  const linkModes = [
    ...(meta.configIdCoexistence ? (["coexistence"] as const) : []),
    ...(meta.configIdCloudApi ? (["cloud_api"] as const) : []),
  ];
  const share =
    choice === "connect" ? (
      <WhatsAppShareLink
        refId={ref}
        modes={linkModes}
        disabled={!overview.can_connect}
        hasLive={liveLink}
        fromPhone={env().NEXUS_OWNER_LINK_FROM_PHONE}
      />
    ) : null;
  const connect = (await isDesktopShell()) ? (
    <div className="flex flex-wrap items-center gap-2">
      <WhatsAppContinueInBrowser href={`${base}/channels`} />
      {share}
    </div>
  ) : choice === "connect" ? (
    <div className="flex flex-wrap items-center gap-2">
      <WhatsAppConnect refId={ref} meta={meta} canConnect={overview.can_connect} used={n} max={m} />
      {share}
    </div>
  ) : choice === "by_auphere" ? (
    <WhatsAppConnectByAuphere />
  ) : null;

  const socialConnect =
    manage && social && !(await isDesktopShell()) ? (
      <>
        {social.channels.map((c) => (
          <MetaSocialConnect key={c.kind} refId={ref} offer={social} kind={c.kind} />
        ))}
      </>
    ) : null;

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
          {visible.length > 0 ? socialConnect : null}
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
            action={
              manage ? (
                <div className="flex flex-wrap items-center justify-center gap-2">
                  {connect}
                  {socialConnect}
                </div>
              ) : undefined
            }
            readonly={!manage}
          />
        }
      />
      <TemplatesSection refId={ref} list={templates} error={templatesError} manage={manage} />
    </div>
  );
}
