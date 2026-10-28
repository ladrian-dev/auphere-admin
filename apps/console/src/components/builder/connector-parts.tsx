"use client";

import * as React from "react";

import {
  Button,
  Checkbox,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Field,
  Input,
  Label,
  NativeSelect,
} from "@nexus/ui";

import { useT } from "@/i18n/client";
import { messages, type MessageKey } from "@/i18n/messages";
import type { Activation, ConnectFormField, ConnectorPermission, ConnectorSettings, SettingsSchema } from "@/lib/backend/agent-connectors-types";
import { CONNECTOR_PERMISSIONS } from "@/lib/backend/agent-connectors-types";

import type { Result } from "./builder-model";
import {
  apiSettingProblems,
  permissionLabel,
  settingFields,
  settingLabel,
  settingProblems,
  settingValues,
  settingsFromValues,
  type SettingField,
  type SettingProblem,
} from "./connector-model";

/**
 * Spec 047 (historia 21; T129) — las piezas que comparten la sección
 * Conectores del agente y la página de cada conexión: el logotipo, el selector
 * del permiso (35.5) y el diálogo de los ajustes declarados en el catálogo
 * (36.2). Los textos son de la consola; la API solo nombra el caso.
 */

/**
 * El logotipo, pedido a nuestro propio origen (`/api/connector-logo`, que lo
 * busca en el catálogo del cliente). Sin logotipo, la inicial.
 */
export function ConnectorLogo({ refId, slug, name, logo }: { refId: string; slug: string; name: string; logo: string | null }) {
  return (
    <span className="flex size-10 shrink-0 items-center justify-center overflow-hidden rounded-md bg-muted ring-1 ring-foreground/10" data-slot="connector-logo">
      {logo ? (
        // Ya viene por nuestra propia ruta: no hay nada que optimizar.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={`/api/connector-logo/${encodeURIComponent(refId)}/${encodeURIComponent(slug)}`} alt="" loading="lazy" className="size-10 object-contain" />
      ) : (
        <span aria-hidden="true" className="text-sm font-medium text-muted-foreground">
          {name.trim().charAt(0).toUpperCase()}
        </span>
      )}
    </span>
  );
}

/** Lo que significa cada permiso, para el texto de ayuda del selector. */
export function permissionHint(t: ReturnType<typeof useT>, p: ConnectorPermission): string {
  return t(`agentConn.permission.hint.${p}` as MessageKey);
}

/**
 * El permiso de un agente con un conector: «Solo leer», «Preguntar antes de
 * escribir» o «Leer y escribir» y, si `allowOff`, «Sin usar en este agente».
 * Es un `<select>` del navegador: teclado, lector de pantalla y móvil de serie.
 */
export function PermissionSelect({
  id,
  label,
  value,
  allowOff,
  disabled,
  busy,
  onChange,
}: {
  id?: string;
  /** El nombre accesible: «Permiso de WooCommerce en este agente». */
  label: string;
  value: ConnectorPermission | null;
  allowOff: boolean;
  disabled?: boolean;
  busy?: boolean;
  onChange: (next: ConnectorPermission | null) => void;
}) {
  const t = useT();
  return (
    <NativeSelect
      id={id}
      size="sm"
      aria-label={label}
      aria-busy={busy || undefined}
      value={value ?? "off"}
      disabled={disabled || busy}
      onChange={(e) => onChange(e.target.value === "off" ? null : (e.target.value as ConnectorPermission))}
      wrapperClassName="w-full sm:w-auto"
      data-slot="connector-permission"
    >
      {allowOff || value === null ? <option value="off">{t("agentConn.permission.off")}</option> : null}
      {CONNECTOR_PERMISSIONS.map((p) => (
        <option key={p} value={p}>
          {permissionLabel(t, p)}
        </option>
      ))}
    </NativeSelect>
  );
}

function problemText(t: ReturnType<typeof useT>, problem: SettingProblem, field: SettingField): string {
  if (problem === "required") return t("agentConn.field.required");
  if (problem === "https") return t("agentConn.settings.https");
  if (problem === "integer" && field.min !== undefined && field.max !== undefined) return t("agentConn.settings.integer", { min: field.min, max: field.max });
  return t("agentConn.settings.invalid");
}

/**
 * Los ajustes de un conector en un agente (36.2): un campo por propiedad del
 * esquema del catálogo, los de un grupo juntos. Se valida aquí lo evidente y la
 * API vuelve a validar con el esquema; lo que marque vuelve a su campo.
 */
