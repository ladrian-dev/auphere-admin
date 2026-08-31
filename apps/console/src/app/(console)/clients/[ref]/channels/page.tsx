import { Stethoscope, MessageCircle } from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import { Alert, AlertDescription, AlertTitle, Button, EmptyState } from "@nexus/ui";

import { ChannelCard } from "@/components/channels/channel-card";
import { TemplatesSection } from "@/components/channels/templates-section";
import { f2ChannelCounter, f2VisibleChannels } from "@/components/channels/visible-channels";
import { WhatsAppConnectUnavailable } from "@/components/channels/whatsapp-connect-unavailable";
import { getT } from "@/i18n/server";
import { BackendError, backendFor } from "@/lib/backend";
import type { TemplateList } from "@/lib/backend/channels";
import { can, requirePrincipal } from "@/lib/principal";

/**
 * Channels centre (CP-17/18). F2: WhatsApp cards only; Connect CTA disabled
 * (no Embedded Signup). Quality + roles, templates, diagnostics link.
 * Templates with Meta's literal rejection reason and a link to diagnostics.
 */
export default async function ChannelsPage({ params }: { params: Promise<{ ref: string }> }) {
  const { ref } = await params;
  const principal = await requirePrincipal();
  if (!can(principal.role, "channels:read")) redirect(`/clients/${ref}`);
  const { t } = await getT(principal.locale);
  const manage = can(principal.role, "channels:write");
  const api = backendFor(principal);

  const overview = await api.channelsOverview(ref);
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
  const connect = <WhatsAppConnectUnavailable used={n} />;

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
      {overview.roles_required ? (
        <Alert>
          <AlertTitle>{t("ch.roles.required.title")}</AlertTitle>
          <AlertDescription>{t("ch.roles.required.body")}</AlertDescription>
        </Alert>
      ) : null}
      {visible.length === 0 ? (
        <EmptyState icon={MessageCircle} title={t("ch.empty.title")} description={t("ch.empty.description")} action={manage ? connect : undefined} readonly={!manage} />
      ) : (
        <ul className="grid gap-3 md:grid-cols-2" aria-label={t("ch.title")}>
          {visible.map((ch) => (
            <ChannelCard key={ch.id} refId={ref} channel={ch} manage={manage} showRoles={visible.filter((c) => c.status === "active").length > 1} />
          ))}
        </ul>
      )}
      <TemplatesSection refId={ref} list={templates} error={templatesError} manage={manage} />
    </div>
  );
}
