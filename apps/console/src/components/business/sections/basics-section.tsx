"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Field, Input, NativeSelect, StatusBadge, Textarea } from "@nexus/ui";

import { reloadSectionAction, saveBasicsAction } from "@/app/(console)/clients/[ref]/business/actions";
import { decideSuggestionAction } from "@/app/(console)/clients/[ref]/client-v2-actions";
import { useT } from "@/i18n/client";
import type { Basics, BasicsBody, Sector, SectorOption } from "@/lib/backend/business-sections";
import type { Suggestion } from "@/lib/backend/client-records";

import { sectorLabelOf } from "./proposals-model";
import { ConflictNotice, EditAction, ReadList, SectionFrame, problemOf, useSectionEdit, type Result } from "./section-frame";

type Save = (body: { ref: string; revision: number; body: BasicsBody }) => Promise<Result<Basics>>;
type Decide = (body: { ref: string; id: string; decision: "accept" | "discard" }) => Promise<Result<unknown>>;
type Reload = (body: { ref: string; section: "basics" }) => Promise<Result<unknown>>;

/** «Otro»: un sector sin guía de Auphere, con su etiqueta libre (57.5). */
const OTHER = "otro";
const SECTOR_LABEL_MAX = 40;

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
 *
 * Enmienda del 2026-10-29 (T209, requisito 57.5): el sector, con «Con guía» o
 * «Generada» según tenga guía de Auphere, «Identificando el sector…» mientras el
 * sistema lo identifica, y la propuesta del sistema al lado del valor cuando lo
 * fijó una persona (aceptar o descartar, 57.3). Se corrige en «Editar» con los
 * sectores con guía (`GET /console/sectors`) o «Otro» con una etiqueta libre de
 * hasta 40 caracteres. Una API sin el campo no enseña nada del sector.
 */
export function BasicsSection({
  refId,
  basics: initial,
  canWrite,
  sectors,
  sectorProposal = null,
  save = (b) => saveBasicsAction(b),
  decide = (b) => decideSuggestionAction(b),
  reload = (b) => reloadSectionAction(b),
}: {
  refId: string;
  basics: Basics;
  canWrite: boolean;
  /** Los sectores con guía; sin ellos (o si no cargaron), solo el actual y «Otro». */
  sectors?: Result<SectorOption[]>;
  /** La propuesta pendiente del sistema para el sector (`/business/sector`). */
  sectorProposal?: Suggestion | null;
  save?: Save;
  decide?: Decide;
  reload?: Reload;
}) {
  const t = useT();
  const [basics, setBasics] = React.useState(initial);
  const [values, setValues] = React.useState(() => valuesOf(initial));
  const [euOnly, setEuOnly] = React.useState(initial.eu_only);
  const [sector, setSector] = React.useState(() => sectorValuesOf(initial.sector));
  const [sectorError, setSectorError] = React.useState<string | null>(null);
  const [proposal, setProposal] = React.useState(sectorProposal);
  // La propuesta de sector que se está decidiendo: sus botones esperan (un doble clic no la manda dos veces).
  const [deciding, setDeciding] = React.useState<"accept" | "discard" | null>(null);
  const [problem, setProblem] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();
  const edit = useSectionEdit("business-basics");
  const hasSector = basics.sector !== undefined;
  const options = sectorOptions(sectors?.ok ? sectors.data : [], basics.sector ?? null);

  function cancel() {
    setValues(valuesOf(basics));
    setEuOnly(basics.eu_only);
    setSector(sectorValuesOf(basics.sector));
    setSectorError(null);
    setProblem(null);
    edit.close();
  }

  /** El cambio de sector que hay que mandar; `null` si no cambió; `false` si falta la etiqueta de «Otro». */
  function sectorChange(): BasicsBody["sector"] | null | false {
    if (!hasSector || !sector.key) return null;
    const current = basics.sector ?? null;
    if (sector.key === OTHER) {
      const label = sector.other.trim().slice(0, SECTOR_LABEL_MAX);
      if (!label) return false;
      return current?.key === OTHER && current.label === label ? null : { key: OTHER, label };
    }
    if (current?.key === sector.key) return null;
    const option = options.find((o) => o.key === sector.key);
    return option ? { key: option.key, label: option.label } : null;
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
    const changed = sectorChange();
    if (changed === false) {
      setSectorError(t("business.sector.error.other_required"));
      return;
    }
    setSectorError(null);
    if (changed) body.sector = changed;
    startTransition(async () => {
      const res = await save({ ref: refId, revision: basics.revision, body });
      if (res.ok) {
        setBasics(res.data);
        setValues(valuesOf(res.data));
        setEuOnly(res.data.eu_only);
        setSector(sectorValuesOf(res.data.sector));
        setProblem(null);
        edit.close();
        toast.success(t("business.section.saved"));
        return;
      }
      const code = problemOf(res);
      setProblem(
        code === "conflict"
          ? "conflict"
          : code === "timezone_invalid"
            ? t("business.basics.error.timezone_invalid")
            : code === "sector_unknown"
              ? t("business.sector.error.unknown")
              : t("business.section.error.generic"),
      );
    });
  }

  async function decideSector(decision: "accept" | "discard") {
    if (!proposal || deciding) return;
    setDeciding(decision);
    const res = await decide({ ref: refId, id: proposal.id, decision }).catch(() => null);
    setDeciding(null);
    if (!res?.ok) {
      toast.error(res?.code === "already_decided" ? t("business.suggested.error.decided") : t("business.section.error.generic"));
      return;
    }
    setProposal(null);
    toast.success(decision === "accept" ? t("business.sector.accepted") : t("business.suggested.discarded"));
    if (decision === "discard") return;
    const fresh = await reload({ ref: refId, section: "basics" });
    if (fresh.ok) {
      const next = fresh.data as Basics;
      setBasics(next);
      setValues(valuesOf(next));
      setEuOnly(next.eu_only);
      setSector(sectorValuesOf(next.sector));
    }
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
          {hasSector ? (
            <div className="grid min-w-0 gap-4 sm:grid-cols-2">
              <Field
                label={t("business.sector.label")}
                hint={sectors && !sectors.ok ? t("business.sector.list.error") : undefined}
                className="min-w-0"
              >
                {(a11y) => (
                  <NativeSelect
                    {...a11y}
                    value={sector.key}
                    onChange={(e) => {
                      setSector({ ...sector, key: e.target.value });
                      setSectorError(null);
                    }}
                    wrapperClassName="w-full"
                  >
                    {!sector.key ? <option value="">{t("business.sector.choose")}</option> : null}
                    {options.map((o) => (
                      <option key={o.key} value={o.key}>
                        {o.label}
                      </option>
                    ))}
                    <option value={OTHER}>{t("business.sector.other")}</option>
                  </NativeSelect>
                )}
              </Field>
              {sector.key === OTHER ? (
                <Field label={t("business.sector.other.label")} hint={t("business.sector.other.hint")} error={sectorError ?? undefined} required className="min-w-0">
                  {(a11y) => (
                    <Input
                      {...a11y}
                      value={sector.other}
                      maxLength={SECTOR_LABEL_MAX}
                      autoComplete="off"
                      onChange={(e) => {
                        setSector({ ...sector, other: e.target.value });
                        setSectorError(null);
                      }}
                    />
                  )}
                </Field>
              ) : null}
            </div>
          ) : null}
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
            <Button type="submit" size="sm" loading={pending}>
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
            ...(hasSector || proposal
              ? [
                  {
                    label: t("business.sector.label"),
                    value: (
                      <SectorValue
                        sector={basics.sector ?? null}
                        proposal={proposal}
                        canWrite={canWrite}
                        deciding={deciding}
                        onDecide={(decision) => void decideSector(decision)}
                      />
                    ),
                  },
                ]
              : []),
            { label: label.info, value: basics.info || t("business.basics.read.no_info"), muted: !basics.info },
            { label: label.website, value: basics.website || t("business.basics.read.no_web"), muted: !basics.website },
            { label: label.timezone, value: basics.price_currency ? `${basics.timezone} · ${basics.price_currency}` : basics.timezone },
          ]}
        />
      )}
    </SectionFrame>
  );
}

