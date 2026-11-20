"use client";

import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button, Callout, Skeleton, StatusBadge, formatNumber } from "@nexus/ui";

import { agentModelAction, setAgentModelAction } from "@/app/(console)/clients/[ref]/agents/agent-model-actions";
import { useLocale, useT } from "@/i18n/client";
import type { Locale, MessageKey } from "@/i18n/messages";
import { actionErrorText } from "@/lib/action-error";
import type { AgentModel, AgentModelOption, ModelEstimate } from "@/lib/backend/models";

import type { Result } from "./builder-model";

type Ids = { ref: string; agent: string };
export type AgentModelActions = {
  load?: (body: Ids) => Promise<Result<AgentModel>>;
  save?: (body: Ids & { model_id: string }) => Promise<Result<AgentModel>>;
};

const SERVER_ACTIONS: Required<AgentModelActions> = {
  load: (body) => agentModelAction(body),
  save: (body) => setAgentModelAction(body),
};
const NO_ACTIONS: AgentModelActions = {};

type T = ReturnType<typeof useT>;

const LINES: Record<AgentModelOption["line"], MessageKey> = {
  max: "agentModel.line.max",
  balanced: "agentModel.line.balanced",
  economy: "agentModel.line.economy",
};
const PROVIDERS: Record<string, MessageKey> = {
  openai: "agentModel.provider.openai",
  anthropic: "agentModel.provider.anthropic",
};

/**
 * «≈ 62,69 USD por 1.000 respuestas»: la API da el precio de una respuesta en
 * cien milésimas, así que por cada 1.000 respuestas son `amount_micros / 100`.
 */
