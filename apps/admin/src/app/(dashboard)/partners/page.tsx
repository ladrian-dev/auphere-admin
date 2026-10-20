import Link from "next/link";

import { Button, EmptyState, ErrorState, PageHeader } from "@nexus/ui";

import { backend } from "@/lib/backend";

import { PartnersTable } from "./partners-table";

export const metadata = { title: "Partners" };
export const dynamic = "force-dynamic";

/**
 * Spec 031 (R4.1): the agencies and resellers that run Auphere's console for
 * their own clients. One row each with their clients, people and balance.
 */
export default async function PartnersPage() {
  const partners = await backend.listPartners().catch(() => null);
  return (
    <>
      <PageHeader
        title="Partners"
        description="Agencias que operan la consola de Auphere para sus propios clientes."
        actions={<Button nativeButton={false} render={<Link href="/partners/new" />}>Nuevo partner</Button>}
      />
      {partners === null ? (
        <ErrorState title="No se pudieron leer los partners" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : partners.length === 0 ? (
        <EmptyState
          title="Todavía no hay partners"
          description="Da de alta el primero para que pueda entrar en su consola."
          action={<Button nativeButton={false} render={<Link href="/partners/new" />}>Nuevo partner</Button>}
        />
      ) : (
        <PartnersTable partners={partners} />
      )}
    </>
  );
}
