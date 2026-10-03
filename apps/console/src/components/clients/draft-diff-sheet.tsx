"use client";

import { Button, Section, Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@nexus/ui";
import * as React from "react";

import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { DraftDiff } from "@/lib/backend";

import { settingValue } from "./draft-setting-value";
import { PromptDiff } from "./prompt-diff";

type Row = { term: string; before: string; after: string };

/**
 * «Revisar y publicar» (spec 017, R3.2): qué cambia el borrador respecto a
 * la versión que atiende ahora, antes de que el partner decida.
 *
 * La API contesta en claves; la traducción vive aquí. Un campo que la API
 * nombre y la consola no conozca se enseña con su clave en vez de
 * desaparecer: que falte una traducción no puede esconder un cambio.
 */
export function DraftDiffSheet({
  open,
  onOpenChange,
  diff,
  loading,
  canPublish,
  publishing,
  onPublish,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  diff: DraftDiff | null;
  loading: boolean;
  canPublish: boolean;
  publishing: boolean;
  onPublish: () => void;
}) {
  const t = useT();
  const titleRef = React.useRef<HTMLHeadingElement>(null);
  const version = diff?.version.draft ?? 0;
  const active = diff?.version.active ?? null;

  const settings: Row[] = (diff?.settings ?? []).map((row) => ({
    term: label(t, `draft.field.${row.field}`, row.field),
    before: settingValue(t, row.field, row.before),
    after: settingValue(t, row.field, row.after),
  }));
  const capabilities: Row[] = (diff?.capabilities ?? []).map((row) => ({
    term: row.name,
    before: t(row.change === "enabled" ? "draft.diff.disabled" : "draft.diff.enabled"),
    after: t(row.change === "enabled" ? "draft.diff.enabled" : "draft.diff.disabled"),
  }));
  const knowledge: Row[] = (diff?.knowledge ?? []).map((row) => ({
    term: row.title,
    before: row.change === "added" ? "—" : t("draft.diff.added"),
    after: t(row.change === "added" ? "draft.diff.added" : "draft.diff.removed"),
  }));
  const promptChanged = Boolean(diff && diff.prompt.before !== diff.prompt.after);
  const nothing = !loading && settings.length === 0 && capabilities.length === 0 && knowledge.length === 0 && !promptChanged;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {/* Una sola sangría para todo, y solo el cuerpo hace scroll: el pie
          con «Publicar» no se va con el contenido. */}
      <SheetContent initialFocus={titleRef} className="flex flex-col gap-0 overflow-hidden data-[side=right]:sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle ref={titleRef} tabIndex={-1} className="outline-none">
            {t("draft.diff.title", { version })}
          </SheetTitle>
          <SheetDescription>
            {active === null ? t("draft.diff.descriptionFirst") : t("draft.diff.description", { active })}
          </SheetDescription>
        </SheetHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-(--space-block) overflow-y-auto px-4 pb-4">
          {loading ? <p className="text-sm text-muted-foreground">{t("draft.diff.loading")}</p> : null}
          {nothing ? <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("draft.diff.empty")}</p> : null}
          {settings.length ? <DiffTable title={t("draft.screen.settings")} rows={settings} /> : null}
          {capabilities.length ? <DiffTable title={t("draft.screen.capabilities")} rows={capabilities} /> : null}
          {knowledge.length ? <DiffTable title={t("draft.screen.knowledge")} rows={knowledge} /> : null}
          {promptChanged && diff ? (
            <Section title={t("draft.screen.prompt")} headingLevel={3} flat>
              <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("draft.diff.promptChanged")}</p>
              {/* Plegado: son miles de caracteres y casi nadie los lee antes
                  de publicar, pero quien quiera verlos no debería tener que
                  irse a otra pantalla. Es el mismo componente que Agente. */}
              <details className="text-sm">
                <summary className="cursor-pointer text-muted-foreground">{t("draft.diff.promptOpen")}</summary>
                <PromptDiff before={diff.prompt.before} after={diff.prompt.after} noneLabel={t("draft.diff.empty")} />
              </details>
            </Section>
          ) : null}
        </div>
        <SheetFooter className="flex-row justify-end gap-2 border-t border-border">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("draft.diff.cancel")}
          </Button>
          {canPublish ? (
            <Button onClick={onPublish} loading={publishing} disabled={loading}>
              {t("draft.diff.publish", { version })}
            </Button>
          ) : null}
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}

/** Antes y ahora al mismo ancho: la comparación es entre iguales. */
function DiffTable({ title, rows }: { title: string; rows: Row[] }) {
  const t = useT();
  return (
    <Section title={title} headingLevel={3} flat>
      <table className="w-full text-sm">
        <colgroup>
          <col className="w-[30%]" />
          <col className="w-[35%]" />
          <col className="w-[35%]" />
        </colgroup>
        <thead>
          <tr className="text-left text-xs text-muted-foreground">
            <th scope="col" className="pb-1 font-medium">
              {t("draft.diff.what")}
            </th>
            <th scope="col" className="pb-1 font-medium">
              {t("draft.diff.before")}
            </th>
            <th scope="col" className="pb-1 font-medium">
              {t("draft.diff.after")}
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.term} className="border-t border-border align-top">
              <th scope="row" className="py-2 pr-3 text-left font-normal text-muted-foreground">
                {row.term}
              </th>
              <td className="py-2 pr-3 text-muted-foreground">{row.before}</td>
              <td className="py-2 font-medium">{row.after}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Section>
  );
}

/** Una traducción que falte enseña la clave, no esconde el cambio. */
function label(t: (k: MessageKey) => string, key: string, fallback: string): string {
  const translated = t(key as MessageKey);
  return translated === key ? fallback : translated;
}
