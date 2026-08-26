import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Eyebrow } from "@/components/brand/eyebrow";
import { StatusDot } from "@/components/brand/status-dot";
import { Separator } from "@/components/ui/separator";
import { backend } from "@/lib/backend";
import { getImpersonateSessionId } from "@/lib/impersonate";
import { matchImpersonationBanner } from "@/lib/impersonate-cookie";
import { getOperator } from "@/lib/session";
import { statusLabel } from "@/lib/format";

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
          className="flex items-center gap-2 text-xs font-mono uppercase text-muted-foreground"
          style={{ letterSpacing: "var(--tracking-eyebrow)" }}
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
            className="text-2xl md:text-3xl font-semibold leading-tight"
            style={{ letterSpacing: "var(--tracking-tight)" }}
          >
            {partner.name}
          </h1>
          <div className="flex items-center gap-3 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-2">
              <StatusDot tone={STATUS_TONE[partner.status] ?? "muted"} />
              {statusLabel(partner.status)}
            </span>
            {partner.contact_email ? (
              <span>{partner.contact_email}</span>
            ) : null}
            <span className="font-mono text-xs">{partner.slug}</span>
          </div>
        </div>
      </div>
      <PartnerTabs partnerId={partner.id} />
      <Separator />
      {children}
    </div>
  );
}
