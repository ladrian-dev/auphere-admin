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

import {
  Badge,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Input,
  Label,
  Separator,
  Skeleton,
  Textarea,
} from "@nexus/ui";
import type { WhatsAppTemplate } from "@/lib/backend";

import {
  isSpanishTemplate,
  OTP_BUTTON_MAX,
  OTP_DEFAULT_BUTTON,
  otpIssues,
  otpPayload,
  otpPreview,
} from "./otp-template";
import {
  createWhatsAppTemplateAction,
  deleteWhatsAppTemplateAction,
  listWhatsAppTemplatesAction,
} from "./setup-actions";

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
  const [creating, setCreating] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  // Create-form state.
  const [name, setName] = useState("");
  const [language, setLanguage] = useState("es");
  const [category, setCategory] = useState("UTILITY");
  const [bodyText, setBodyText] = useState("");
  // Spec 077 (3.1): an authentication template is Meta's fixed text; only these are chosen.
  const [otpButton, setOtpButton] = useState(OTP_DEFAULT_BUTTON);
  const [otpMinutes, setOtpMinutes] = useState("10");
  const [otpSecurity, setOtpSecurity] = useState(true);
  const isAuth = category === "AUTHENTICATION";
  const otpDraft = { buttonText: otpButton, minutes: otpMinutes, security: otpSecurity };
  const otpProblems = otpIssues(otpDraft);
  const preview = otpPreview(otpDraft);

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
    if (isAuth) {
      const problem = otpProblems.button ?? otpProblems.minutes;
      if (problem) {
        toast.error("Revisa la plantilla de código", { description: problem });
        return;
      }
    } else if (!bodyText.trim()) {
      toast.error("Falta el texto del mensaje");
      return;
    }
    setCreating(true);
    // Spec 077: AUTHENTICATION goes as `otp`, never as free text (Meta refuses it).
    const res = await createWhatsAppTemplateAction(
      tenantId,
      isAuth
        ? { name: cleanName, language, category: "AUTHENTICATION", otp: otpPayload(otpDraft) }
        : {
            name: cleanName,
            language,
            category,
            components: [{ type: "BODY", text: bodyText.trim() }],
          },
    );
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
            <LayoutTemplate className="h-4 w-4" strokeWidth={1.75} />
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
            <RefreshCw className="mr-2 size-4" />
            Actualizar
          </Button>
          <Button
            variant={showForm ? "secondary" : "default"}
            size="sm"
            onClick={() => setShowForm((v) => !v)}
          >
            <Plus className="mr-2 size-4" />
            Nueva plantilla
          </Button>
        </div>

        {showForm ? (
          <form
            onSubmit={onCreate}
            className="grid gap-3 rounded-md border border-border bg-card p-4"
          >
            <div className="grid gap-3 md:grid-cols-3">
              <div className="grid gap-2">
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
              <div className="grid gap-2">
                <Label htmlFor="tpl-lang">Idioma</Label>
                <Input
                  id="tpl-lang"
                  value={language}
                  onChange={(e) => setLanguage(e.target.value)}
                  placeholder="es"
                  className="font-mono"
                />
              </div>
              <div className="grid gap-2">
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
            {isAuth ? (
              <div className="grid gap-3 md:grid-cols-2">
                <fieldset className="grid content-start gap-3">
                  <legend className="mb-1 text-xs text-muted-foreground">
                    Autenticación: Meta fija el texto. Solo se eligen estos campos.
                  </legend>
                  <div className="grid gap-2">
                    <div className="grid gap-2">
                      <Label htmlFor="tpl-otp-button">Texto del botón</Label>
                      <Input
                        id="tpl-otp-button"
                        value={otpButton}
                        maxLength={OTP_BUTTON_MAX}
                        onChange={(e) => setOtpButton(e.target.value)}
                        aria-invalid={otpProblems.button ? true : undefined}
                        aria-describedby="tpl-otp-button-help"
                      />
                      <p
                        id="tpl-otp-button-help"
                        className={otpProblems.button ? "text-xs text-destructive" : "text-xs text-muted-foreground"}
                      >
                        {otpProblems.button ?? `Hasta ${OTP_BUTTON_MAX} caracteres.`}
                      </p>
                    </div>
                    <div className="grid gap-2">
                      <Label htmlFor="tpl-otp-minutes">Caduca en (min)</Label>
                      <Input
                        id="tpl-otp-minutes"
                        type="number"
                        inputMode="numeric"
                        min={1}
                        max={90}
                        step={1}
                        value={otpMinutes}
                        onChange={(e) => setOtpMinutes(e.target.value)}
                        aria-invalid={otpProblems.minutes ? true : undefined}
                        aria-describedby="tpl-otp-minutes-help"
                        className="tabular-nums"
                      />
                      <p
                        id="tpl-otp-minutes-help"
                        className={otpProblems.minutes ? "text-xs text-destructive" : "text-xs text-muted-foreground"}
                      >
                        {otpProblems.minutes ?? "De 1 a 90. Vacío: no dice cuándo caduca."}
                      </p>
                    </div>
                  </div>
                  <label htmlFor="tpl-otp-security" className="flex min-h-6 items-center gap-2 text-sm">
                    <input
                      id="tpl-otp-security"
                      type="checkbox"
                      checked={otpSecurity}
                      onChange={(e) => setOtpSecurity(e.target.checked)}
                      className="size-4 shrink-0 accent-primary"
                    />
                    Aviso de seguridad
                  </label>
                </fieldset>
                {isSpanishTemplate(language) ? (
                  <figure className="grid min-w-0 content-start gap-2">
                    <figcaption className="text-xs text-muted-foreground">Vista previa en español</figcaption>
                    <div lang="es" className="flex flex-col gap-1 rounded-md bg-muted p-3" data-slot="otp-preview">
                      <div className="rounded-md bg-background px-3 py-2 text-sm shadow-sm ring-1 ring-foreground/5">
                        <p className="text-pretty break-words">
                          <strong>{preview.body.split(" ")[0]}</strong>
                          {preview.body.slice(preview.body.indexOf(" "))}
                        </p>
                        {preview.footer ? (
                          <p className="mt-1 text-xs text-muted-foreground">{preview.footer}</p>
                        ) : null}
                      </div>
                      <div className="rounded-md bg-background px-3 py-2 text-center text-sm font-medium text-primary-deep shadow-sm ring-1 ring-foreground/5">
                        {preview.button}
                      </div>
                    </div>
                  </figure>
                ) : (
                  <p className="text-xs text-pretty text-muted-foreground" data-slot="otp-preview-other">
                    Meta pone el texto fijo en el idioma de la plantilla
                    {language.trim() ? <> (<code className="font-mono">{language.trim()}</code>)</> : null}; aquí
                    solo se previsualiza en español.
                  </p>
                )}
              </div>
            ) : (
            <div className="grid gap-2">
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
            )}
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
                    <Trash2 className="size-4 text-muted-foreground" />
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
