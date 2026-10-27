"use client";

import { ChevronDown, X } from "lucide-react";
import * as React from "react";

import {
  Alert,
  AlertDescription,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Field,
  Input,
  NativeSelect,
  Switch,
  Textarea,
} from "@nexus/ui";

import {
  createClientV2Action,
  detectClientLinksAction,
  nicheSuggestionsAction,
} from "@/app/(console)/clients/new-client-actions";
import { useLocale, useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type {
  DeductionSource,
  DetectedLink,
  LinkDetection,
  Network,
  NewClientBody,
  NewClientCreated,
  NicheSuggestion,
} from "@/lib/backend/clients-v2";

import {
  COUNTRIES,
  EMPTY_SETTINGS,
  INFO_MAX,
  NAME_MAX,
  NICHE_MAX,
  NO_EDITS,
  PRICE_CURRENCIES,
  canSubmit,
  displayName,
  draftProblems,
  isEuEea,
  mergeNicheSuggestion,
  newClientBody,
  newIdempotencyKey,
  shownChips,
  sourceKey,
  timezoneOptions,
  visibleSuggestions,
  applyDeduction,
  browserHints,
  type ChipEdits,
  type ClientDraft,
  type SettingKey,
  type Settings,
  type ShownChip,
} from "./client-modal-model";

type Failed = { ok: false; status: number; message: string; code?: string | null };
type Result<T> = { ok: true; data: T } | Failed;

/** Lo que el modal pide fuera. Por defecto, las acciones de servidor; las pruebas ponen las suyas. */
export type ClientModalActions = {
  detect: (body: { info: string; browser_timezone: string | null; browser_locale: string | null }) => Promise<Result<LinkDetection>>;
  suggest: (body: { q: string }) => Promise<Result<NicheSuggestion[]>>;
  create: (body: NewClientBody & { idempotency_key: string }) => Promise<Result<NewClientCreated>>;
};

const DEFAULT_ACTIONS: ClientModalActions = {
  detect: (b) => detectClientLinksAction(b),
  suggest: (b) => nicheSuggestionsAction(b),
  create: (b) => createClientV2Action(b),
};

/** Lo que tarda en mirarse lo escrito: lo justo para no preguntar a cada tecla. */
export const DETECT_DEBOUNCE_MS = 350;

export type ClientModalProps = {
  mode: "create" | "edit";
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Al editar: lo que tiene hoy. */
  initial?: Partial<Omit<ClientDraft, "settings">> & { settings?: Partial<Settings> };
  /** Tras crear (lo usa el botón para llevar al Panel). */
  onCreated?: (created: NewClientCreated) => void;
  /** Al editar: guardar es de quien abre el modal (T063, `PATCH` con `If-Match`). */
  onSave?: (body: NewClientBody) => Promise<Result<unknown>>;
  actions?: Partial<ClientModalActions>;
};

/**
 * El modal «Nuevo cliente» / «Editar cliente» (spec 047, requisitos 4, 5.1 y
 * 6.1): tres datos —nombre, nicho e información— y «Más ajustes» con lo
 * deducido. Mientras se escribe la información salen los chips de lo que irá a
 * la ficha; un `@` suelto se propone como Instagram y se puede cambiar.
 *
 * Crear un cliente **nunca** crea un agente: lo dice la API, y aquí no hay
 * plantilla que elegir. El mismo modal sirve para editar.
 */
export function ClientModal({ mode, open, onOpenChange, initial, onCreated, onSave, actions }: ClientModalProps) {
  const t = useT();
  const locale = useLocale();
  const act = React.useMemo(() => ({ ...DEFAULT_ACTIONS, ...actions }), [actions]);
  const ids = { name: React.useId(), niche: React.useId(), info: React.useId(), more: React.useId() };

  const [name, setName] = React.useState(initial?.name ?? "");
  const [niche, setNiche] = React.useState(initial?.niche ?? "");
  const [info, setInfo] = React.useState(initial?.info ?? "");
  const [settings, setSettings] = React.useState<Settings>({ ...EMPTY_SETTINGS, ...initial?.settings });
  const [touched, setTouched] = React.useState<Set<SettingKey>>(() => new Set(mode === "edit" ? (Object.keys(EMPTY_SETTINGS) as SettingKey[]) : []));
  const [source, setSource] = React.useState<DeductionSource | null>(null);
  const [links, setLinks] = React.useState<DetectedLink[]>([]);
  const [edits, setEdits] = React.useState<ChipEdits>(NO_EDITS);
  const [detecting, setDetecting] = React.useState(false);
  const [detectFailed, setDetectFailed] = React.useState(false);
  const [suggestions, setSuggestions] = React.useState<NicheSuggestion[]>([]);
  const [more, setMore] = React.useState(false);
  const [showErrors, setShowErrors] = React.useState(false);
  const [failure, setFailure] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();
  const idempotencyKey = React.useRef(newIdempotencyKey());

  // Lo escrito en la información → chips y «Más ajustes». Las respuestas que
  // llegan tarde (de un texto que ya cambió) se descartan.
  const seq = React.useRef(0);
  React.useEffect(() => {
    if (!open) return;
    const mine = ++seq.current;
    const handle = window.setTimeout(() => {
      setDetecting(true);
      void act
        .detect({ info, ...browserHints() })
        .then((res) => {
          if (mine !== seq.current) return;
          if (res.ok) {
            setLinks(res.data.links);
            setSource(res.data.deduced.source);
            setSettings((current) => applyDeduction(current, res.data.deduced, touched));
            setDetectFailed(false);
          } else {
            setDetectFailed(true);
          }
        })
        .catch(() => mine === seq.current && setDetectFailed(true))
        .finally(() => mine === seq.current && setDetecting(false));
    }, DETECT_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
    // `touched` se lee al llegar la respuesta; cambiarlo no es motivo para volver a preguntar.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [info, open, act]);

  // Las sugerencias de nicho: las de las plantillas y los más usados del partner.
  React.useEffect(() => {
    if (!open) return;
    let live = true;
    const handle = window.setTimeout(() => {
      void act
        .suggest({ q: niche.trim().length >= 2 ? niche.trim() : "" })
        .then((res) => live && res.ok && setSuggestions(res.data))
        .catch(() => undefined);
    }, DETECT_DEBOUNCE_MS);
    return () => {
      live = false;
      window.clearTimeout(handle);
    };
  }, [niche, open, act]);

  const problems = draftProblems({ name, niche, info });
  const ready = canSubmit({ name, niche, info });
  const chips = shownChips(links, edits);
  const visible = visibleSuggestions(suggestions, niche);

  const label = (s: NicheSuggestion) => (s.source === "template" && s.key ? t(`business.niche.${s.key}` as MessageKey) : (s.value ?? ""));
  const networkLabel = (n: Network) => t(`business.links.network.${n}` as MessageKey);

  function touch<K extends SettingKey>(key: K, value: Settings[K]) {
    setTouched((prev) => new Set(prev).add(key));
    setSettings((prev) => {
      const next = { ...prev, [key]: value };
      // Elegir un país propone su «Solo UE» si la persona no lo tocó.
      if (key === "country" && !touched.has("eu_only")) next.eu_only = isEuEea(value as string | null);
      return next;
    });
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!ready) {
      setShowErrors(true);
      return;
    }
    setFailure(null);
    const body = newClientBody({ name, niche, info, settings }, links, edits);
    startTransition(async () => {
      if (mode === "edit") {
        const res = onSave ? await onSave(body) : null;
        if (res && !res.ok) setFailure(t("business.error.save"));
        else onOpenChange(false);
        return;
      }
      const res = await act.create({ ...body, idempotency_key: idempotencyKey.current });
      if (!res.ok) {
        setFailure(res.status === 409 ? t("business.error.quota") : t("business.error.create"));
        return;
      }
      idempotencyKey.current = newIdempotencyKey();
      onCreated?.(res.data);
    });
  }

  const fieldError = (key: "name" | "niche" | "info") => {
    const p = problems[key];
    return showErrors && p ? t(`business.error.${key}.${p}` as MessageKey) : undefined;
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-xl" data-slot="client-modal">
        <form onSubmit={submit} noValidate className="grid min-w-0 gap-4">
          <DialogHeader>
            <DialogTitle className="text-balance">{t(mode === "create" ? "business.client.new.title" : "business.client.edit.title")}</DialogTitle>
            <DialogDescription className="text-pretty">
              {t(mode === "create" ? "business.client.new.description" : "business.client.edit.description")}
            </DialogDescription>
          </DialogHeader>

          <Field label={t("business.field.name")} htmlFor={ids.name} required requiredLabel={t("business.field.required")} hint={t("business.field.name.hint")} error={fieldError("name")}>
            {(a11y) => (
              <Input {...a11y} value={name} maxLength={NAME_MAX} autoComplete="organization" placeholder={t("business.field.name.placeholder")} onChange={(e) => setName(e.target.value)} />
            )}
          </Field>

          <div className="grid min-w-0 gap-2">
            <Field label={t("business.field.niche")} htmlFor={ids.niche} required requiredLabel={t("business.field.required")} hint={t("business.field.niche.hint")} error={fieldError("niche")}>
              {(a11y) => <Input {...a11y} value={niche} maxLength={NICHE_MAX} placeholder={t("business.field.niche.placeholder")} onChange={(e) => setNiche(e.target.value)} />}
            </Field>
            {visible.length > 0 ? (
              <div className="flex min-w-0 flex-wrap items-center gap-2" role="group" aria-label={t("business.niche.suggestions")}>
                <span className="text-xs text-muted-foreground">{t("business.niche.suggestions")}</span>
                {visible.map((s) => {
                  const text = label(s);
                  return (
                    <Button
                      key={`${s.source}:${s.key ?? s.value}`}
                      type="button"
                      variant="outline"
                      size="xs"
                      className="max-w-full min-w-0"
                      title={s.group ? t(`business.niche.group.${s.group}` as MessageKey) : undefined}
                      aria-label={t("business.niche.add", { label: text })}
                      onClick={() => setNiche((current) => mergeNicheSuggestion(current, text))}
                    >
                      <span className="truncate">{text}</span>
                    </Button>
                  );
                })}
              </div>
            ) : null}
          </div>

          <div className="grid min-w-0 gap-2">
            <Field label={t("business.field.info")} htmlFor={ids.info} optionalLabel={t("business.field.optional")} hint={t("business.field.info.hint")} error={fieldError("info")}>
              {(a11y) => (
                <Textarea {...a11y} value={info} maxLength={INFO_MAX} rows={3} placeholder={t("business.field.info.placeholder")} onChange={(e) => setInfo(e.target.value)} />
              )}
            </Field>
            <p className="text-right text-xs text-muted-foreground tabular-nums" aria-live="polite">
              {t("business.field.count", { n: info.length, max: INFO_MAX })}
            </p>
            <LinkChips
              chips={chips}
              detecting={detecting}
              failed={detectFailed}
              networkLabel={networkLabel}
              onRemove={(chip) => setEdits((e) => ({ ...e, removed: [...e.removed, chip.origin] }))}
              onChange={(chip, network) => setEdits((e) => ({ ...e, network: { ...e.network, [chip.origin]: network } }))}
            />
          </div>

          <section className="grid min-w-0 gap-3" aria-labelledby={`${ids.more}-toggle`}>
            <Button
              id={`${ids.more}-toggle`}
              type="button"
              variant="ghost"
              size="sm"
              className="justify-self-start"
              aria-expanded={more}
              aria-controls={ids.more}
              onClick={() => setMore((v) => !v)}
            >
              {t("business.settings.toggle")}
              <ChevronDown aria-hidden="true" className={more ? "rotate-180 transition-transform motion-reduce:transition-none" : "transition-transform motion-reduce:transition-none"} />
            </Button>
            <div id={ids.more} hidden={!more} className={more ? "grid min-w-0 gap-3 sm:grid-cols-2" : "hidden"}>
              {source ? <p className="text-xs text-muted-foreground text-pretty sm:col-span-2">{t(sourceKey(source))}</p> : null}
              <MoreSettings settings={settings} locale={locale} onChange={touch} t={t} />
            </div>
          </section>

          {failure ? (
            <Alert variant="destructive">
              <AlertDescription>{failure}</AlertDescription>
            </Alert>
          ) : null}

          <DialogFooter className="items-center sm:justify-between">
            <p className="text-xs text-muted-foreground" aria-live="polite">
              {!ready ? t("business.submit.required") : null}
            </p>
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
                {t("business.submit.cancel")}
              </Button>
              <Button type="submit" disabled={!ready || pending} aria-disabled={!ready || pending}>
                {pending
                  ? t(mode === "create" ? "business.submit.creating" : "business.submit.saving")
                  : t(mode === "create" ? "business.submit.create" : "business.submit.save")}
              </Button>
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function LinkChips({
  chips,
  detecting,
  failed,
  networkLabel,
  onRemove,
  onChange,
}: {
  chips: ShownChip[];
  detecting: boolean;
  failed: boolean;
  networkLabel: (n: Network) => string;
  onRemove: (chip: ShownChip) => void;
  onChange: (chip: ShownChip, network: Network) => void;
}) {
  const t = useT();
  if (!chips.length) {
    if (failed) return <p className="text-xs text-muted-foreground text-pretty">{t("business.links.failed")}</p>;
    return detecting ? (
      <p className="text-xs text-muted-foreground" aria-live="polite">
        {t("business.links.checking")}
      </p>
    ) : null;
  }
  const guessed = chips.some((c) => c.guessed);
  return (
    <div className="grid min-w-0 gap-2" data-slot="link-chips">
      <p className="text-xs font-medium text-muted-foreground">{t("business.links.title")}</p>
      <ul className="flex min-w-0 flex-wrap gap-2" aria-label={t("business.links.listLabel")}>
        {chips.map((chip) => {
          const target = chip.target === "website" ? t("business.links.target.website") : t("business.links.target.links", { network: networkLabel(chip.network) });
          return (
            <li key={chip.origin} className="flex max-w-full min-w-0 items-center gap-1 rounded-sm border border-border bg-muted/40 py-1 pr-1 pl-2 text-xs">
              <span className="min-w-0 truncate font-medium" title={chip.value}>
                {chip.value}
              </span>
              <span className="shrink-0 text-muted-foreground">· {target}</span>
              {chip.guessed && chip.handle ? (
                <NativeSelect
                  size="sm"
                  aria-label={t("business.links.change", { value: chip.value })}
                  value={chip.network}
                  onChange={(e) => onChange(chip, e.target.value as Network)}
                  className="h-6 text-xs"
                >
                  {[chip.network, ...chip.alternatives.filter((n) => n !== chip.network)].map((n) => (
                    <option key={n} value={n}>
                      {networkLabel(n)}
                    </option>
                  ))}
                </NativeSelect>
              ) : null}
              <Button type="button" variant="ghost" size="icon-xs" aria-label={t("business.links.remove", { value: chip.value })} onClick={() => onRemove(chip)}>
                <X aria-hidden="true" />
              </Button>
            </li>
          );
        })}
      </ul>
      {guessed ? <p className="text-xs text-muted-foreground text-pretty">{t("business.links.guessed")}</p> : null}
    </div>
  );
}

function MoreSettings({
  settings,
  locale,
  onChange,
  t,
}: {
  settings: Settings;
  locale: string;
  onChange: <K extends SettingKey>(key: K, value: Settings[K]) => void;
  t: (key: MessageKey, vars?: Record<string, string | number>) => string;
}) {
  const euId = React.useId();
  const zones = React.useMemo(() => timezoneOptions(settings.timezone), [settings.timezone]);
  const countries = React.useMemo(
    () => [...COUNTRIES].map((code) => ({ code, name: displayName(locale, "region", code) })).sort((a, b) => a.name.localeCompare(b.name, locale)),
    [locale],
  );
  const currencies = React.useMemo(() => Array.from(new Set([...PRICE_CURRENCIES, ...(settings.price_currency ? [settings.price_currency] : [])])), [settings.price_currency]);
  return (
    <>
      <Field label={t("business.settings.country")}>
        {(a11y) => (
          <NativeSelect {...a11y} value={settings.country ?? ""} onChange={(e) => onChange("country", e.target.value || null)} wrapperClassName="w-full">
            <option value="">{t("business.settings.countryNone")}</option>
            {countries.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      <Field label={t("business.settings.timezone")}>
        {(a11y) => (
          <NativeSelect {...a11y} value={settings.timezone} onChange={(e) => onChange("timezone", e.target.value)} wrapperClassName="w-full">
            {zones.map((z) => (
              <option key={z} value={z}>
                {z.replaceAll("_", " ")}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      <Field label={t("business.settings.priceCurrency")} hint={t("business.settings.priceCurrency.hint")}>
        {(a11y) => (
          <NativeSelect {...a11y} value={settings.price_currency ?? ""} onChange={(e) => onChange("price_currency", e.target.value || null)} wrapperClassName="w-full">
            <option value="">{t("business.settings.priceCurrencyNone")}</option>
            {currencies.map((c) => (
              <option key={c} value={c}>
                {`${c} · ${displayName(locale, "currency", c)}`}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      <Field label={t("business.settings.walletCurrency")} hint={t("business.settings.walletCurrency.hint")}>
        {(a11y) => (
          <NativeSelect {...a11y} value={settings.wallet_currency} onChange={(e) => onChange("wallet_currency", e.target.value as Settings["wallet_currency"])} wrapperClassName="w-full">
            {(["EUR", "USD"] as const).map((c) => (
              <option key={c} value={c}>
                {`${c} · ${displayName(locale, "currency", c)}`}
              </option>
            ))}
          </NativeSelect>
        )}
      </Field>
      <div className="flex min-w-0 items-start justify-between gap-3 sm:col-span-2">
        <div className="grid min-w-0 gap-1">
          <span id={euId} className="text-sm font-medium">
            {t("business.settings.euOnly")}
          </span>
          <span className="text-xs text-muted-foreground text-pretty">{t("business.settings.euOnly.hint")}</span>
        </div>
        <Switch aria-labelledby={euId} checked={settings.eu_only} onCheckedChange={(checked) => onChange("eu_only", checked)} />
      </div>
    </>
  );
}
