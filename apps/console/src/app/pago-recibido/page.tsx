import { CircleCheck, CircleX } from "lucide-react";
import type { Metadata } from "next";

import { BrandLockup } from "@nexus/ui";

import { getT } from "@/i18n/server";
import { resolvePrincipal } from "@/lib/principal";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{ estado?: string }>;

/**
 * The same language as `<html lang>` (the root layout): a signed-in visitor
 * without the cookie gets their account's, like `not-found.tsx`.
 */
async function pageT() {
  const resolution = await resolvePrincipal().catch(() => null);
  return getT(resolution?.kind === "ok" ? resolution.principal.locale : undefined);
}

/** The tab says what the page says: a cancelled payment is not «Pago recibido». */
export async function generateMetadata({ searchParams }: { searchParams: SearchParams }): Promise<Metadata> {
  const canceled = (await searchParams).estado === "cancelado";
  const { t } = await pageT();
  return {
    title: t(canceled ? "payReturn.title.canceled" : "payReturn.title.paid"),
    robots: { index: false, follow: false },
  };
}

/**
 * Spec 077 (7.9): where someone who paid a client membership on Stripe lands.
 * Public, outside the session (`proxy.ts`), and it reads and writes nothing:
 * the state of the membership is Stripe's notice to the API, never this page.
 * `?estado=cancelado` is Stripe's «cancel_url»: nothing was charged.
 */
export default async function PaymentReturnPage({ searchParams }: { searchParams: SearchParams }) {
  const canceled = (await searchParams).estado === "cancelado";
  const { t } = await pageT();
  const Icon = canceled ? CircleX : CircleCheck;
  return (
    <main className="mx-auto flex min-h-svh w-full max-w-md flex-col justify-center gap-8 px-6 py-12">
      <BrandLockup />
      <section className="flex flex-col gap-3" aria-labelledby="pay-return-title">
        <Icon
          className={canceled ? "size-8 text-muted-foreground" : "size-8 text-status-positive-text"}
          aria-hidden="true"
        />
        <h1 id="pay-return-title" className="text-2xl font-semibold tracking-tight text-balance">
          {t(canceled ? "payReturn.title.canceled" : "payReturn.title.paid")}
        </h1>
        <p className="text-base text-pretty text-muted-foreground">
          {t(canceled ? "payReturn.body.canceled" : "payReturn.body.paid")}
        </p>
      </section>
    </main>
  );
}
