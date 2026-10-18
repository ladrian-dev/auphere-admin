import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Eyebrow, Separator, StatusDot } from "@nexus/ui";
import { backend } from "@/lib/backend";
import { getImpersonateSessionId } from "@/lib/impersonate";
import { matchImpersonationBanner } from "@/lib/impersonate-cookie";
import { getOperator } from "@/lib/session";
import { formatCents, statusLabel } from "@/lib/format";

import { ImpersonateBannerView } from "./impersonate-banner";
import { PartnerTabs } from "./tabs";

const STATUS_TONE = {
  active: "positive",
  suspended: "danger",
} as const;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const partner = await backend.getPartner(id).catch(() => null);
  return {
    title: partner ? partner.name : "Partner",
  };
}

export default async function PartnerLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const partner = await backend.getPartner(id);
  if (!partner) notFound();

  const operator = await getOperator();
  const cookieId = await getImpersonateSessionId();
  const active = operator
    ? await backend.listActiveImpersonations(operator.id)
    : [];
  const live = matchImpersonationBanner(cookieId, partner.id, active);

  return (
    <div className="flex flex-col gap-6">
      {live ? (
        <ImpersonateBannerView
          partnerName={partner.name}
          sessionId={live.id}
          reason={live.reason}
          expiresAt={live.expires_at}
        />
      ) : null}
      <div className="flex flex-col gap-2">
        <nav
          aria-label="Migas"
          className="flex items-center gap-2 text-xs font-mono uppercase text-muted-foreground tracking-eyebrow"
        >
          <Link
            href="/partners"
            className="hover:text-foreground transition-colors"
          >
            Partners
          </Link>
          <span aria-hidden="true">/</span>
          <span className="text-foreground">{partner.slug}</span>
        </nav>
        <div className="flex flex-col gap-2">
          <Eyebrow>Partner</Eyebrow>
          <h1
            className="text-2xl md:text-3xl font-semibold leading-tight tracking-tight"
          >
            {partner.name}
          </h1>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-2">
              <StatusDot tone={STATUS_TONE[partner.status] ?? "muted"} />
              {statusLabel(partner.status)}
            </span>
            <span className="inline-flex items-center gap-2">
              <StatusDot tone={partner.console_enabled ? "positive" : "muted"} />
              {partner.console_enabled ? "Consola encendida" : "Consola apagada"}
            </span>
            <span className="font-mono text-xs">{partner.slug}</span>
          </div>
        </div>
        {/* Spec 031 (R4.3): the facts the operator asks first, before any tab. */}
        <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
          {[
            { term: "Clientes", detail: partner.clients_count ?? "—", href: `/partners/${partner.id}/clients` },
            { term: "Personas", detail: partner.members_count ?? "—", href: `/partners/${partner.id}/team` },
            { term: "Saldo disponible", detail: formatCents(partner.available_cents), href: `/partners/${partner.id}/money` },
            { term: "Alta", detail: new Date(partner.created_at).toLocaleDateString("es", { dateStyle: "medium" }), href: null },
          ].map((f) => (
            <div key={f.term} className="flex min-w-0 flex-col gap-1">
              <dt className="text-xs text-muted-foreground">{f.term}</dt>
              <dd className="truncate text-base font-semibold tabular-nums">
                {f.href ? (
                  <Link href={f.href} className="underline-offset-4 hover:underline">
                    {f.detail}
                  </Link>
                ) : (
                  f.detail
                )}
              </dd>
            </div>
          ))}
        </dl>
      </div>
      <PartnerTabs partnerId={partner.id} />
      <Separator />
      {children}
    </div>
  );
}
