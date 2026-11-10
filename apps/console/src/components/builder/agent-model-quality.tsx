"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, DescriptionList, Skeleton, StatusBadge, StatusDot } from "@nexus/ui";

import { checkModelQualityAction, modelQualityAction } from "@/app/(console)/clients/[ref]/agents/model-quality-actions";
import { qualityJobAction } from "@/app/(console)/clients/[ref]/agents/quality-actions";
import { useLocale, useT } from "@/i18n/client";
import type { QualityJob } from "@/lib/backend/agent-quality-types";
import type { ModelPolicy, ModelQuality, PinnableModel, ProfileOption, QualityCheck, QualityCheckAccepted } from "@/lib/backend/model-quality-types";

import { sleep, type Result } from "./builder-model";
import {
  autoOption,
  deltaText,
  isChecking,
  offeredProfiles,
  optionName,
  optionPolicy,
  policyName,
  priceText,
  profileLine,
  reasonText,
  residencyText,
  samePolicy,
  unitPriceText,
  usable,
  withCheck,
} from "./model-quality-model";
import { waitForJob } from "./quality-model";

type Ids = { ref: string; agent: string };
export type ModelQualityActions = {
  load?: (body: Ids) => Promise<Result<ModelQuality>>;
  check?: (body: Ids & { policy: ModelPolicy }) => Promise<Result<QualityCheckAccepted>>;
  poll?: (body: { ref: string; job: string }) => Promise<Result<QualityJob>>;
};

const SERVER_ACTIONS: Required<ModelQualityActions> = {
  load: (body) => modelQualityAction(body),
  check: (body) => checkModelQualityAction(body),
  poll: (body) => qualityJobAction(body),
};
const NO_ACTIONS: ModelQualityActions = {};

type Option = ProfileOption | PinnableModel;
const keyOf = (p: ModelPolicy) => (p.kind === "profile" ? `profile:${p.profile}` : `pinned:${p.deployment}`);

/**
 * Agente › Avanzado › Calidad (spec 047, historia 23; T147; requisito 39):
 * cuánta calidad paga este agente, sin saber de modelos.
 *
 * - Cada opción —«Automático», «Económico», «Equilibrado», «Máximo» y, en
 *   «Fijar un modelo», los modelos que se pueden fijar— dice para qué sirve y
 *   su precio estimado por mensaje en la moneda de la cuenta, comparado con el
 *   de la opción actual (39.4). Con «Solo UE», lo que no tiene modelo en la UE
 *   no sale (39.10).
 * - Junto al estimado, el precio real medio por mensaje de los últimos 7 días
 *   (39.5).
 * - Elegir una opción que todavía no está comprobada con este agente pide
 *   «Comprobar la calidad»: corre la suite del agente con esa política y se
 *   sigue como un trabajo (39.9). Solo una opción comprobada se lleva al
 *   borrador, y se aplica al «Guardar», que pasa la puerta (39.1).
 * - A un agente migrado se le propone «Automático» (39.11).
 *
 * Las opciones son un grupo de radio: una se elige, y la acción va debajo,
 * una sola. Sin `agents:write` (o sin `change` en `allowed`) se lee todo.
 *
 * `quality` en `undefined` se lee al montar; en `null`, no se pudo leer.
 */
