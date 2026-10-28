import { redirect } from "next/navigation";

import { PageHeader } from "@nexus/ui";

import { KnowledgeTable } from "@/components/agent-tools/knowledge-table";
import { pageTitle } from "@/i18n/metadata";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

import { addPlaybookUrlAction, deletePlaybookAction, reindexPlaybookAction, uploadPlaybookAction } from "./actions";

export const generateMetadata = () => pageTitle("nav.knowledge");

/**
 * Partner playbook at /console/knowledge. Client KB stays under the client.
 *
 * Spec 047 (prototipo «Consola de partners v2»): la cabecera grande de las demás
 * páginas, «Subir archivo» y «Añadir URL» lado a lado y la tarjeta «Documentos»
 * (la variante `playbook` de la tabla, que el conocimiento del cliente no usa).
 */
export default async function PlaybookPage() {
  const principal = await requirePartnerPrincipal();
  if (!can(principal.role, "playbook:read")) redirect("/");
  const { t } = await getT(principal.locale);
  const data = await backendFor(principal).listPlaybook();
  return (
    <>
      <PageHeader size="display" title={t("playbook.title")} description={t("playbook.description")} />
      <KnowledgeTable
        variant="playbook"
        refId=""
        data={data}
        canWrite={can(principal.role, "playbook:write")}
        emptyCopy={{ title: t("playbook.empty.title"), body: t("playbook.empty.body") }}
        actions={{
          upload: uploadPlaybookAction,
          addUrl: addPlaybookUrlAction,
          remove: deletePlaybookAction,
          reindex: reindexPlaybookAction,
        }}
      />
    </>
  );
}