export function SettingsDialog({
  open,
  onOpenChange,
  ...form
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
} & Omit<SettingsFormProps, "onClose">) {
  const t = useT();
  const [busy, setBusy] = React.useState(false);
  return (
    <Dialog open={open} onOpenChange={(o) => !busy && onOpenChange(o)}>
      <DialogContent className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("agentConn.settings.title", { name: form.name })}</DialogTitle>
          <DialogDescription>{t("agentConn.settings.body")}</DialogDescription>
        </DialogHeader>
        {/* El formulario nace al abrir: lee lo guardado de ahora. */}
        <SettingsForm {...form} onBusy={setBusy} onClose={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}

type SettingsFormProps = {
  slug: string;
  name: string;
  schema: SettingsSchema | null;
  settings: ConnectorSettings;
  save: (settings: ConnectorSettings) => Promise<Result<Activation>>;
  onSaved: (activation: Activation) => void;
  onClose: () => void;
  onBusy?: (busy: boolean) => void;
};

function SettingsForm({ slug, schema, settings, save, onSaved, onClose, onBusy }: SettingsFormProps) {
  const t = useT();
  const fields = React.useMemo(() => settingFields(schema), [schema]);
  const [values, setValues] = React.useState(() => settingValues(fields, settings));
  const [problems, setProblems] = React.useState<Record<string, SettingProblem>>({});
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusyState] = React.useState(false);
  const formId = React.useId();
  const setBusy = (b: boolean) => {
    setBusyState(b);
    onBusy?.(b);
  };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const found = settingProblems(fields, values);
    setProblems(found);
    setError(null);
    if (Object.keys(found).length) return;
    setBusy(true);
    const res = await save(settingsFromValues(fields, values));
    setBusy(false);
    if (res.ok) {
      onSaved(res.data);
      onClose();
      return;
    }
    if (res.code === "invalid_settings") {
      setProblems(apiSettingProblems(res.info));
      setError(t("agentConn.error.invalid_settings"));
      return;
    }
    setError(
      res.status === 401 || res.status === 403
        ? t("common.forbidden")
        : res.code === "connection_not_authorized" || res.code === "settings_not_supported"
          ? t(`agentConn.error.${res.code}`)
          : t("agentConn.error.unknown"),
    );
  }

  const groups: { group: string | null; fields: SettingField[] }[] = [];
  for (const f of fields) {
    const last = groups[groups.length - 1];
    if (last && last.group === f.group) last.fields.push(f);
    else groups.push({ group: f.group, fields: [f] });
  }

  const control = (f: SettingField) => {
    const id = `${formId}-${f.path.replaceAll(".", "-")}`;
    const label = settingLabel(t, slug, f.path, f.title);
    const problem = problems[f.path];
    if (f.kind === "boolean") {
      return (
        <div key={f.path} className="flex min-w-0 items-center gap-2">
          <Checkbox id={id} checked={values[f.path] === true} onCheckedChange={(c) => setValues((v) => ({ ...v, [f.path]: c === true }))} disabled={busy} />
          <Label htmlFor={id} className="font-normal">
            {label}
          </Label>
        </div>
      );
    }
    return (
      <Field key={f.path} label={label} htmlFor={id} error={problem ? problemText(t, problem, f) : undefined} required={f.required}>
        {(a11y) => (
          <Input
            {...a11y}
            type={f.kind === "url" ? "url" : "text"}
            inputMode={f.kind === "integer" || f.kind === "number" ? "numeric" : f.kind === "url" ? "url" : undefined}
            autoComplete="off"
            spellCheck={false}
            value={String(values[f.path] ?? "")}
            onChange={(e) => setValues((v) => ({ ...v, [f.path]: e.target.value }))}
            disabled={busy}
          />
        )}
      </Field>
    );
  };

  return (
    <form className="grid min-w-0 gap-4" onSubmit={(e) => void submit(e)} noValidate aria-busy={busy}>
      {groups.map((g, i) =>
        g.group ? (
          <fieldset key={g.group} className="grid min-w-0 gap-3 rounded-md border border-border p-3">
            <legend className="px-1 text-sm font-medium">{settingLabel(t, slug, g.group)}</legend>
            {g.fields.map(control)}
          </fieldset>
        ) : (
          <React.Fragment key={`top-${i}`}>{g.fields.map(control)}</React.Fragment>
        ),
      )}
      {error ? (
        <p role="alert" className="text-sm text-destructive text-pretty">
          {error}
        </p>
      ) : null}
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" loading={busy}>
          {t("common.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}

/**
 * Las credenciales que pide un servicio que se conecta con una clave: los
 * campos del catálogo, los secretos como contraseña. Nunca se vuelven a
 * enseñar: se mandan con el alta de siempre (`integrations/actions.ts`).
 */
export function CredentialsForm({
  slug,
  fields,
  busy,
  error,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  slug: string;
  fields: readonly ConnectFormField[];
  busy: boolean;
  error: string | null;
  submitLabel: string;
  onSubmit: (values: Record<string, string>) => void;
  onCancel: () => void;
}) {
  const t = useT();
  const formId = React.useId();
  const [values, setValues] = React.useState<Record<string, string>>({});
  const [missing, setMissing] = React.useState<Record<string, boolean>>({});

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const gaps: Record<string, boolean> = {};
    for (const f of fields) if (f.required !== false && !(values[f.field] ?? "").trim()) gaps[f.field] = true;
    setMissing(gaps);
    if (!Object.keys(gaps).length) onSubmit(values);
  }

  return (
    <form className="grid min-w-0 gap-4" onSubmit={submit} noValidate aria-busy={busy}>
      {fields.map((f) => {
        const id = `${formId}-${f.field}`;
        const key = `connectors.field.${slug}.${f.field}` as MessageKey;
        return (
          <Field key={f.field} label={key in messages ? t(key) : (f.label ?? f.field)} htmlFor={id} required={f.required !== false} error={missing[f.field] ? t("agentConn.field.required") : undefined}>
            {(a11y) => (
              <Input
                {...a11y}
                type={f.secret ? "password" : "text"}
                autoComplete={f.secret ? "new-password" : "off"}
                spellCheck={false}
                placeholder={f.placeholder}
                value={values[f.field] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [f.field]: e.target.value }))}
                disabled={busy}
              />
            )}
          </Field>
        );
      })}
      {error ? (
        <p role="alert" className="text-sm text-destructive text-pretty">
          {error}
        </p>
      ) : null}
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onCancel} disabled={busy}>
          {t("common.cancel")}
        </Button>
        <Button type="submit" loading={busy}>
          {submitLabel}
        </Button>
      </DialogFooter>
    </form>
  );
}
