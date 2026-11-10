import { redirect } from "next/navigation";

import { BuilderNew } from "@/components/builder/builder-new";
import { CrumbName } from "@/components/shell/crumb-names";
import { clientHref } from "@/components/shell/routes-v2";
import { getT } from "@/i18n/server";
import { run } from "@/lib/actions";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { getClientV2Cached, getConsoleVersionCached } from "../../data";

export async function generateMetadata() {
  const { t } = await getT();
  return { title: t("builder.new.title") };
}

/**
 * «Nuevo agente» con la consola nueva (spec 047, historia 7; requisito 17.1),
 * como el prototipo aprobado (`agente.md` §3): la pantalla del agente con la
 * descripción, los pasos del borrador y, al terminar, el agente (con sus
 * preguntas encima, `?job=`). Abrirla no crea nada: el agente nace con su
 * primer borrador (17.2). El nombre del cliente va bajo el título.
 *
 * Solo para quien puede crear agentes; quien no, vuelve a la pestaña Agentes.
 * Si los ejemplos y las plantillas no llegan, la pantalla funciona igual con
 * los límites de siempre y lo dice donde iban las plantillas.
 */
export default async function NewAgentPage({
  params,
  searchParams,
}: {
  params: Promise<{ ref: string }>;
  searchParams: Promise<{ name?: string; description?: string }>;
}) {
  const { ref } = await params;
  // «Crear este agente» desde «Completar con el constructor» (18.4): rellena, no crea.
  const { name, description } = await searchParams;
  const principal = await requirePartnerPrincipal(`/clients/${ref}/agents/new`);
  if (!can(principal.role, "clients:read")) redirect("/");
  if ((await getConsoleVersionCached(principal)) !== "v2") redirect(`/clients/${encodeURIComponent(ref)}/agent`);
  if (!can(principal.role, "agents:write")) redirect(clientHref(ref, "agents"));
  const { t } = await getT(principal.locale);

  const [options, client] = await Promise.all([
    run(() => backendFor(principal).getDraftOptions(ref)),
    // «de Flor y Encanto» bajo el título: la misma lectura que el layout.
    getClientV2Cached(principal, ref).catch(() => null),
  ]);
  return (
    <>
      {/* La miga dice «Nuevo agente», no «Agente». */}
      <CrumbName id="new" label={t("builder.new.title")} />
      <BuilderNew
        refId={ref}
        options={options.ok ? options.data : null}
        clientName={client?.name ?? null}
        initial={{ name: typeof name === "string" ? name.slice(0, 40) : undefined, description: typeof description === "string" ? description.slice(0, 1024) : undefined }}
      />
    </>
  );
}
