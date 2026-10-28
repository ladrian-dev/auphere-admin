"use client";

import { Archive, ArchiveRestore, MapPin, Pencil, Plus } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Button, Field, Input, StatusBadge } from "@nexus/ui";

import { archiveLocationAction, createLocationAction, updateLocationAction } from "@/app/(console)/clients/[ref]/business/actions";
import { useT } from "@/i18n/client";
import type { Location, LocationBody, Locations } from "@/lib/backend/business-sections";

import { ConflictNotice, SectionFrame, problemOf, type Result } from "./section-frame";

type Act<B> = (body: B) => Promise<Result<Locations>>;
export type LocationsActions = {
  create: Act<{ ref: string; revision: number; body: LocationBody }>;
  update: Act<{ ref: string; revision: number; id: string; body: LocationBody }>;
  archive: Act<{ ref: string; revision: number; id: string; restore: boolean }>;
};

const SERVER_ACTIONS: LocationsActions = {
  create: (b) => createLocationAction(b),
  update: (b) => updateLocationAction(b),
  archive: (b) => archiveLocationAction(b),
};

/**
 * «Sedes» de Negocio (spec 047, T060; requisito 9): nombre, dirección,
 * teléfono y si tiene horario propio (se edita en «Horario», eligiendo la sede).
 * Archivar se deshace con «Restaurar». Sin sedes, se dice lo que hará el agente.
 */