export function AgentModelQuality({
  refId,
  agentId,
  quality: initial,
  canWrite,
  drafted = null,
  onUse,
  actions: given = NO_ACTIONS,
  wait = sleep,
}: {
  refId: string;
  agentId: string;
  quality?: ModelQuality | null;
  canWrite: boolean;
  /** La política del borrador, si tiene una. */
  drafted?: ModelPolicy | null;
  /** Llevar la política al borrador (sin borrador editable, no se ofrece). */
  onUse?: (policy: ModelPolicy) => Promise<Result<unknown>>;
  actions?: ModelQualityActions;
  wait?: (ms: number) => Promise<void>;
}) {
  const t = useT();
  const locale = useLocale();
  const actions = React.useMemo(() => ({ ...SERVER_ACTIONS, ...given }), [given]);
  const ids = React.useMemo(() => ({ ref: refId, agent: agentId }), [refId, agentId]);
  const [quality, setQuality] = React.useState<ModelQuality | null | undefined>(initial);
  const [loading, setLoading] = React.useState(initial === undefined);
  const [chosen, setChosen] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [using, setUsing] = React.useState(false);
  const polling = React.useRef(new Set<string>());
  const alive = React.useRef(true);
  React.useEffect(
    () => () => {
      alive.current = false;
    },
    [],
  );
  const groupName = React.useId();

  const load = React.useCallback(async (): Promise<ModelQuality | null> => {
    setLoading(true);
    const res = await actions.load(ids);
    if (!alive.current) return null;
    setLoading(false);
    setQuality(res.ok ? res.data : null);
    return res.ok ? res.data : null;
  }, [actions, ids]);

  /** Sigue una comprobación hasta que termina y vuelve a leer la calidad para saber si pasó. */
  const follow = React.useCallback(
    async (policy: ModelPolicy, job: string, name: string) => {
      if (polling.current.has(job)) return;
      polling.current.add(job);
      await waitForJob(() => actions.poll({ ref: refId, job }), { wait, cancelled: () => !alive.current });
      polling.current.delete(job);
      if (!alive.current) return;
      const next = await load();
      const option = next ? [...next.profiles, ...next.pinnable].find((o) => samePolicy(optionPolicy(o), policy)) : null;
      if (option?.check.status === "passed" || option?.certified) toast.success(t("modelQuality.check.done", { name }));
      else if (option?.check.status === "failed") toast.error(t("modelQuality.check.notPassed", { name }));
    },
    [actions, load, refId, t, wait],
  );

  // Sin datos del servidor: se leen al montar.
  const asked = React.useRef(initial !== undefined);
  React.useEffect(() => {
    if (asked.current) return;
    asked.current = true;
    void load();
  }, [load]);

  // Una comprobación que ya estaba en marcha al abrir la pantalla se sigue igual.
  React.useEffect(() => {
    if (!quality) return;
    for (const option of [...quality.profiles, ...quality.pinnable]) {
      if (isChecking(option.check) && option.check.job_id) void follow(optionPolicy(option), option.check.job_id, optionName(t, option));
    }
  }, [quality, follow, t]);

  if (quality === undefined || (loading && quality === null)) {
    return (
      <div className="grid min-w-0 gap-3" aria-busy="true" data-slot="model-quality-loading">
        <p role="status" className="text-sm text-muted-foreground">
          {t("modelQuality.loading")}
        </p>
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (quality === null) {
    return (
      <Callout
        tone="danger"
        action={
          <Button size="sm" variant="outline" onClick={() => void load()}>
            {t("modelQuality.retry")}
          </Button>
        }
      >
        {t("modelQuality.error")}
      </Callout>
    );
  }

  const canChange = canWrite && quality.allowed.includes("change");
  const profiles = offeredProfiles(quality);
  const options: Option[] = [...profiles, ...quality.pinnable];
  const draftDiffers = drafted !== null && !samePolicy(drafted, quality.current);
  // Lo elegido: lo que la persona marcó o, si no, lo del borrador o lo publicado.
  const fallback = options.find((o) => samePolicy(optionPolicy(o), drafted ?? quality.current)) ?? null;
  const selected = options.find((o) => keyOf(optionPolicy(o)) === chosen) ?? fallback;
  const auto = autoOption(quality);
  const pinnedOpen = options.some((o) => !("profile" in o) && (o.current || samePolicy(optionPolicy(o), drafted)));

  async function check(option: Option) {
    setError(null);
    const policy = optionPolicy(option);
    const res = await actions.check({ ...ids, policy });
    if (!alive.current) return;
    if (!res.ok) {
      setError(
        res.code === "build_budget_exhausted" || res.status === 402
          ? t("money.build.blocked")
          : res.code === "no_version"
            ? t("modelQuality.error.no_version")
            : res.code === "profile_not_eu_servable"
              ? t("modelQuality.error.not_eu")
              : res.code === "invalid_model_policy"
                ? t("modelQuality.error.invalid")
                : res.status === 401 || res.status === 403
                  ? t("common.forbidden")
                  : t("modelQuality.error.check"),
      );
      return;
    }
    const running: QualityCheck = { status: "queued", job_id: res.data.job_id, reasons: [] };
    setQuality((prev) => (prev ? withCheck(prev, policy, running) : prev));
    void follow(policy, res.data.job_id, optionName(t, option));
  }

  async function use(option: Option) {
    if (!onUse) return;
    setError(null);
    setUsing(true);
    const res = await onUse(optionPolicy(option));
    if (!alive.current) return;
    setUsing(false);
    if (!res.ok) return setError(res.status === 401 || res.status === 403 ? t("common.forbidden") : t("modelQuality.error.use"));
    setChosen(null);
    toast.success(t("modelQuality.used", { name: optionName(t, option) }));
  }

  const radio = (option: Option) => {
    const policy = optionPolicy(option);
    const key = keyOf(policy);
    const id = `${groupName}-${key.replace(/[^a-z0-9-]/gi, "-")}`;
    const name = optionName(t, option);
    const inDraft = draftDiffers && samePolicy(policy, drafted);
    const delta = option.current ? null : deltaText(t, option.delta);
    return (
      <li key={key} className="min-w-0">
        <label
          htmlFor={id}
          className="flex min-w-0 cursor-pointer items-start gap-3 rounded-md border border-border p-3 has-[:checked]:border-primary has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring"
          data-slot="quality-option"
        >
          <input
            id={id}
            type="radio"
            name={groupName}
            value={key}
            checked={selected ? keyOf(optionPolicy(selected)) === key : false}
            onChange={() => setChosen(key)}
            className="mt-1 accent-primary"
          />
          <span className="grid min-w-0 flex-1 gap-1">
            <span className="flex min-w-0 flex-wrap items-center gap-2">
              <span className="font-medium break-words">{name}</span>
              {option.current ? <StatusBadge tone="positive">{t("modelQuality.badge.current")}</StatusBadge> : null}
              {inDraft ? <StatusBadge tone="info">{t("modelQuality.badge.drafted")}</StatusBadge> : null}
            </span>
            <span className="text-sm text-pretty text-muted-foreground">
              {"profile" in option ? profileLine(t, option) : `${option.provider} · ${residencyText(t, option.residency)}`}
            </span>
            <span className="flex min-w-0 flex-wrap items-center gap-x-3 gap-y-1 text-sm">
              <span className="tabular-nums">{priceText(t, option.price_per_message)}</span>
              {delta ? <span className="text-xs text-muted-foreground tabular-nums">{delta}</span> : null}
            </span>
            <CheckLine option={option} />
          </span>
        </label>
      </li>
    );
  };

  return (
    <div className="grid min-w-0 gap-4" data-slot="model-quality">
      <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("modelQuality.intro")}</p>
      {!canChange ? <p className="text-sm text-muted-foreground">{t("modelQuality.readonly")}</p> : null}
      {quality.eu_only ? <Callout tone="info">{t("modelQuality.eu")}</Callout> : null}
      {quality.suggest_auto && auto && !auto.current && !samePolicy(drafted, optionPolicy(auto)) ? (
        <Callout
          tone="info"
          action={
            canChange ? (
              <Button size="sm" variant="outline" onClick={() => setChosen(keyOf(optionPolicy(auto)))}>
                {t("modelQuality.profile.auto")}
              </Button>
            ) : undefined
          }
        >
          {auto.price_per_message
            ? t("modelQuality.suggest", { price: unitPriceText(t, auto.price_per_message) })
            : t("modelQuality.suggest.noPrice")}
        </Callout>
      ) : null}

      <DescriptionList
        layout="inline"
        items={[
          { key: "now", term: t("modelQuality.now"), detail: policyName(t, quality.current, quality.pinnable) },
          {
            key: "real",
            term: t("modelQuality.real"),
            detail: quality.real_price_7d ? <span className="tabular-nums">{priceText(t, quality.real_price_7d)}</span> : t("modelQuality.real.none"),
          },
        ]}
      />
      <p className="text-xs text-pretty text-muted-foreground">{t(`modelQuality.source.${quality.estimate_source}`)}</p>
      {draftDiffers ? (
        <p className="text-sm text-pretty" data-slot="quality-drafted">
          {t("modelQuality.drafted", { name: policyName(t, drafted, quality.pinnable) })}
        </p>
      ) : null}

      <fieldset className="grid min-w-0 gap-3" disabled={!canChange}>
        <legend className="mb-2 text-sm font-semibold">{t("modelQuality.options")}</legend>
        <ul className="grid min-w-0 gap-2">{profiles.map(radio)}</ul>
        <details className="group min-w-0 rounded-md border border-border p-3" open={pinnedOpen || undefined}>
          <summary className="cursor-pointer text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
            {t("modelQuality.pinned.title")}
          </summary>
          <div className="mt-3 grid min-w-0 gap-2">
            <p className="text-sm text-pretty text-muted-foreground">{t("modelQuality.pinned.line")}</p>
            {quality.pinnable.length ? (
              <ul aria-label={t("modelQuality.pinned.list")} className="grid min-w-0 gap-2">
                {quality.pinnable.map(radio)}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">{t("modelQuality.pinned.empty")}</p>
            )}
          </div>
        </details>
      </fieldset>

      {canChange && selected ? (
        <ChosenAction
          option={selected}
          isDraft={samePolicy(optionPolicy(selected), drafted ?? quality.current)}
          canUse={Boolean(onUse)}
          using={using}
          onCheck={() => void check(selected)}
          onUse={() => void use(selected)}
          locale={locale}
        />
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-destructive text-pretty">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** El estado de la comprobación de una opción, en palabras (el punto no basta). */
function CheckLine({ option }: { option: Option }) {
  const t = useT();
  const { status } = option.check;
  if (isChecking(option.check)) {
    return (
      <span className="inline-flex items-center gap-2 text-xs" data-slot="quality-check">
        <StatusDot tone="info" pulse />
        {t("modelQuality.check.running")}
      </span>
    );
  }
  const [tone, text] =
    status === "failed"
      ? (["danger", t("modelQuality.check.failed")] as const)
      : option.certified
        ? (["positive", t("modelQuality.check.certified")] as const)
        : status === "passed"
          ? (["positive", t("modelQuality.check.passed")] as const)
          : (["muted", t("modelQuality.check.none")] as const);
  return (
    <span className="inline-flex items-center gap-2 text-xs text-muted-foreground" data-slot="quality-check">
      <StatusDot tone={tone} />
      {text}
    </span>
  );
}

/**
 * La acción de la opción elegida, una sola: llevarla al borrador si ya está
 * comprobada; si no, comprobarla (o volver a hacerlo si no pasó, con sus
 * motivos). La que ya está en el borrador no pide nada.
 */
function ChosenAction({
  option,
  isDraft,
  canUse,
  using,
  onCheck,
  onUse,
  locale,
}: {
  option: Option;
  isDraft: boolean;
  canUse: boolean;
  using: boolean;
  onCheck: () => void;
  onUse: () => void;
  locale: string;
}) {
  const t = useT();
  const name = optionName(t, option);
  if (isDraft) return null;
  const checking = isChecking(option.check);
  return (
    <div className="grid min-w-0 gap-2 rounded-md border border-border bg-muted/40 p-3" data-slot="quality-action">
      <p role="status" className="inline-flex min-w-0 items-center gap-2 text-sm empty:hidden">
        {checking ? (
          <>
            <StatusDot tone="info" pulse />
            {t("modelQuality.check.running")}
          </>
        ) : null}
      </p>
      {option.check.status === "failed" && !checking ? (
        <ul className="grid list-disc gap-1 pl-5 text-sm" aria-label={t("modelQuality.check.failed")}>
          {(option.check.reasons.length ? option.check.reasons : ["unknown"]).map((r) => (
            <li key={r}>{reasonText(t, r, locale)}</li>
          ))}
        </ul>
      ) : null}
      {usable(option) ? (
        canUse ? (
          <div className="flex min-w-0 flex-wrap gap-2">
            <Button onClick={onUse} loading={using}>
              {t("modelQuality.use", { name })}
            </Button>
          </div>
        ) : null
      ) : (
        <>
          {!checking ? <p className="text-xs text-pretty text-muted-foreground">{t("modelQuality.use.needsCheck")} {t("modelQuality.check.cost")}</p> : null}
          <div className="flex min-w-0 flex-wrap gap-2">
            <Button
              variant={option.check.status === "failed" ? "outline" : "default"}
              onClick={onCheck}
              disabled={checking}
            >
              {t(option.check.status === "failed" ? "modelQuality.check.again" : "modelQuality.check.run", { name })}
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
