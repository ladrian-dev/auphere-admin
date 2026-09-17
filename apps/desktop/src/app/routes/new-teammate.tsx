/**
 * Crear un teammate desde la aplicación — spec 003, Requisito 2.1.
 *
 * Cuatro decisiones y ninguna más: cómo se llama, de qué trabaja, con qué
 * cerebro y qué se le deja hacer. Los permisos son **interruptores**, no una
 * lista de herramientas: la pantalla no sabe —ni tiene que saber— qué
 * herramientas da cada uno; eso lo traduce la plataforma, y que no lo sepa es
 * lo que impide que la aplicación amplíe el catálogo (garantía 2).
 *
 * Lo que este componente sí decide es todo lo que puede salir mal al escribir:
 * el nombre se corta donde la columna termina, el envío no se puede repetir, y
 * un fallo **conserva lo escrito** — volver a teclear un formulario por un 422
 * es la forma más barata de perder a alguien.
 */
import { Button, Input, Label, Skeleton } from "@nexus/ui";
import * as React from "react";

import { type AppKey, useAppT } from "../i18n";

export type CostLabel = "bajo" | "medio" | "alto" | "desconocido";
export type ModelChoice = { id: string; note: string; cost_label: CostLabel };

export type TeammatePermissions = {
  read: boolean;
  write: boolean;
  spend: boolean;
  publish: boolean;
  contact: boolean;
};

export type TeammateDraft = {
  name: string;
  job: string;
  model: string;
  permissions: TeammatePermissions;
  local_exec: boolean;
};

/**
 * El tope del nivel, tal y como lo manda la plataforma (spec 005, R1.2).
 *
 * `TierLimitReached` carga estos tres números a propósito — su docstring dice
 * por qué: «a message that only says "limit reached" makes someone open a
 * support ticket to learn a number we already know». Llegan hasta aquí y hasta
 * hace poco se tiraban en `App.tsx`.
 */
export type TierCap = { limit: number; current: number; tier: string };

export type SubmitResult = { ok: true } | { ok: false; error: string; cap?: TierCap };

export type NewTeammateFormProps = {
  status: "loading" | "ready" | "error";
  jobs: string[];
  models: ModelChoice[];
  onSubmit: (draft: TeammateDraft) => Promise<SubmitResult>;
  onCancel: () => void;
  onRetry: () => void;
};

/** El límite de la columna (`teammates.name`). Cortar aquí evita un 422 al final. */
export const NAME_MAX = 80;

/** Lo mínimo encendido: leer. Todo lo que cambia algo nace apagado. */
const SAFE_DEFAULTS: TeammatePermissions = {
  read: true,
  write: false,
  spend: false,
  publish: false,
  contact: false,
};

export const PERMISSION_ORDER: (keyof TeammatePermissions)[] = [
  "read",
  "write",
  "spend",
  "publish",
  "contact",
];

/** Los códigos que la plataforma sabe decir. El resto se cuenta en general —
 *  enseñar el código crudo no ayuda a nadie a arreglar nada. */
const KNOWN_ERRORS = ["model_not_allowed", "tool_not_in_catalog", "tier_limit_reached"] as const;
type KnownError = (typeof KNOWN_ERRORS)[number];
export const isKnownError = (code: string): code is KnownError =>
  (KNOWN_ERRORS as readonly string[]).includes(code);

/**
 * Qué frase toca para un rechazo por tope de plan.
 *
 * Se apoya en `limit` y **no** en el `kind` que manda la API: el mismo código
 * lo lanza `assert_can_add_member` para personas, y dar por supuesto que
 * siempre son teammates dejaría una frase mintiendo el día que esa ruta llegue
 * a esta pantalla.
 *
 * Sin `cap` —el cuerpo viene de la red— se cae a la frase sin números, nunca a
 * un hueco.
 */
export function tierCopyKey(cap: TierCap | undefined): AppKey {
  if (!cap || !Number.isFinite(cap.limit)) return "create.failed.tier_limit_reached";
  return cap.limit === 0 ? "create.failed.tier_none" : "create.failed.tier_full";
}

