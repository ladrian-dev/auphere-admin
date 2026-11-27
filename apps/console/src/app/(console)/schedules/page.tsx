import { redirect } from "next/navigation";

import { PageHeader } from "@nexus/ui";

import { ClientPicker } from "@/components/schedules/client-picker";
import { NoAgentState } from "@/components/schedules/no-agent-state";
import { ScheduleList } from "@/components/schedules/schedule-list";
import { pageTitle } from "@/i18n/metadata";
import { getT } from "@/i18n/server";
import { backendFor } from "@/lib/backend";
import { can, requirePartnerPrincipal } from "@/lib/principal";

export const generateMetadata = () => pageTitle("nav.schedules");

type Search = { client?: string; state?: string; agent?: string };

/**
 * Rutinas, en `/schedules` (spec 082, requisitos 1.2 y 14).
 *
 * Se elige cliente primero y luego se ven las suyas: una rutina es de un agente,
 * y un agente es de un cliente. Sin `?client=` esta página es el selector, no
 * una lista vacía de todo junto.
 *
 * El estado que se pinta es el que manda la API, que ya viene cruzado con el
 * del agente: aquí no se deduce nada.
 */
export default async function SchedulesPage({
  searchParams,
}: {
  searchParams: Promise<Search>;
}) {
  const principal = await requirePartnerPrincipal();
  if (!can(principal.role, "schedules:read")) redirect("/");
  const { t } = await getT(principal.locale);
  const { client, state, agent } = await searchParams;
  const api = backendFor(principal);

  if (!client) {
    const clients = await api.listClients({ status: "active", limit: 100 });
    return (
      <>
        <PageHeader size="display" title={t("schedules.title")} description={t("schedules.description")} />
        <ClientPicker
          clients={clients.items}
          copy={{
            title: t("schedules.pick.title"),
            lead: t("schedules.pick.lead"),
            empty: {
              title: t("schedules.noclients.title"),
              body: t("schedules.noclients.body"),
              action: t("schedules.noclients.action"),
            },
          }}
        />
      </>
    );
  }

  // El nombre del cliente, no su referencia: «flor-y-encanto todavía no tiene
  // ninguna rutina» se lee como un identificador, no como un negocio.
  const detail = await api.getClient(client).catch(() => null);
  const name = detail?.name ?? client;
  // Sin agente no hay a quién vincular una rutina, y decirlo aquí evita que
  // alguien llegue al alta para encontrarse un desplegable vacío.
  if (detail && detail.setup?.agent === false) {
    return (
      <>
        <PageHeader size="display" title={t("schedules.title")} description={t("schedules.description")} />
        <NoAgentState
          title={t("schedules.noagents.title", { client: name })}
          body={t("schedules.noagents.body")}
          action={t("schedules.noagents.action")}
          href={`/clients/${encodeURIComponent(client)}`}
        />
      </>
    );
  }
  const page = await api.listSchedules(client, {
    agent,
    state: state === "active" || state === "paused" || state === "archived" ? state : undefined,
  });
  return (
    <>
      <PageHeader
        size="display"
        title={t("schedules.title")}
        description={t("schedules.timezone", { zone: page.timezone })}
      />
      <ScheduleList
        refId={client}
        page={page}
        state={state ?? "all"}
        agent={agent ?? ""}
        copy={{
          filters: {
            all: t("schedules.filter.all"),
            active: t("schedules.filter.active"),
            paused: t("schedules.filter.paused"),
            archived: t("schedules.filter.archived"),
          },
          columns: {
            routine: t("schedules.col.routine"),
            agent: t("schedules.col.agent"),
            when: t("schedules.col.when"),
            next: t("schedules.col.next"),
            runs: t("schedules.col.runs"),
            state: t("schedules.col.state"),
          },
          states: {
            active: t("schedules.state.active"),
            paused: t("schedules.state.paused"),
            archived: t("schedules.state.archived"),
          },
          reasons: {
            manual: t("schedules.reason.manual"),
            agent_unavailable: t("schedules.reason.agent_unavailable"),
            no_balance: t("schedules.reason.no_balance"),
            failures: t("schedules.reason.failures"),
          },
          noMatch: t("schedules.filter.none"),
          empty: {
            title: t("schedules.empty.title", { client: name }),
            body: t("schedules.empty.body"),
          },
          toolsNote: t("schedules.tools.note"),
          never: t("schedules.when.never"),
        }}
      />
    </>
  );
}
