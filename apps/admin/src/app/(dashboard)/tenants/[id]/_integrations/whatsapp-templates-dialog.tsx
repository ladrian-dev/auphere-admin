"use client";

/**
 * "Plantillas" dialog for the connected Meta WhatsApp channel.
 *
 * Lists the WABA's message templates straight from the Cloud API
 * (estado de aprobación incluido), lets the operator submit a new
 * template for review, edit one (spec 075) and delete existing ones. Las
 * plantillas son necesarias para iniciar conversación fuera de la ventana
 * de 24h (recordatorios, alertas, consultas al dueño).
 *
 * Crear y editar usan el mismo editor que la consola (`TemplateEditor`, de
 * `@nexus/ui`), también para las de autenticación y para los clientes de
 * solo envío (spec 075, requisito 10): no hay otro formulario. Qué se puede
 * editar lo dice la API en cada fila (`edit_blocker`), nunca esta pantalla (9.3).
 */

import { LayoutTemplate, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import {
  Badge,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Separator,
  Skeleton,
  TemplateEditor,
  canEditTemplate,
  draftFromContent,
  languageLabel,
  templateEditFailure,
  type TemplateEditorOutcome,
  type TemplateSubmission,
} from "@nexus/ui";
import type { WhatsAppTemplate, WhatsAppTemplateEditResult } from "@/lib/backend";

import {
  createWhatsAppTemplateAction,
  deleteWhatsAppTemplateAction,
  editWhatsAppTemplateAction,
  listWhatsAppTemplatesAction,
} from "./setup-actions";
import { TEMPLATE_EDITOR_LABELS_ES, blockerSentence, editFailureSentence } from "./template-editor-labels";

const STATUS_TONE: Record<string, string> = {
  APPROVED:
    "border-status-positive-border text-status-positive-text",
  PENDING:
    "border-status-warning-border text-status-warning-text",
  REJECTED:
    "border-status-danger-border text-status-danger-text",
  PAUSED:
    "border-status-warning-border text-status-warning-text",
  DISABLED: "text-muted-foreground",
};

const STATUS_LABEL: Record<string, string> = {
  APPROVED: "Aprobada",
  PENDING: "En revisión",
  REJECTED: "Rechazada",
  PAUSED: "Pausada",
  DISABLED: "Deshabilitada",
};

function bodyTextOf(tpl: WhatsAppTemplate): string {
  for (const c of tpl.components) {
    const type = String(c.type ?? "").toUpperCase();
    if (type === "BODY" && typeof c.text === "string") return c.text;
  }
  return "";
}

export function WhatsAppTemplatesDialog({ tenantId }: { tenantId: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [templates, setTemplates] = useState<WhatsAppTemplate[]>([]);
  // A fresh editor each time «Nueva plantilla» opens it: the next one starts empty.
  const [creating, setCreating] = useState<{ key: number; open: boolean }>({ key: 0, open: false });
  const [deleting, setDeleting] = useState<string | null>(null);
  // Spec 075: the template being edited, as it was when the editor opened —
  // its fingerprint is what the save sends. «Recargar» starts again from a fresh one.
  const [editing, setEditing] = useState<{ key: number; tpl: WhatsAppTemplate; open: boolean } | null>(null);

  const refresh = useCallback(async (): Promise<WhatsAppTemplate[] | null> => {
    setLoading(true);
    setLoadError(null);
    const res = await listWhatsAppTemplatesAction(tenantId);
    setLoading(false);
    if (!res.ok) {
      setLoadError(res.error);
      return null;
    }
    setTemplates(res.data.templates);
    return res.data.templates;
  }, [tenantId]);

  function openEditor(tpl: WhatsAppTemplate) {
    setEditing((e) => ({ key: (e?.key ?? 0) + 1, tpl, open: true }));
  }

  function closeEditor() {
    setEditing((e) => (e ? { ...e, open: false } : e));
  }

  function onEdited(result: WhatsAppTemplateEditResult) {
    const status = (result.status ?? "").toUpperCase();
    toast.success(
      result.changed
        ? `Cambios enviados a Meta. Estado: ${STATUS_LABEL[status] ?? result.status ?? "desconocido"}.`
        : "No había cambios: no se ha mandado nada a Meta.",
    );
    closeEditor();
    void refresh();
  }

  /**
   * After a conflict: the list again, and the editor from the template as it is now.
   * What went wrong comes back to the editor, which is in front of the list.
   */
  async function reloadEditing(): Promise<string | null> {
    const current = editing?.tpl;
    if (!current) return null;
    const res = await listWhatsAppTemplatesAction(tenantId);
    if (!res.ok) return `No se pudo recargar la plantilla: ${res.error}`;
    setTemplates(res.data.templates);
    const again = res.data.templates.find((t) => t.name === current.name && t.language === current.language);
    if (!again) toast.error("Esta plantilla ya no existe en ese idioma.");
    setEditing((e) =>
      again && canEditTemplate(again) ? { key: (e?.key ?? 0) + 1, tpl: again, open: true } : e ? { ...e, open: false } : e,
    );
    return null;
  }

  function onCreated(tplName: string) {
    toast.success(`Plantilla ${tplName} enviada a revisión`, {
      description: "Meta la revisa (minutos a horas). El estado se actualiza solo.",
    });
    setCreating((c) => ({ ...c, open: false }));
    void refresh();
  }

  async function onDelete(tplName: string) {
    setDeleting(tplName);
    const res = await deleteWhatsAppTemplateAction(tenantId, tplName);
    setDeleting(null);
    if (!res.ok) {
      toast.error("No se pudo borrar", { description: res.error });
      return;
    }
    toast.success(`Plantilla ${tplName} borrada`);
    void refresh();
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) void refresh();
      }}
    >
      <DialogTrigger
        render={
          <Button variant="outline" size="sm">
            <LayoutTemplate className="h-4 w-4" strokeWidth={1.75} />
            Plantillas
          </Button>
        }
      />
      {/* sm: — without it the primitive's sm:max-w-sm wins and the list is 384 px wide on a desktop. */}
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Plantillas de WhatsApp</DialogTitle>
          <DialogDescription>
            Mensajes pre-aprobados por Meta. Son obligatorios para escribirle
            a un cliente fuera de la ventana de 24 horas (recordatorios,
            avisos). El texto admite variables con{" "}
            <code className="font-mono text-xs">{"{{nombre}}"}</code>.
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void refresh()}
            disabled={loading}
          >
            <RefreshCw className="mr-2 size-4" />
            Actualizar
          </Button>
          <Button size="sm" onClick={() => setCreating((c) => ({ key: c.key + 1, open: true }))}>
            <Plus className="mr-2 size-4" />
            Nueva plantilla
          </Button>
        </div>

        <Separator />

        {loading ? (
          <div className="grid gap-2">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : loadError ? (
          <div className="rounded-md border border-status-danger-border p-4 text-sm">
            <p className="font-medium">No se pudieron cargar las plantillas</p>
            <p className="mt-1 text-muted-foreground">{loadError}</p>
            <Button
              variant="outline"
              size="sm"
              className="mt-3"
              onClick={() => void refresh()}
            >
              Reintentar
            </Button>
          </div>
        ) : templates.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">
            Este número todavía no tiene plantillas. Creá la primera con
            «Nueva plantilla» — sin una plantilla aprobada el agente no puede
            iniciar conversaciones (solo responder).
          </p>
        ) : (
          // One column as wide as the dialog: an `auto` track grows to the
          // whole `truncate` line and pushes «Editar» and «Borrar» out of view.
          <ul className="grid max-h-80 grid-cols-1 gap-2 overflow-y-auto pr-1">
            {templates.map((tpl) => {
              const status = (tpl.status ?? "").toUpperCase();
              return (
                <li
                  key={`${tpl.name}:${tpl.language}`}
                  className="flex min-w-0 items-start justify-between gap-3 rounded-md border border-border p-3"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="min-w-0 font-mono text-sm break-all">{tpl.name}</span>
                      <Badge variant="outline" className="font-mono text-[10px]">
                        {tpl.language}
                      </Badge>
                      {tpl.category ? (
                        <Badge variant="outline" className="text-[10px]">
                          {tpl.category}
                        </Badge>
                      ) : null}
                      <Badge
                        variant="outline"
                        className={`text-[10px] ${STATUS_TONE[status] ?? ""}`}
                      >
                        {STATUS_LABEL[status] ?? tpl.status ?? "—"}
                      </Badge>
                    </div>
                    {bodyTextOf(tpl) ? (
                      <p className="mt-1 truncate text-xs text-muted-foreground">
                        {bodyTextOf(tpl)}
                      </p>
                    ) : null}
                    {tpl.edit_blocker ? (
                      // 3.2 · One line: which part keeps it out, and where it is edited.
                      <p className="mt-1 text-xs text-pretty text-muted-foreground" data-slot="edit-blocker">
                        {blockerSentence(tpl.edit_blocker)}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {canEditTemplate(tpl) ? (
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Editar plantilla ${tpl.name} (${languageLabel(tpl.language)})`}
                        onClick={() => openEditor(tpl)}
                      >
                        <Pencil className="size-4 text-muted-foreground" />
                      </Button>
                    ) : null}
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Borrar plantilla ${tpl.name}`}
                      disabled={deleting === tpl.name}
                      onClick={() => void onDelete(tpl.name)}
                    >
                      <Trash2 className="size-4 text-muted-foreground" />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        <CreateTemplateDialog
          key={creating.key}
          tenantId={tenantId}
          open={creating.open}
          onClose={() => setCreating((c) => ({ ...c, open: false }))}
          onCreated={onCreated}
        />
        {editing ? (
          <EditTemplateDialog
            key={editing.key}
            tenantId={tenantId}
            tpl={editing.tpl}
            open={editing.open}
            onClose={closeEditor}
            onSaved={onEdited}
            onReload={reloadEditing}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}

/**
 * Spec 075 (10.5, 10.6): create a template with the console's editor, every
 * category included, for any client (also a send-only one). The editor hands
 * over the console's shape and the API builds what goes to Meta (9.3).
 */
function CreateTemplateDialog({
  tenantId,
  open,
  onClose,
  onCreated,
}: {
  tenantId: string;
  open: boolean;
  onClose: () => void;
  onCreated: (name: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(draft: TemplateSubmission): Promise<TemplateEditorOutcome> {
    setError(null);
    setBusy(true);
    try {
      const res = await createWhatsAppTemplateAction(tenantId, draft);
      if (!res.ok) {
        // What Meta or the API said, where the operator is looking; what was written stays.
        setError(res.error);
        return { kind: "failed" };
      }
      onCreated(res.data.name);
      return { kind: "done" };
    } catch {
      setError(editFailureSentence({ kind: "unknown" }));
      return { kind: "failed" };
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && !next && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>Nueva plantilla</DialogTitle>
          <DialogDescription>
            Meta la revisa antes de que se pueda mandar, normalmente en minutos. El nombre y el idioma no se pueden
            cambiar después.
          </DialogDescription>
        </DialogHeader>
        <TemplateEditor
          mode="create"
          labels={TEMPLATE_EDITOR_LABELS_ES}
          pending={busy}
          serverError={error}
          onSubmit={create}
          onCancel={onClose}
        />
      </DialogContent>
    </Dialog>
  );
}

/**
 * Spec 075 (9.1, 9.2): edit one language of a template, with the console's
 * editor. It starts from what the API split (`draft`) and saves with the
 * fingerprint the list gave (`version`): a change made meanwhile is never
 * overwritten (7.1).
 */
function EditTemplateDialog({
  tenantId,
  tpl,
  open,
  onClose,
  onSaved,
  onReload,
}: {
  tenantId: string;
  tpl: WhatsAppTemplate;
  open: boolean;
  onClose: () => void;
  onSaved: (result: WhatsAppTemplateEditResult) => void;
  /** The list again; on success the caller reopens the editor, on failure it says why. */
  onReload: () => Promise<string | null>;
}) {
  const [busy, setBusy] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [error, setError] = useState<{ text: string; reload: boolean } | null>(null);

  async function reload() {
    setReloading(true);
    try {
      const problem = await onReload();
      if (problem) setError({ text: problem, reload: true });
    } catch {
      setError({ text: "No se pudo recargar la plantilla. Inténtalo de nuevo en un momento.", reload: true });
    } finally {
      setReloading(false);
    }
  }
  const locked = (tpl.status ?? "").toUpperCase() === "APPROVED";
  const initial = tpl.draft ? draftFromContent(tpl.name, tpl.language, tpl.draft) : null;

  async function save(draft: TemplateSubmission, { confirm }: { confirm: boolean }): Promise<TemplateEditorOutcome> {
    // The editor does not offer Authentication when editing (1.4, 3.2): nothing to send.
    if (draft.category === "AUTHENTICATION") return { kind: "failed" };
    setError(null);
    setBusy(true);
    try {
      // The name and the language are the template's, in the path: never in the body.
      const res = await editWhatsAppTemplateAction(tenantId, tpl.name, tpl.language, {
        version: tpl.version ?? "",
        confirm,
        ...(locked ? {} : { category: draft.category }),
        header_text: draft.header_text,
        body_text: draft.body_text,
        footer_text: draft.footer_text,
        buttons: draft.buttons,
        examples: draft.examples,
      });
      if (res.ok) {
        onSaved(res.data);
        return { kind: "done" };
      }
      const failure = templateEditFailure(res.code, res.info);
      if (failure.kind === "confirmation_required") return failure;
      setError({
        // "invalid": the action refused it before the API, and says so itself.
        text: res.code === "invalid" ? res.error : editFailureSentence(failure),
        reload: failure.kind === "template_changed" || failure.kind === "not_editable" || failure.kind === "template_not_found",
      });
      return failure.kind === "system_variables" ? failure : { kind: "failed" };
    } catch {
      // The action itself failed (network): what was written stays.
      setError({ text: editFailureSentence({ kind: "unknown" }), reload: false });
      return { kind: "failed" };
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !busy && !next && onClose()}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>Editar plantilla</DialogTitle>
          <DialogDescription>
            Meta vuelve a revisar la plantilla con el mismo nombre. El nombre y el idioma no cambian. El resto se
            manda entero, también lo que no toques.
          </DialogDescription>
        </DialogHeader>
        {tpl.rejection_reason ? (
          // 1.2 · What Meta said, in sight while editing.
          <div className="grid min-w-0 gap-1 rounded-md border border-status-danger-border p-3 text-sm" data-slot="rejection">
            <p className="font-medium">Motivo de Meta</p>
            <p className="font-mono text-xs break-words">{tpl.rejection_reason}</p>
          </div>
        ) : null}
        <TemplateEditor
          mode="edit"
          initial={initial}
          categoryLocked={locked}
          systemVariables={tpl.system_variables ?? null}
          labels={TEMPLATE_EDITOR_LABELS_ES}
          pending={busy}
          serverError={error?.text}
          serverErrorAction={
            error?.reload ? (
              <Button type="button" variant="outline" size="sm" onClick={() => void reload()} loading={reloading}>
                Recargar
              </Button>
            ) : undefined
          }
          onSubmit={save}
          onCancel={onClose}
        />
      </DialogContent>
    </Dialog>
  );
}