function priceText(t: T, locale: Locale, estimate: ModelEstimate): string {
  const amount = formatNumber(estimate.amount_micros / 100, locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return t("agentModel.price", { amount, currency: estimate.currency });
}

/**
 * Agente › Avanzado › Modelo (spec 065, T027; requisitos 1.5, 2.4, 2.7, 4.8 y
 * 9.2): el modelo con el que responde el agente y los que el partner puede
 * elegir y pagar, del más barato al más caro.
 *
 * - Solo salen modelos reales de `options`, cada uno con su proveedor, la línea
 *   de su gama y lo que costarían 1.000 respuestas de este agente con él,
 *   estimado («≈»). Sin opción para volver al modelo por defecto de Auphere y
 *   sin decir de dónde sale el modelo (2.7).
 * - El que responde (`effective`) lleva «Ahora» y es el elegido al abrir. Si no
 *   está entre las opciones (`outside_offer`), una línea dice con cuál responde,
 *   su precio y por qué, y no hay nada elegido.
 * - Si el modelo elegido no puede usar las Skills del agente (`notice`), un aviso
 *   dice con cuál responde mientras tanto (4.8).
 * - «Guardar modelo» se enciende cuando la elección cambia, y vale desde el
 *   próximo mensaje, sin publicar (2.3). Sin `agents:write` la lista se ve
 *   apagada (2.4).
 *
 * `model` en `undefined` se lee al montar; en `null`, no se pudo leer.
 */
export function AgentModelSelect({
  refId,
  agentId,
  agentName,
  model: initial,
  canWrite,
  actions: given = NO_ACTIONS,
}: {
  refId: string;
  agentId: string;
  /** Para el toast: «{agente} responde con {modelo} desde el próximo mensaje». */
  agentName: string;
  model?: AgentModel | null;
  canWrite: boolean;
  actions?: AgentModelActions;
}) {
  const t = useT();
  const locale = useLocale();
  const router = useRouter();
  const actions = React.useMemo(() => ({ ...SERVER_ACTIONS, ...given }), [given]);
  const ids = React.useMemo(() => ({ ref: refId, agent: agentId }), [refId, agentId]);
  const [data, setData] = React.useState<AgentModel | null | undefined>(initial);
  // La página vuelve a leer el modelo al refrescar (también al guardar el tope de
  // al lado): lo nuevo manda, y lo que se eligió sin guardar sigue elegido mientras
  // el agente responda con el mismo modelo.
  const [seen, setSeen] = React.useState(initial);
  const [picked, setPicked] = React.useState<string | null>(null);
  if (seen !== initial) {
    setSeen(initial);
    setData(initial);
    if (initial?.effective.model_id !== data?.effective.model_id) setPicked(null);
  }
  const [loading, setLoading] = React.useState(initial === undefined);
  const [saving, setSaving] = React.useState(false);
  const alive = React.useRef(true);
  React.useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);
  const headingId = React.useId();
  const groupName = React.useId();

  const load = React.useCallback(async () => {
    setLoading(true);
    const res = await actions.load(ids);
    if (!alive.current) return;
    setLoading(false);
    setPicked(null);
    setData(res.ok ? res.data : null);
  }, [actions, ids]);

  // Sin datos del servidor: se leen al montar.
  const asked = React.useRef(initial !== undefined);
  React.useEffect(() => {
    if (asked.current) return;
    asked.current = true;
    void load();
  }, [load]);

  // Lo que se puede elegir y lo elegido (con datos; sin ellos, nada de esto se usa).
  const options = data?.options ?? [];
  const effective = data?.effective ?? null;
  const readOnly = !canWrite || !data?.can_change;
  // El que responde sale elegido si está entre las opciones; si no, nada.
  const preselected = effective && options.some((o) => o.model_id === effective.model_id) ? effective.model_id : null;
  const selected = picked !== null && options.some((o) => o.model_id === picked) ? picked : preselected;
  // Se compara con lo guardado, no con el que responde: con el aviso (4.8) lo guardado es el
  // que no puede, y guardar el que responde ahora lo deja como elegido y quita el aviso.
  const stored = data?.choice?.model_id ?? preselected;
  const dirty = selected !== null && selected !== stored;
  // Un agente sin consumo se estima con una conversación típica: la entrada lo dice.
  const nominal = [effective?.estimate, ...options.map((o) => o.estimate)].some((e) => e?.basis === "nominal");
  const intro = t(nominal ? "agentModel.introNominal" : "agentModel.intro");

  async function save() {
    if (!selected || !dirty || readOnly) return;
    setSaving(true);
    const res = await actions.save({ ...ids, model_id: selected });
    if (!alive.current) return;
    setSaving(false);
    if (!res.ok) {
      toast.error(res.status === 422 ? t("agentModel.error.unavailable") : actionErrorText(res, t));
      return;
    }
    setPicked(null);
    setData(res.data);
    toast.success(t("agentModel.saved", { agent: agentName, model: res.data.effective.display_name }));
    router.refresh();
  }

  let body: React.ReactNode;
  if (data === undefined || loading) {
    body = <ModelSkeleton />;
  } else if (data === null || effective === null) {
    body = (
      <Callout
        tone="danger"
        title={t("agentModel.error.title")}
        action={
          <Button size="sm" variant="outline" onClick={() => void load()}>
            {t("agentModel.retry")}
          </Button>
        }
      >
        {t("agentModel.error.body")}
      </Callout>
    );
  } else if (options.length === 0) {
    body = (
      <>
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{intro}</p>
        <div className="grid min-w-0 gap-1" data-slot="agent-model-empty">
          <p className="min-w-0 text-sm font-medium text-pretty break-words">
            {effective.estimate
              ? t("agentModel.empty.now", { model: effective.display_name, price: priceText(t, locale, effective.estimate) })
              : t("agentModel.empty.nowNoPrice", { model: effective.display_name })}
          </p>
          <p className="min-w-0 text-sm text-pretty text-muted-foreground">{t("agentModel.empty.body")}</p>
        </div>
      </>
    );
  } else {
    const outside = effective.outside_offer;
    const price = effective.estimate ? priceText(t, locale, effective.estimate) : null;
    body = (
      <>
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{intro}</p>
        {data.notice === "chosen_model_cannot_run_agent" && data.choice ? (
          <Callout tone="warning" title={t("agentModel.notice.title", { model: data.choice.display_name })}>
            {t("agentModel.notice.body", { fallback: effective.display_name })}
          </Callout>
        ) : null}
        {outside ? (
          <Callout tone="info">
            {outside === "operator"
              ? price
                ? t("agentModel.outside.operator", { model: effective.display_name, price })
                : t("agentModel.outside.operatorNoPrice", { model: effective.display_name })
              : price
                ? t("agentModel.outside.retired", { model: effective.display_name, price })
                : t("agentModel.outside.retiredNoPrice", { model: effective.display_name })}
          </Callout>
        ) : null}
        {options.some((o) => o.estimate === null) ? <Callout tone="info">{t("agentModel.partial")}</Callout> : null}

        <fieldset role="radiogroup" aria-labelledby={headingId} disabled={readOnly || saving} className="min-w-0">
          <ul className="grid min-w-0 gap-2">
            {options.map((option) => (
              <ModelOption
                key={option.model_id}
                option={option}
                name={groupName}
                checked={selected === option.model_id}
                now={!outside && option.model_id === effective.model_id}
                price={option.estimate ? priceText(t, locale, option.estimate) : null}
                onPick={() => setPicked(option.model_id)}
              />
            ))}
          </ul>
        </fieldset>

        {readOnly ? (
          <p className="min-w-0 text-sm text-pretty text-muted-foreground">{t("agentModel.readonly")}</p>
        ) : (
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <Button type="button" size="sm" onClick={() => void save()} disabled={!dirty} loading={saving}>
              {t("agentModel.save")}
            </Button>
            <p className="min-w-0 text-xs text-pretty text-muted-foreground">{t("agentModel.hint")}</p>
          </div>
        )}
      </>
    );
  }

  return (
    <section aria-labelledby={headingId} className="grid min-w-0 gap-4" data-slot="agent-model">
      <h3 id={headingId} className="text-sm font-semibold text-balance">
        {t("agentModel.title")}
      </h3>
      {body}
    </section>
  );
}

