"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Field, Input, Textarea } from "@nexus/ui";

import { saveBasicsAction } from "@/app/(console)/clients/[ref]/business/actions";
import { useT } from "@/i18n/client";
import type { Basics, BasicsBody } from "@/lib/backend/business-sections";

import { ConflictNotice, EditAction, ReadList, SectionFrame, problemOf, useSectionEdit, type Result } from "./section-frame";

type Save = (body: { ref: string; revision: number; body: BasicsBody }) => Promise<Result<Basics>>;

const FIELDS = ["name", "niche", "info", "website", "country", "timezone", "price_currency"] as const;
type FieldKey = (typeof FIELDS)[number];
const REQUIRED: ReadonlySet<FieldKey> = new Set(["name", "niche", "timezone"]);

/**
 * «Datos básicos» de Negocio (spec 047, T060; requisito 8.1): nombre, nicho,
 * información (dato no confiable: el agente la lee como dato), web, país, zona
 * horaria, moneda de los precios y «Solo UE». Solo se manda lo que cambió.
 *
 * Como el prototipo aprobado: se lee (nombre, nicho, información, web y zona
 * con la moneda) y «Editar» abre el formulario en la propia tarjeta, con todos
 * los campos, también el país y «Solo UE», que no se piden en el alta.
 */
export function BasicsSection({
  refId,
  basics: initial,
  canWrite,
  save = (b) => saveBasicsAction(b),
}: {
  refId: string;
  basics: Basics;
  canWrite: boolean;
  save?: Save;
}) {
  const t = useT();
  const [basics, setBasics] = React.useState(initial);
  const [values, setValues] = React.useState(() => valuesOf(initial));
  const [euOnly, setEuOnly] = React.useState(initial.eu_only);
  const [problem, setProblem] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();
  const edit = useSectionEdit("business-basics");

  function cancel() {
    setValues(valuesOf(basics));
    setEuOnly(basics.eu_only);
    setProblem(null);
    edit.close();
  }

  const label: Record<FieldKey, string> = {
    name: t("business.field.name"),
    niche: t("business.field.niche"),
    info: t("business.field.info"),
    website: t("business.basics.website"),
    country: t("business.basics.country"),
    timezone: t("business.basics.timezone"),
    price_currency: t("business.basics.price_currency"),
  };

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const before = valuesOf(basics);
    const body: BasicsBody = {};
    for (const key of FIELDS) {
      const value = values[key].trim();
      if (value === before[key]) continue;
      const cleaned = key === "country" || key === "price_currency" ? value.toUpperCase() : value;
      (body as Record<string, string | null>)[key] = cleaned === "" && !REQUIRED.has(key) ? null : cleaned;
    }
    if (euOnly !== basics.eu_only) body.eu_only = euOnly;
    startTransition(async () => {
      const res = await save({ ref: refId, revision: basics.revision, body });
      if (res.ok) {
        setBasics(res.data);
        setValues(valuesOf(res.data));
        setEuOnly(res.data.eu_only);
        setProblem(null);
        edit.close();
        toast.success(t("business.section.saved"));
        return;
      }
      const code = problemOf(res);
      setProblem(code === "conflict" ? "conflict" : code === "timezone_invalid" ? t("business.basics.error.timezone_invalid") : t("business.section.error.generic"));
    });
  }

  return (
    <SectionFrame
      id="business-basics"
      title={t("business.basics.title")}
      state={basics.state}
      canWrite={canWrite}
      action={edit.editing ? null : <EditAction label={t("business.section.edit.label", { section: t("business.basics.title") })} onClick={edit.open} />}
    >
      {canWrite && edit.editing ? (
        <form onSubmit={submit} className="grid min-w-0 gap-4" noValidate>
          <div className="grid min-w-0 gap-4 sm:grid-cols-2">
            {FIELDS.filter((k) => k !== "info").map((key) => (
              <Field key={key} label={label[key]} required={REQUIRED.has(key)} className="min-w-0">
                {(a11y) => (
                  <Input
                    {...a11y}
                    value={values[key]}
                    maxLength={key === "name" ? 60 : key === "niche" ? 80 : key === "website" ? 300 : 64}
                    onChange={(e) => setValues({ ...values, [key]: e.target.value })}
                  />
                )}
              </Field>
            ))}
          </div>
          <Field label={label.info}>
            {(a11y) => <Textarea {...a11y} value={values.info} maxLength={2000} onChange={(e) => setValues({ ...values, info: e.target.value })} />}
          </Field>
          <label className="flex min-h-6 items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={euOnly} onChange={(e) => setEuOnly(e.target.checked)} />
            {t("business.basics.eu_only")}
          </label>
          {problem === "conflict" ? <ConflictNotice /> : null}
          {problem && problem !== "conflict" ? (
            <p role="alert" className="text-sm text-destructive">
              {problem}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button type="submit" size="sm" disabled={pending}>
              {t("business.basics.save")}
            </Button>
            <Button type="button" size="sm" variant="ghost" onClick={cancel}>
              {t("business.section.cancel")}
            </Button>
          </div>
        </form>
      ) : (
        <ReadList
          rows={[
            { label: label.name, value: basics.name },
            { label: label.niche, value: basics.niche },
            { label: label.info, value: basics.info || t("business.basics.read.no_info"), muted: !basics.info },
            { label: label.website, value: basics.website || t("business.basics.read.no_web"), muted: !basics.website },
            { label: label.timezone, value: basics.price_currency ? `${basics.timezone} · ${basics.price_currency}` : basics.timezone },
          ]}
        />
      )}
    </SectionFrame>
  );
}

function valuesOf(b: Basics): Record<FieldKey, string> {
  return {
    name: b.name,
    niche: b.niche,
    info: b.info ?? "",
    website: b.website ?? "",
    country: b.country ?? "",
    timezone: b.timezone,
    price_currency: b.price_currency ?? "",
  };
}
