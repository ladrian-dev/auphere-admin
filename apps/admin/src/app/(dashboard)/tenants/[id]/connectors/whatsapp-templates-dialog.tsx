"use client";

/**
 * "Plantillas" dialog for the connected Meta WhatsApp channel.
 *
 * Lists the WABA's message templates straight from the Cloud API
 * (estado de aprobación incluido), lets the operator submit a new
 * template for review and delete existing ones. Las plantillas son
 * necesarias para iniciar conversación fuera de la ventana de 24h
 * (recordatorios, alertas, consultas al dueño).
 */

import { LayoutTemplate, Plus, RefreshCw, Trash2 } from "lucide-react";
import { useCallback, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import type { WhatsAppTemplate } from "@/lib/backend";

import {
  createWhatsAppTemplateAction,
  deleteWhatsAppTemplateAction,
  listWhatsAppTemplatesAction,
} from "./setup-actions";

const STATUS_TONE: Record<string, string> = {
  APPROVED:
    "border-[color:var(--color-status-positive)]/30 text-[color:var(--color-status-positive)]",
  PENDING:
    "border-[color:var(--color-status-warning)]/30 text-[color:var(--color-status-warning)]",
  REJECTED:
    "border-[color:var(--color-status-danger)]/30 text-[color:var(--color-status-danger)]",
  PAUSED:
    "border-[color:var(--color-status-warning)]/30 text-[color:var(--color-status-warning)]",
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
  const [creating, setCreating] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Create-form state.
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("es");
  const [category, setCategory] = useState("UTILITY");
  const [bodyText, setBodyText] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    const res = await listWhatsAppTemplatesAction(tenantId);
    setLoading(false);
    if (!res.ok) {
      setLoadError(res.error);
      return;
    }
    setTemplates(res.data.templates);
  }, [tenantId]);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    const cleanName = name.trim();
    if (!/^[a-z0-9_]+$/.test(cleanName)) {
      toast.error("Nombre inválido", {
        description:
          "Solo minúsculas, números y guiones bajos (ej. recordatorio_24h).",
      });
      return;
    }
    if (!bodyText.trim()) {
      toast.error("Falta el texto del mensaje");
      return;
    }
    setCreating(true);
    const res = await createWhatsAppTemplateAction(tenantId, {
      name: cleanName,
      language,
      category,
      components: [{ type: "BODY", text: bodyText.trim() }],
    });
    setCreating(false);
    if (!res.ok) {
      toast.error("Meta no aceptó la plantilla", { description: res.error });
      return;
    }
    toast.success(`Plantilla ${cleanName} enviada a revisión`, {
      description:
        "Meta la revisa (minutos a horas). El estado se actualiza solo.",
    });
    setShowForm(false);
    setName("");
    setBodyText("");
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
            <LayoutTemplate className="h-3.5 w-3.5" strokeWidth={1.75} />
            Plantillas
          </Button>
        }
      />
      <DialogContent className="max-w-2xl">
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
            <RefreshCw className="mr-1.5 size-3.5" />
            Actualizar
          </Button>
          <Button
            variant={showForm ? "secondary" : "default"}
            size="sm"
            onClick={() => setShowForm((v) => !v)}
          >
            <Plus className="mr-1.5 size-3.5" />
            Nueva plantilla
          </Button>
        </div>

        {showForm ? (
          <form
            onSubmit={onCreate}
            className="grid gap-3 rounded-md border border-border bg-card p-4"
          >
            <div className="grid gap-3 md:grid-cols-3">
              <div className="grid gap-1.5">
                <Label htmlFor="tpl-name">Nombre</Label>
                <Input
                  id="tpl-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="recordatorio_24h"
                  className="font-mono"
                  autoComplete="off"
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="tpl-lang">Idioma</Label>
                <Input
                  id="tpl-lang"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  placeholder="es"
                  className="font-mono"
                />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="tpl-cat">Categoría</Label>
                <select
                  id="tpl-cat"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="h-9 rounded-md border border-input bg-transparent px-3 text-sm"
                >
                  <option value="UTILITY">Utility (avisos, recordatorios)</option>
                  <option value="MARKETING">Marketing</option>
                  <option value="AUTHENTICATION">Autenticación</option>
                </select>
              </div>
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="tpl-body">Texto del mensaje</Label>
              <Textarea
                id="tpl-body"
                value={bodyText}
                onChange={(e) => setBodyText(e.target.value)}
                rows={3}
                placeholder={
                  "Hola {{nombre}}, te recordamos tu cita de mañana a las {{hora}}. Responde CONFIRMAR o CANCELAR."
                }
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setShowForm(false)}
              >
                Cancelar
              </Button>
              <Button type="submit" size="sm" disabled={creating}>
                {creating ? "Enviando a Meta…" : "Enviar a revisión"}
              </Button>
            </div>
          </form>
        ) : null}

        <Separator />

        {loading ? (
          <div className="grid gap-2">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : loadError ? (
          <div className="rounded-md border border-[color:var(--color-status-danger)]/30 p-4 text-sm">
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
          <ul className="grid max-h-80 gap-2 overflow-y-auto pr-1">
            {templates.map((tpl) => {
              const status = (tpl.status ?? "").toUpperCase();
              return (
                <li
                  key={`${tpl.name}:${tpl.language}`}
                  className="flex items-start justify-between gap-3 rounded-md border border-border p-3"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-sm">{tpl.name}</span>
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
                  </div>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label={`Borrar plantilla ${tpl.name}`}
                    disabled={deleting === tpl.name}
                    onClick={() => void onDelete(tpl.name)}
                  >
                    <Trash2 className="size-3.5 text-muted-foreground" />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </DialogContent>
    </Dialog>
  );
}
