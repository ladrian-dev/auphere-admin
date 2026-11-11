import Link from "next/link";

import { Callout, EmptyState, PageHeader } from "@nexus/ui";
import { ReadError } from "@/components/states/read-error";
import { backend } from "@/lib/backend";

import { canSend } from "./labels";
import { CreateNumberDialog } from "./number-dialogs";
import { NumbersTable } from "./numbers-table";

export const metadata = { title: "Números de Auphere" };
export const dynamic = "force-dynamic";

type SearchParams = { include_inactive?: string };

/**
 * Spec 059 (historia 6; 5.1, 6.1–6.5): Auphere's own WhatsApp numbers, from
 * which it writes to the business owners — notices, and the questions the
 * agents pass to them. Same header, table, dialogs and words as the rest of
 * the panel; every change names its operator and its reason.
 *
 * Empty on purpose in production today: the empty state says what that means.
 * Deactivating does not cascade: owners pinned to a number fall back to the
 * principal one on the next send.
 */
export default async function AuphereNumbersPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const { include_inactive } = await searchParams;
  const showInactive = include_inactive === "true";
  const numbers = await backend.listAuphereChannels(showInactive).catch(() => null);
  const active = numbers?.filter((n) => n.active) ?? [];
  const cannotSend = active.filter((n) => !canSend(n)).length;
  const noPrincipal = active.length > 0 && !active.some((n) => n.is_default);

  return (
    <>
      <PageHeader
        title="Números de Auphere"
        description="Los números de WhatsApp de la cuenta de Meta de Auphere. Desde el principal salen los avisos de Auphere y las consultas a los dueños de los negocios que no tienen un número asignado."
        actions={numbers?.length ? <CreateNumberDialog /> : undefined}
      />
      {numbers === null ? (
        <ReadError title="No se pudieron leer los números" description="La API no respondió. Vuelve a intentarlo en un momento." />
      ) : (
        <div className="flex flex-col gap-4">
          {noPrincipal ? (
            <Callout tone="warning" title="Ningún número es el principal">
              Hasta que marques uno, Auphere no envía avisos por WhatsApp ni consultas a los dueños sin un número asignado.
            </Callout>
          ) : null}
          {cannotSend > 0 ? (
            <Callout tone="warning" title="Hay números que no pueden enviar">
              {cannotSend === 1 ? "1 número no puede enviar" : `${cannotSend} números no pueden enviar`}: le falta el token o el
              identificador del número en Meta. Complétalos con «Editar».
            </Callout>
          ) : null}
          {numbers.length === 0 ? (
            <EmptyState
              title={showInactive ? "Auphere no tiene ningún número registrado" : "Auphere no tiene ningún número activo"}
              description="Sin un número, Auphere no envía avisos ni consultas por WhatsApp a los dueños de los negocios. Regístralo cuando Auphere tenga el suyo en Meta."
              action={<CreateNumberDialog />}
            />
          ) : (
            <NumbersTable numbers={numbers} />
          )}
          <p className="text-sm">
            <Link
              href={showInactive ? "/auphere/channels" : "/auphere/channels?include_inactive=true"}
              className="inline-flex min-h-6 items-center rounded-sm text-muted-foreground underline-offset-4 outline-none hover:text-foreground hover:underline focus-visible:ring-2 focus-visible:ring-ring"
            >
              {showInactive ? "Ver solo los activos" : "Ver también los desactivados"}
            </Link>
          </p>
        </div>
      )}
    </>
  );
}