export function LocationsSection({
  refId,
  locations: initial,
  canWrite,
  actions = SERVER_ACTIONS,
  onChange,
  confirmable = false,
}: {
  refId: string;
  locations: Locations;
  canWrite: boolean;
  actions?: LocationsActions;
  onChange?: (next: Locations) => void;
  /** «Es correcto» de lo leído de la web: solo en la consola del partner. */
  confirmable?: boolean;
}) {
  const t = useT();
  const [locations, setLocations] = React.useState(initial);
  const [editing, setEditing] = React.useState<Location | "new" | null>(null);
  const [showArchived, setShowArchived] = React.useState(false);
  const [conflict, setConflict] = React.useState(false);
  const [pending, startTransition] = React.useTransition();
  const live = locations.items.filter((l) => !l.archived);
  const shown = showArchived ? locations.items : live;

  async function apply(res: Result<Locations>): Promise<string | null> {
    if (res.ok) {
      setLocations(res.data);
      onChange?.(res.data);
      setConflict(false);
      toast.success(t("business.section.saved"));
      return null;
    }
    const code = problemOf(res);
    if (code === "conflict") setConflict(true);
    return code;
  }

  return (
    <SectionFrame
      id="business-locations"
      title={t("business.locations.title")}
      state={locations.state}
      canWrite={canWrite}
      confirm={confirmable ? { refId, section: "locations", onConfirmed: () => setLocations((prev) => ({ ...prev, state: "complete" })) } : undefined}
      action={
        editing === null ? (
          <Button type="button" size="sm" variant="outline" onClick={() => setEditing("new")}>
            <Plus aria-hidden="true" />
            {t("business.locations.add")}
          </Button>
        ) : null
      }
    >
      <div className="grid min-w-0 gap-4">
        {conflict ? <ConflictNotice /> : null}
        {live.length === 0 && !showArchived ? <p className="text-sm text-pretty text-muted-foreground">{t("business.locations.empty.read")}</p> : null}
        {shown.length ? (
          // Como el prototipo: una lista con su baldosa, nombre y dirección.
          <ul className="grid min-w-0 divide-y divide-border">
            {shown.map((l) => (
              <li key={l.id} className="group flex min-w-0 items-start gap-3 py-3 first:pt-0 last:pb-0">
                <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground">
                  <MapPin className="size-4" />
                </span>
                <div className="grid min-w-0 flex-1 basis-56 gap-1">
                  <p className="flex min-w-0 flex-wrap items-center gap-2 font-medium">
                    <span className="min-w-0 break-words">{l.name}</span>
                    {l.archived ? <StatusBadge tone="muted">{t("business.locations.archived")}</StatusBadge> : null}
                  </p>
                  {l.address || l.phone_e164 ? (
                    <p className="text-xs text-pretty break-words text-muted-foreground">
                      {[l.address, l.phone_e164].filter(Boolean).join(" · ")}
                    </p>
                  ) : null}
                  <p className="text-xs text-pretty text-muted-foreground">
                    {l.own_hours ? `${t("business.locations.own_hours")}: ${l.label ?? ""}` : t("business.locations.inherits")}
                  </p>
                </div>
                {canWrite ? (
                  <div className="flex shrink-0 gap-1 opacity-60 transition-opacity duration-(--duration-hover) group-focus-within:opacity-100 group-hover:opacity-100">
                    {!l.archived ? (
                      <Button variant="ghost" size="icon" aria-label={`${t("business.section.edit")} ${l.name}`} onClick={() => setEditing(l)}>
                        <Pencil aria-hidden="true" />
                      </Button>
                    ) : null}
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={pending}
                      aria-label={t(l.archived ? "business.locations.restore" : "business.locations.archive", { name: l.name })}
                      onClick={() =>
                        startTransition(async () => {
                          await apply(await actions.archive({ ref: refId, revision: locations.revision, id: l.id, restore: l.archived }));
                        })
                      }
                    >
                      {l.archived ? <ArchiveRestore aria-hidden="true" /> : <Archive aria-hidden="true" />}
                    </Button>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
        {locations.items.some((l) => l.archived) ? (
          <label className="flex min-h-6 items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-primary" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
            {t("business.locations.show_archived")}
          </label>
        ) : null}
        {editing !== null ? (
          <LocationForm
            location={editing === "new" ? null : editing}
            onCancel={() => setEditing(null)}
            onSave={async (body) => {
              const res =
                editing === "new"
                  ? await actions.create({ ref: refId, revision: locations.revision, body })
                  : await actions.update({ ref: refId, revision: locations.revision, id: editing.id, body });
              const problem = await apply(res);
              if (problem === null || problem === "conflict") setEditing(null);
              return problem;
            }}
          />
        ) : null}
      </div>
    </SectionFrame>
  );
}

function LocationForm({
  location,
  onCancel,
  onSave,
}: {
  location: Location | null;
  onCancel: () => void;
  onSave: (body: LocationBody) => Promise<string | null>;
}) {
  const t = useT();
  const [name, setName] = React.useState(location?.name ?? "");
  const [address, setAddress] = React.useState(location?.address ?? "");
  const [phone, setPhone] = React.useState(location?.phone_e164 ?? "");
  const [error, setError] = React.useState<string | null>(null);
  const [pending, startTransition] = React.useTransition();

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return setError("name_required");
    if (phone.trim() && !/^\+[1-9]\d{6,14}$/.test(phone.replace(/\s/g, ""))) return setError("phone_invalid");
    startTransition(async () => {
      const problem = await onSave({ name: name.trim(), address: address.trim() || null, phone_e164: phone.replace(/\s/g, "") || null });
      if (problem && problem !== "conflict") setError(problem === "phone_invalid" || problem === "name_required" ? problem : "generic");
    });
  }

  return (
    <form onSubmit={submit} className="grid min-w-0 gap-3 rounded-md border border-border p-3" noValidate>
      <div className="grid min-w-0 gap-3 sm:grid-cols-3">
        <Field label={t("business.locations.name")} required error={error === "name_required" ? t("business.locations.error.name_required") : undefined}>
          {(a11y) => <Input {...a11y} value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />}
        </Field>
        <Field label={t("business.locations.address")}>
          {(a11y) => <Input {...a11y} value={address} maxLength={300} onChange={(e) => setAddress(e.target.value)} />}
        </Field>
        <Field
          label={t("business.locations.phone")}
          hint={t("business.locations.phone.hint")}
          error={error === "phone_invalid" ? t("business.locations.error.phone_invalid") : undefined}
        >
          {(a11y) => <Input {...a11y} type="tel" inputMode="tel" value={phone} maxLength={20} onChange={(e) => setPhone(e.target.value)} />}
        </Field>
      </div>
      {error === "generic" ? (
        <p role="alert" className="text-sm text-destructive">
          {t("business.section.error.generic")}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button type="submit" disabled={pending}>
          {t("business.locations.save")}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel}>
          {t("business.section.cancel")}
        </Button>
      </div>
    </form>
  );
}
