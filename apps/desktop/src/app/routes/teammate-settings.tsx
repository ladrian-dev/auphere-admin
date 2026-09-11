/**
 * Cambiar y archivar un teammate — spec 003, Requisitos 2.3, 2.4 y 2.6.
 *
 * El roster es del **partner**: lo que aquí se toca lo ven todos, y por eso el
 * guardado manda solo los campos que cambiaron. Un parche completo pisaría en
 * silencio lo que otra persona cambió mientras esta pantalla estaba abierta.
 *
 * Archivar es la única acción sin vuelta atrás desde aquí, así que se pide
 * confirmación y se dice **antes** lo que pasa: no se borra nada y los hilos
 * siguen legibles. «Borrar» no existe en el producto (R2.6) y la base lo revoca.
 */
import { Button, Input, Label } from "@nexus/ui";
import * as React from "react";

import type { Teammate } from "../bridge";
import { useAppT } from "../i18n";
import {
  type ModelChoice,
  PERMISSION_ORDER,
  PermissionSwitch,
  type SubmitResult,
  type TeammatePermissions,
  NAME_MAX,
  isKnownError,
} from "./new-teammate";

export type TeammatePatch = {
  name?: string;
  job?: string;
  model?: string;
  permissions?: TeammatePermissions;
  local_exec?: boolean;
};

export type TeammateSettingsProps = {
  teammate: Teammate;
  jobs: string[];
  models: ModelChoice[];
  onSave: (patch: TeammatePatch) => Promise<SubmitResult>;
  onArchive: () => Promise<SubmitResult>;
  onClose: () => void;
};

export function TeammateSettings({
  teammate,
  jobs,
  models,
  onSave,
  onArchive,
  onClose,
}: TeammateSettingsProps) {
  const t = useAppT();
  const [name, setName] = React.useState(teammate.name);
  const [job, setJob] = React.useState(teammate.job);
  const [model, setModel] = React.useState(teammate.model);
  const [permissions, setPermissions] = React.useState<TeammatePermissions>(teammate.permissions);
  const [localExec, setLocalExec] = React.useState(teammate.local_exec);
  const [sending, setSending] = React.useState(false);
  const [failed, setFailed] = React.useState<string | null>(null);
  const [confirming, setConfirming] = React.useState(false);

  // Un archivado se lee, no se cambia: ofrecer los campos sugeriría que puede
  // volver, y volver no es cambiar sino crear otro.
  if (teammate.status === "archived") {
    return (
      <div className="flex flex-col items-start gap-3 p-6" role="status">
        <h2 className="text-base font-semibold text-balance">{teammate.name}</h2>
        <p className="max-w-prose text-sm text-pretty text-muted-foreground">
          {t("settings.archived")}
        </p>
        <Button variant="outline" size="sm" onClick={onClose}>
          {t("settings.close")}
        </Button>
      </div>
    );
  }

  const samePermissions =
    PERMISSION_ORDER.every((k) => permissions[k] === teammate.permissions[k]) &&
    localExec === teammate.local_exec;

  const patch: TeammatePatch = {
    ...(name.trim() !== teammate.name ? { name: name.trim() } : {}),
    ...(job.trim() !== teammate.job ? { job: job.trim() } : {}),
    ...(model !== teammate.model ? { model } : {}),
    ...(samePermissions ? {} : { permissions, local_exec: localExec }),
  };
  // `local_exec` viaja con los permisos: en la pantalla es un interruptor más
  // de la misma pregunta («qué le dejas hacer»), y separarlos haría que un
  // cambio se guardase a medias.
  if (patch.permissions && localExec === teammate.local_exec) delete patch.local_exec;
  const dirty = Object.keys(patch).length > 0;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!dirty || sending) return;
    setSending(true);
    setFailed(null);
    const result = await onSave(patch);
    setSending(false);
    if (!result.ok) setFailed(result.error);
  };

  const archive = async () => {
    setSending(true);
    setFailed(null);
    const result = await onArchive();
    setSending(false);
    setConfirming(false);
    if (result.ok) onClose();
    else setFailed(result.error);
  };

  return (
    <form className="flex min-w-0 flex-col gap-5 p-6" onSubmit={(e) => void submit(e)} noValidate>
      <h2 className="text-base font-semibold text-balance">{t("settings.title")}</h2>

      <div className="flex min-w-0 flex-col gap-1.5">
        <Label htmlFor="settings-name">{t("create.name")}</Label>
        <Input
          id="settings-name"
          value={name}
          maxLength={NAME_MAX}
          autoComplete="off"
          onChange={(e) => setName(e.target.value.slice(0, NAME_MAX))}
        />
      </div>

      <div className="flex min-w-0 flex-col gap-1.5">
        <Label htmlFor="settings-job">{t("create.job")}</Label>
        <Input
          id="settings-job"
          list="settings-jobs"
          value={job}
          maxLength={NAME_MAX}
          autoComplete="off"
          onChange={(e) => setJob(e.target.value.slice(0, NAME_MAX))}
        />
        <datalist id="settings-jobs">
          {jobs.map((seed) => (
            <option key={seed} value={seed}>
              {seed}
            </option>
          ))}
        </datalist>
        <p className="text-xs text-pretty text-muted-foreground">{t("settings.jobHint")}</p>
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
              name="settings-model"
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
          {t(isKnownError(failed) ? `create.failed.${failed}` : "settings.failed.unknown")}
        </p>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={!dirty || sending}>
          {t("settings.save")}
        </Button>
        <Button type="button" variant="outline" onClick={onClose} disabled={sending}>
          {t("settings.close")}
        </Button>
        <Button
          type="button"
          variant="outline"
          className="ml-auto"
          onClick={() => setConfirming(true)}
          disabled={sending}
        >
          {t("settings.archive")}
        </Button>
      </div>

      {confirming ? (
        <div
          role="alertdialog"
          aria-label={t("settings.archive")}
          className="flex flex-col gap-3 rounded-md border border-border bg-muted p-4"
        >
          <p className="max-w-prose text-sm text-pretty">
            {t("settings.archive.confirm", { name: teammate.name })}
          </p>
          <div className="flex gap-2">
            <Button type="button" onClick={() => void archive()} disabled={sending}>
              {t("settings.archive.yes")}
            </Button>
            <Button type="button" variant="outline" onClick={() => setConfirming(false)}>
              {t("settings.archive.no")}
            </Button>
          </div>
        </div>
      ) : null}
    </form>
  );
}