/**
 * Una tarjeta: el nombre (su nombre accesible), «Ahora» si responde con él, el
 * proveedor, la línea de su gama y el precio. Toda la tarjeta es la diana.
 */
function ModelOption({
  option,
  name,
  checked,
  now,
  price,
  onPick,
}: {
  option: AgentModelOption;
  name: string;
  checked: boolean;
  now: boolean;
  price: string | null;
  onPick: () => void;
}) {
  const t = useT();
  const base = React.useId();
  const id = `${base}-input`;
  const nameId = `${base}-name`;
  const described = [now ? `${base}-now` : null, `${base}-provider`, LINES[option.line] ? `${base}-line` : null, price ? `${base}-price` : null]
    .filter(Boolean)
    .join(" ");
  const provider = PROVIDERS[option.provider];
  const line = LINES[option.line];
  return (
    <li className="min-w-0">
      <label
        htmlFor={id}
        data-slot="model-option"
        className="flex min-w-0 cursor-pointer items-start gap-3 rounded-md border border-border bg-card p-3 transition-colors hover:bg-muted/60 has-[:checked]:border-primary has-[:disabled]:cursor-not-allowed has-[:disabled]:hover:bg-card has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring motion-reduce:transition-none"
      >
        <input
          id={id}
          type="radio"
          name={name}
          value={option.model_id}
          checked={checked}
          onChange={onPick}
          aria-labelledby={nameId}
          aria-describedby={described}
          className="mt-1 size-4 shrink-0 accent-primary"
        />
        <span className="grid min-w-0 flex-1 gap-1" data-slot="model-option-body">
          <span className="flex min-w-0 flex-wrap items-center gap-2">
            <span id={nameId} className="min-w-0 text-sm font-medium break-words">
              {option.display_name}
            </span>
            {now ? (
              <StatusBadge id={`${base}-now`} tone="positive">
                {t("agentModel.now")}
              </StatusBadge>
            ) : null}
          </span>
          <span id={`${base}-provider`} className="min-w-0 text-xs break-words text-muted-foreground">
            {provider ? t(provider) : option.provider}
          </span>
          {line ? (
            <span id={`${base}-line`} className="min-w-0 text-sm text-pretty text-muted-foreground">
              {t(line)}
            </span>
          ) : null}
          {price ? (
            <span id={`${base}-price`} className="min-w-0 text-sm tabular-nums">
              {price}
            </span>
          ) : null}
        </span>
      </label>
    </li>
  );
}

/** Mientras se lee: el marco de tres tarjetas, con las mismas líneas que las de verdad. */
function ModelSkeleton() {
  const t = useT();
  return (
    <div className="grid min-w-0 gap-4" aria-busy="true" data-slot="agent-model-loading">
      <p role="status" className="sr-only">
        {t("common.loading")}
      </p>
      <div className="grid max-w-prose gap-1">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-2/3" />
      </div>
      <ul className="grid min-w-0 gap-2">
        {[0, 1, 2].map((i) => (
          <li key={i} className="flex min-w-0 items-start gap-3 rounded-md border border-border p-3" data-slot="model-option-skeleton">
            <span className="mt-1 size-4 shrink-0 rounded-full border border-border" />
            <span className="grid min-w-0 flex-1 gap-1">
              <Skeleton className="h-5 w-24" />
              <Skeleton className="h-4 w-16" />
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-5 w-48 max-w-full" />
            </span>
          </li>
        ))}
      </ul>
      <Skeleton className="h-8 w-36" />
    </div>
  );
}