/**
 * El sector en lectura: su etiqueta con «Con guía» o «Generada» y una línea que
 * lo explica; «Identificando el sector…» mientras no hay; y, si el sistema
 * propone otro contra uno fijado por una persona, la propuesta al lado.
 */
function SectorValue({
  sector,
  proposal,
  canWrite,
  deciding,
  onDecide,
}: {
  sector: Sector | null;
  proposal: Suggestion | null;
  canWrite: boolean;
  deciding: "accept" | "discard" | null;
  onDecide: (decision: "accept" | "discard") => void;
}) {
  const t = useT();
  const proposed = proposal ? sectorLabelOf(proposal.proposed_value) : null;
  return (
    <div className="grid min-w-0 gap-2" data-slot="business-sector">
      {sector ? (
        <>
          <span className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="min-w-0 break-words">{sector.label}</span>
            <StatusBadge tone={sector.has_guide ? "muted" : "info"}>
              {sector.has_guide ? t("business.sector.guide") : t("business.sector.generated")}
            </StatusBadge>
          </span>
          <span className="text-xs text-pretty text-muted-foreground">
            {sector.has_guide ? t("business.sector.guide.hint") : t("business.sector.generated.hint")}
          </span>
        </>
      ) : (
        <span className="text-muted-foreground">{t("business.sector.identifying")}</span>
      )}
      {proposal && proposed ? (
        <div className="grid min-w-0 gap-2 rounded-md border border-dashed border-input p-3" data-slot="business-sector-proposal">
          <span className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="min-w-0 font-medium break-words">{t("business.sector.proposal", { label: proposed })}</span>
            <StatusBadge tone="warn">{t("business.suggested.badge")}</StatusBadge>
          </span>
          <span className="text-xs text-pretty text-muted-foreground">{t("business.sector.proposal.hint")}</span>
          {canWrite ? (
            <span className="flex flex-wrap gap-2">
              <Button
                type="button"
                size="sm"
                onClick={() => onDecide("accept")}
                loading={deciding === "accept"}
                disabled={deciding !== null}
                aria-label={t("business.sector.accept.label", { label: proposed })}
              >
                {t("business.suggested.accept")}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => onDecide("discard")}
                loading={deciding === "discard"}
                disabled={deciding !== null}
                aria-label={t("business.sector.discard.label", { label: proposed })}
              >
                {t("business.suggested.discard")}
              </Button>
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/** Lo que el selector enseña: los sectores con guía y, si el actual no está entre ellos (y no es «Otro»), el actual. */
function sectorOptions(listed: readonly SectorOption[], current: Sector | null): SectorOption[] {
  const out = listed.filter((o) => o.key !== OTHER);
  if (current && current.key !== OTHER && !out.some((o) => o.key === current.key)) out.unshift({ key: current.key, label: current.label });
  return out;
}

function sectorValuesOf(sector: Sector | null | undefined): { key: string; other: string } {
  return { key: sector?.key ?? "", other: sector?.key === OTHER ? sector.label : "" };
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
