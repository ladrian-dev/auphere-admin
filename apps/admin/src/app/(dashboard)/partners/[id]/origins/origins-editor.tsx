"use client";

import { useState, useTransition } from "react";
import { Plus, X } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { PartnerApiKeyOut } from "@/lib/backend";

import { updateKeyOriginsAction } from "../../actions";
import { KEY_STATE_LABEL, partnerKeyState } from "../key-state";

/** Mirror de la validación del backend (PUT .../origins): https:// o
 *  http://localhost — nada más. */
function isValidOrigin(origin: string): boolean {
  return (
    (origin.startsWith("https://") && origin.length > "https://".length) ||
    origin.startsWith("http://localhost")
  );
}

/**
 * Editor de allowed_origins de UNA key: lista de inputs + agregar/quitar
 * + guardar. La validación cliente replica la del backend para feedback
 * inmediato; el backend sigue siendo la autoridad (422 verbatim en toast).
 */
export function OriginsEditor({
  partnerId,
  apiKey,
}: {
  partnerId: string;
  apiKey: PartnerApiKeyOut;
}) {
  const [origins, setOrigins] = useState<string[]>(
    apiKey.allowed_origins.length > 0 ? apiKey.allowed_origins : [""],
  );
  const [pending, start] = useTransition();

  const state = partnerKeyState(apiKey);
  const cleaned = origins.map((o) => o.trim()).filter((o) => o !== "");
  const invalid = cleaned.filter((o) => !isValidOrigin(o));
  const dirty =
    cleaned.join("\n") !== apiKey.allowed_origins.join("\n");

  function setAt(index: number, value: string) {
    setOrigins((prev) => prev.map((o, i) => (i === index ? value : o)));
  }

  function removeAt(index: number) {
    setOrigins((prev) =>
      prev.length === 1 ? [""] : prev.filter((_, i) => i !== index),
    );
  }

  function onSave() {
    if (invalid.length > 0) return;
    start(async () => {
      const res = await updateKeyOriginsAction(partnerId, apiKey.id, cleaned);
      if (!res.ok) {
        toast.error("No se pudieron guardar los origins", {
          description: res.error,
        });
        return;
      }
      toast.success(`Origins de ${apiKey.prefix_snippet} actualizados`, {
        description:
          cleaned.length === 0
            ? "Lista vacía — el widget no cargará en ningún dominio."
            : `${cleaned.length} origin${cleaned.length === 1 ? "" : "s"} permitidos.`,
      });
    });
  }

  return (
    <section
      aria-label={`Origins de ${apiKey.prefix_snippet}`}
      className="rounded-md border border-border p-4 grid gap-3"
    >
      <div className="flex flex-wrap items-center gap-2">
        <code className="font-mono text-xs">{apiKey.prefix_snippet}</code>
        <Badge variant="outline" className="font-mono">
          {apiKey.type}
        </Badge>
        {state === "grace" ? (
          <Badge variant="secondary">{KEY_STATE_LABEL[state]}</Badge>
        ) : null}
      </div>

      <div className="grid gap-2">
        {origins.map((origin, index) => {
          const trimmed = origin.trim();
          const showError = trimmed !== "" && !isValidOrigin(trimmed);
          return (
            <div key={index} className="grid gap-1">
              <div className="flex items-center gap-2">
                <Input
                  value={origin}
                  onChange={(e) => setAt(index, e.target.value)}
                  placeholder="https://app.partner.com"
                  className="font-mono text-xs"
                  autoComplete="off"
                  autoCapitalize="off"
                  spellCheck={false}
                  aria-invalid={showError}
                  aria-label={`Origin ${index + 1}`}
                  disabled={pending}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="size-8 p-0 shrink-0"
                  aria-label={`Quitar origin ${index + 1}`}
                  onClick={() => removeAt(index)}
                  disabled={pending}
                >
                  <X className="size-4" aria-hidden="true" />
                </Button>
              </div>
              {showError ? (
                <p className="text-xs text-destructive">
                  Debe empezar con <code>https://</code> o{" "}
                  <code>http://localhost</code>.
                </p>
              ) : null}
            </div>
          );
        })}
      </div>

      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setOrigins((prev) => [...prev, ""])}
          disabled={pending || origins.length >= 20}
        >
          <Plus className="size-4" aria-hidden="true" />
          Agregar origen
        </Button>
        <Button
          type="button"
          size="sm"
          onClick={onSave}
          disabled={pending || invalid.length > 0 || !dirty}
        >
          {pending ? "Guardando…" : "Guardar"}
        </Button>
        {origins.length >= 20 ? (
          <span className="text-xs text-muted-foreground">
            Máximo 20 origins por key.
          </span>
        ) : null}
      </div>
    </section>
  );
}