/**
 * El tope del nivel, si el rechazo lo trae.
 *
 * `Err.body` viene de la red y no se confía en su forma: si falta, si llega con
 * otra, o si los números no son números, se devuelve nada y la pantalla dice lo
 * que sí sabe. Devolver `{}` en vez de `{ cap: undefined }` es lo que deja que
 * el llamante lo esparza sin pisar el campo.
 *
 * Lo que NO se hace aquí es mirar `kind`: el mismo código lo lanza el tope de
 * personas, y la frase la elige la pantalla a partir de `limit`.
 */
export function capOf(body: unknown): { cap?: TierCap } {
  if (!body || typeof body !== "object") return {};
  const b = body as Record<string, unknown>;
  const { limit, current, tier } = b;
  if (typeof limit !== "number" || typeof current !== "number" || typeof tier !== "string") {
    return {};
  }
  return { cap: { limit, current, tier } };
}

export function NewTeammateForm({
  status,
  jobs,
  models,
  onSubmit,
  onCancel,
  onRetry,
}: NewTeammateFormProps) {
  const t = useAppT();
  const [name, setName] = React.useState("");
  const [job, setJob] = React.useState("");
  const [model, setModel] = React.useState("");
  const [permissions, setPermissions] = React.useState<TeammatePermissions>(SAFE_DEFAULTS);
  const [localExec, setLocalExec] = React.useState(false);
  const [sending, setSending] = React.useState(false);
  const [failed, setFailed] = React.useState<string | null>(null);
  // El tope viaja aparte del código: sin él la frase no puede dar números.
  const [cap, setCap] = React.useState<TierCap | undefined>(undefined);

  // El oficio y el modelo llegan con la lista; se eligen los primeros hasta que
  // la persona diga otra cosa. Un formulario que empieza sin nada elegido
  // obliga a decidir dos veces lo que casi siempre es lo mismo.
  React.useEffect(() => {
    setJob((current) => current || (jobs[0] ?? ""));
  }, [jobs]);
  React.useEffect(() => {
    setModel((current) => current || (models[0]?.id ?? ""));
  }, [models]);

  if (status === "loading") {
    return (
      <div className="flex flex-col gap-3 p-6" role="status" aria-busy="true">
        <span className="sr-only">{t("create.loading")}</span>
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className="flex flex-col items-start gap-3 p-6" role="status">
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">{t("create.error")}</p>
        <Button variant="outline" size="sm" onClick={onRetry}>
          {t("roster.retry")}
        </Button>
      </div>
    );
  }

  // Sin modelos no hay teammate posible: la lista la decide un administrador en
  // la consola. Pintar el formulario y fallar al enviar sería hacerle escribir
  // para nada (§V).
  if (models.length === 0) {
    return (
      <div className="flex flex-col items-start gap-3 p-6" role="status">
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">
          {t("create.noModels")}
        </p>
        <Button variant="outline" size="sm" onClick={onCancel}>
          {t("create.cancel")}
        </Button>
      </div>
    );
  }

  const ready = name.trim().length > 0 && job.trim().length > 0 && model.length > 0;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!ready || sending) return;
    setSending(true);
    setFailed(null);
    setCap(undefined);
    const result = await onSubmit({
      name: name.trim(),
      job: job.trim(),
      model,
      permissions,
      local_exec: localExec,
    });
    setSending(false);
    if (!result.ok) {
      setFailed(result.error);
      setCap(result.cap);
    }
  };

  return (
    <form className="flex min-w-0 flex-col gap-5 p-6" onSubmit={(e) => void submit(e)} noValidate>
      <h2 className="text-base font-semibold text-balance">{t("create.title")}</h2>

      <div className="flex min-w-0 flex-col gap-2">
        <Label htmlFor="teammate-name">{t("create.name")}</Label>
        <Input
          id="teammate-name"
          value={name}
          maxLength={NAME_MAX}
          autoComplete="off"
          onChange={(e) => setName(e.target.value.slice(0, NAME_MAX))}
        />
      </div>

      <div className="flex min-w-0 flex-col gap-2">
        <Label htmlFor="teammate-job">{t("create.job")}</Label>
        {/* Semilla editable: la lista ayuda, no encierra (R2.1). */}
        <Input
          id="teammate-job"
          list="teammate-jobs"
          value={job}
          maxLength={NAME_MAX}
          autoComplete="off"
          onChange={(e) => setJob(e.target.value.slice(0, NAME_MAX))}
        />
        <datalist id="teammate-jobs">
          {/* Con texto y no solo `value`: así la opción tiene nombre accesible
              y un lector de pantalla puede leer la semilla. */}
          {jobs.map((seed) => (
            <option key={seed} value={seed}>
              {seed}
            </option>
          ))}
        </datalist>
      </div>

      <fieldset className="flex min-w-0 flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">{t("create.model")}</legend>
        {models.map((choice) => (
          <label
            key={choice.id}
            className="flex min-w-0 cursor-pointer items-start gap-2 rounded-md border border-border p-2 text-sm has-[:checked]:border-primary"
          >
            <input
              type="radio"
              name="teammate-model"
              className="mt-1"
              value={choice.id}
              checked={model === choice.id}
              onChange={() => setModel(choice.id)}
            />
            <span className="flex min-w-0 flex-col">
              <span className="font-medium">{choice.note}</span>
              <span className="text-xs text-pretty text-muted-foreground">
                {t(`create.cost.${choice.cost_label}`)}
              </span>
            </span>
          </label>
        ))}
      </fieldset>

      <fieldset className="flex min-w-0 flex-col gap-2">
        <legend className="mb-1 text-sm font-medium">{t("create.permissions")}</legend>
        {PERMISSION_ORDER.map((key) => (
          <PermissionSwitch
            key={key}
            label={t(`create.perm.${key}`)}
            hint={t(`create.perm.${key}.hint`)}
            checked={permissions[key]}
            onToggle={() => setPermissions((p) => ({ ...p, [key]: !p[key] }))}
          />
        ))}
        <PermissionSwitch
          label={t("create.perm.local_exec")}
          hint={t("create.perm.local_exec.hint")}
          checked={localExec}
          onToggle={() => setLocalExec((v) => !v)}
        />
      </fieldset>

      {failed ? (
        <p className="max-w-prose text-sm text-pretty text-status-warning" role="alert">
          {failed === "tier_limit_reached"
            ? t(tierCopyKey(cap), cap ? { limit: cap.limit, current: cap.current } : undefined)
            : t(isKnownError(failed) ? `create.failed.${failed}` : "create.failed.unknown")}
        </p>
      ) : null}

      <div className="flex gap-2">
        <Button type="submit" disabled={!ready || sending}>
          {t("create.submit")}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel} disabled={sending}>
          {t("create.cancel")}
        </Button>
      </div>
    </form>
  );
}

/**
 * Un interruptor de permiso. `role="switch"` y no una casilla porque lo que
 * hace no es marcar una opción de un conjunto: enciende una capacidad, y el
 * lector de pantalla tiene que decir «activado / desactivado».
 */
export function PermissionSwitch({
  label,
  hint,
  checked,
  onToggle,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="flex min-w-0 items-start gap-3">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={onToggle}
        className="mt-1 inline-flex h-6 w-11 shrink-0 items-center rounded-full border border-border bg-muted p-1 transition-colors aria-[checked=true]:bg-primary"
      >
        <span
          className={`size-4 rounded-full bg-background transition-transform ${checked ? "translate-x-5" : "translate-x-0"}`}
        />
      </button>
      <span className="flex min-w-0 flex-col">
        <span className="text-sm">{label}</span>
        <span className="text-xs text-pretty text-muted-foreground">{hint}</span>
      </span>
    </div>
  );
}
