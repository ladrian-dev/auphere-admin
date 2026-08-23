import { redirect } from "next/navigation";

import { KnowledgeTable } from "@/components/agent-tools/knowledge-table";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePrincipal } from "@/lib/principal";

import { addPlaybookUrlAction, deletePlaybookAction, reindexPlaybookAction, uploadPlaybookAction } from "./actions";

/** Partner playbook at /console/knowledge. Client KB stays under the client. */
export default async function PlaybookPage() {
  const principal = await requirePrincipal();
  if (!can(principal.role, "playbook:read")) redirect("/");
  const { t } = await getT(principal.locale);
  const data = await backendFor(principal).listPlaybook();
  return (
    <section className="flex min-w-0 flex-col gap-4" aria-label={t("playbook.title")}>
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="text-base font-medium text-balance">{t("playbook.title")}</h1>
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("playbook.description")}</p>
      </div>
      <KnowledgeTable
        refId=""
        data={data}
        canWrite={can(principal.role, "playbook:write")}
        actions={{
          upload: uploadPlaybookAction,
          addUrl: addPlaybookUrlAction,
          remove: deletePlaybookAction,
          reindex: reindexPlaybookAction,
        }}
      />
    </section>
  );
}
