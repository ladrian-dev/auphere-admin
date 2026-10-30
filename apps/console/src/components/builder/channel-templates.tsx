"use client";

import * as React from "react";

import { listTemplatesAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { TemplatesSection } from "@/components/channels/templates-section";
import { useT } from "@/i18n/client";
import type { TemplateList } from "@/lib/backend/channels";

/**
 * The WhatsApp templates on the number's page (QA 2026-10-30): the same
 * list, composer and delete as the client's channels page, which no tab of
 * the v2 console leads to — so a partner (or Meta's reviewer) connects,
 * configures and creates a template without leaving the agent. Loaded here,
 * after the page, because it asks Meta.
 */
export function ChannelTemplates({ refId, manage }: { refId: string; manage: boolean }) {
  const t = useT();
  const [state, setState] = React.useState<{ list: TemplateList | null; error: string | null; loading: boolean }>({
    list: null,
    error: null,
    loading: true,
  });

  // Bumped after a create or a delete: the effect reads the list again.
  const [version, setVersion] = React.useState(0);

  React.useEffect(() => {
    let alive = true;
    void listTemplatesAction({ ref: refId })
      .catch(() => null)
      .then((res) => {
        if (!alive) return;
        if (res?.ok) setState({ list: res.data, error: null, loading: false });
        else setState({ list: null, error: t("common.error.backend"), loading: false });
      });
    return () => {
      alive = false;
    };
  }, [refId, t, version]);

  if (state.loading && state.list === null && state.error === null) {
    return (
      <div id="canal-plantillas" className="scroll-mt-24 rounded-md border border-border bg-card p-4 text-sm text-muted-foreground sm:p-6" aria-busy="true">
        {t("tpl.loading")}
      </div>
    );
  }
  return (
    <div className="rounded-md border border-border bg-card p-4 sm:p-6" data-slot="channel-templates">
      <TemplatesSection refId={refId} list={state.list} error={state.error} manage={manage} onChanged={() => setVersion((v) => v + 1)} sectionId="canal-plantillas" headingLevel={3} />
    </div>
  );
}
