"use client";

import * as React from "react";

import { Section, Textarea } from "@nexus/ui";

import { useT } from "@/i18n/client";

import { useDraftSection, useRequiredDraftEdits } from "./draft-edits";

/**
 * The agent's instructions, as one section of the save bar (spec 047,
 * historia 2). Before, «Guardar borrador» here staged a NEW version copied
 * from the active one, and the settings saved a minute earlier stayed behind;
 * now there is no button here at all: the bar saves everything into the one
 * draft.
 *
 * Untouched, the box shows what the draft says — so a refresh that brings
 * someone else's draft shows theirs. Once the person types, it is theirs
 * until they save it or undo it.
 */
export function AgentPromptEditor() {
  const { draft, canWrite } = useRequiredDraftEdits();
  const t = useT();
  const id = React.useId();
  const [text, setText] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const value = text ?? draft.system_prompt;
  const dirty = text !== null && text !== draft.system_prompt;

  useDraftSection("prompt", dirty ? ["system_prompt"] : [], {
    collect: async () => {
      if (!value.trim()) {
        setError(t("agents.draft.prompt.empty"));
        return null;
      }
      setError(null);
      return { system_prompt: value };
    },
    reset: () => {
      setText(null);
      setError(null);
    },
  });

  const context = draft.exists
    ? draft.base_number != null
      ? t("agents.draft.context.draft", { n: draft.number ?? "", agent: draft.agent_name, base: draft.base_number })
      : t("agents.draft.context.draftFirst", { n: draft.number ?? "", agent: draft.agent_name })
    : draft.number != null
      ? t("agents.draft.context.active", { n: draft.number, agent: draft.agent_name })
      : t("agents.draft.context.none", { agent: draft.agent_name });

  return (
    <Section title={t("agents.draft.prompt.title")} description={t("agents.draft.prompt.help")} flat headingLevel={2}>
      <p id={`${id}-context`} className="text-xs text-pretty text-muted-foreground" data-slot="draft-context">
        {context}
      </p>
      {!canWrite ? <p className="text-xs text-muted-foreground">{t("agents.draft.readonly")}</p> : null}
      <Textarea
        id={`${id}-prompt`}
        value={value}
        onChange={(e) => {
          setText(e.target.value);
          if (error) setError(null);
        }}
        readOnly={!canWrite}
        aria-label={t("agents.draft.prompt.title")}
        aria-describedby={error ? `${id}-context ${id}-error` : `${id}-context`}
        aria-invalid={error ? true : undefined}
        spellCheck={false}
        className="min-h-64 font-mono text-xs"
      />
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : null}
    </Section>
  );
}
