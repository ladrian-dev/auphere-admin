"use client";

import { Check, Copy, KeyRound, MoreHorizontal } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type RefObject } from "react";
import { toast } from "sonner";

import {
  Button,
  ConfirmDialog,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  EmptyState,
  ErrorState,
  Input,
  Label,
  PageHeader,
  StatusBadge,
} from "@nexus/ui";
import type { TenantApiKeyCreatedOut, TenantApiKeyOut } from "@/lib/backend";
import { longDate, relativeTime } from "@/lib/format";
import { KEY_STATE, keyState } from "@/lib/send-only";

import { createTenantKeyAction, revokeTenantKeyAction, rotateTenantKeyAction } from "./actions";

/**
 * Spec 077 (requisito 5): the client's sending keys. «Crear clave» is the one
 * primary action; the whole key is shown once, right here, and never again.
 * Rotating and revoking ask for confirmation and land in the audit with the
 * operator's name. `keys === null`: the list could not be read.
 */
export function ApiKeysPanel({
  tenantId,
  tenantName,
  keys,
}: {
  tenantId: string;
  tenantName: string;
  keys: TenantApiKeyOut[] | null;
}) {
  const router = useRouter();
  const [fresh, setFresh] = useState<TenantApiKeyCreatedOut | null>(null);
  const [creating, setCreating] = useState(false);
  // Where focus lands after a revoke: the row's menu is gone once the list reloads.
  const keysHeading = useRef<HTMLHeadingElement>(null);

  async function create() {
    setCreating(true);
    const res = await createTenantKeyAction(tenantId);
    setCreating(false);
    if (!res.ok) {
      toast.error("No se pudo crear la clave", { description: res.error });
      return;
    }
    setFresh(res.data);
    toast.success("Clave creada", { description: "Cópiala ahora: no se vuelve a mostrar." });
    router.refresh();
  }

  const createButton = (
    <Button onClick={() => void create()} loading={creating} disabled={creating}>
      <KeyRound aria-hidden="true" />
      Crear clave
    </Button>
  );

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        size="compact"
        title="Envío por API"
        description={`Las claves con las que el sistema de ${tenantName} envía plantillas, cómo llama y sus últimos envíos.`}
        actions={createButton}
      />

      {/* Always mounted, so the new key is announced when it appears (WCAG 4.1.3). */}
      <p aria-live="polite" className="sr-only">
        {fresh ? `Clave ${fresh.key.prefix_snippet} creada. Cópiala ahora: no se vuelve a mostrar.` : ""}
      </p>

      {/* Keyed by the key: a new one starts with «Copiar», never with the last «Copiada». */}
      {/* «Ya la guardé» unmounts the focused button: focus goes to the list, not to <body>. */}
      {fresh ? (
        <FreshKey
          key={fresh.key.id}
          created={fresh}
          onDone={() => {
            setFresh(null);
            keysHeading.current?.focus();
          }}
        />
      ) : null}

      <section aria-labelledby="keys-title" className="flex flex-col gap-3">
        <h2
          ref={keysHeading}
          id="keys-title"
          tabIndex={-1}
          className="rounded-md text-lg font-semibold text-balance focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          Claves de acceso
        </h2>
        {keys === null ? (
          <ErrorState
            title="No se pudieron leer las claves"
            description="La API no respondió. Vuelve a intentarlo en unos segundos."
            onRetry={() => router.refresh()}
            retryLabel="Reintentar"
          />
        ) : keys.length === 0 ? (
          <EmptyState
            icon={KeyRound}
            title="Este cliente todavía no tiene claves"
            description="Su sistema manda la clave en cada llamada a la API."
            action={createButton}
          />
        ) : (
          <ul className="divide-y divide-border rounded-md ring-1 ring-border">
            {keys.map((key) => (
              <KeyRow key={key.id} tenantId={tenantId} apiKey={key} onRotated={setFresh} afterRevoke={keysHeading} />
            ))}
          </ul>
        )}
        <p className="text-xs text-pretty text-muted-foreground">
          Las claves de este cliente. Las del partner siguen en su ficha. Rotar y revocar piden confirmación y quedan en
          Auditoría con tu nombre.
        </p>
      </section>
    </div>
  );
}

/**
 * The whole key, once. Copy it now: the panel does not keep it. On mount it
 * scrolls into view and takes focus (the input selects itself), so whoever
 * created or rotated it lands on it — a rotate starts far down the list.
 */
function FreshKey({ created, onDone }: { created: TenantApiKeyCreatedOut; onDone: () => void }) {
  const [copied, setCopied] = useState(false);
  const regionRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    // Instant, not smooth: nothing to opt out of under reduced motion.
    regionRef.current?.scrollIntoView?.({ block: "nearest" });
    inputRef.current?.focus({ preventScroll: true });
  }, []);
  async function copy() {
    try {
      await navigator.clipboard.writeText(created.plaintext);
      setCopied(true);
      toast.success("Clave copiada");
    } catch {
      toast.error("No se pudo copiar: selecciona el texto y cópialo a mano");
    }
  }
  return (
    <div
      ref={regionRef}
      role="region"
      aria-labelledby="fresh-key-title"
      className="flex scroll-mt-4 flex-col gap-3 rounded-md border border-primary bg-primary/10 p-4"
    >
      {/* No role="status": the always-mounted live region above already announces it. */}
      <p id="fresh-key-title" className="text-sm font-semibold text-pretty">
        Copia la clave ahora. No se vuelve a mostrar.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Label htmlFor="fresh-key" className="sr-only">
          Clave nueva
        </Label>
        <Input
          ref={inputRef}
          id="fresh-key"
          readOnly
          aria-describedby="fresh-key-title"
          value={created.plaintext}
          onFocus={(e) => e.currentTarget.select()}
          className="min-w-0 flex-1 basis-72 bg-background font-mono text-xs"
        />
        <Button type="button" variant="outline" onClick={() => void copy()}>
          {copied ? <Check aria-hidden="true" /> : <Copy aria-hidden="true" />}
          {copied ? "Copiada" : "Copiar"}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Ya la guardé
        </Button>
      </div>
      <p className="text-xs text-pretty text-muted-foreground">
        Su prefijo, el que verás en la lista: <code className="font-mono">{created.key.prefix_snippet}</code>. Entrégasela
        al cliente por un canal seguro.
      </p>
    </div>
  );
}

function KeyRow({
  tenantId,
  apiKey,
  onRotated,
  afterRevoke,
}: {
  tenantId: string;
  apiKey: TenantApiKeyOut;
  onRotated: (created: TenantApiKeyCreatedOut) => void;
  /** A revoked key loses its menu: focus goes here instead of to nothing. */
  afterRevoke: RefObject<HTMLElement | null>;
}) {
  const router = useRouter();
  const [dialog, setDialog] = useState<"rotate" | "revoke" | null>(null);
  // Only a confirmed action moves focus away from the menu; a cancel returns to it.
  const done = useRef<"rotated" | "revoked" | null>(null);
  const [grace, setGrace] = useState("24");
  const [error, setError] = useState<string | null>(null);
  const state = keyState(apiKey);
  const shown = KEY_STATE[state];
  const live = state === "active" || state === "grace";
  const graceHours = Number(grace);
  const graceValid = grace.trim() !== "" && Number.isInteger(graceHours) && graceHours >= 0 && graceHours <= 336;

  function openDialog(d: "rotate" | "revoke") {
    done.current = null;
    setDialog(d);
  }

  async function rotate() {
    setError(null);
    const res = await rotateTenantKeyAction(tenantId, apiKey.id, graceHours);
    if (!res.ok) return void setError(res.error);
    done.current = "rotated";
    setDialog(null);
    toast.success(
      graceHours > 0 ? `Clave rotada: la anterior sigue valiendo ${graceHours} h` : "Clave rotada: la anterior ya no vale",
    );
    onRotated(res.data);
    router.refresh();
  }

  async function revoke() {
    setError(null);
    const res = await revokeTenantKeyAction(tenantId, apiKey.id);
    if (!res.ok) return void setError(res.error);
    done.current = "revoked";
    setDialog(null);
    toast.success(`Clave ${apiKey.prefix_snippet} revocada`);
    router.refresh();
  }

  return (
    <li className="flex flex-wrap items-center gap-3 px-4 py-3">
      <div className="flex min-w-0 flex-1 basis-64 flex-col gap-1">
        <span className="truncate font-mono text-sm font-medium">{apiKey.prefix_snippet}…</span>
        <span className="text-xs text-pretty wrap-anywhere text-muted-foreground">
          Creada el {longDate(apiKey.created_at)}
          {apiKey.created_by ? ` por ${apiKey.created_by}` : ""} ·{" "}
          {apiKey.last_used_at ? `usada ${relativeTime(apiKey.last_used_at)}` : "sin usar todavía"}
          {state === "grace" && apiKey.grace_expires_at ? ` · deja de valer ${relativeTime(apiKey.grace_expires_at)}` : ""}
        </span>
      </div>
      <StatusBadge tone={shown.tone}>{shown.label}</StatusBadge>
      {live ? (
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <Button variant="outline" size="icon-sm" aria-label={`Opciones de la clave ${apiKey.prefix_snippet}`}>
                <MoreHorizontal aria-hidden="true" />
              </Button>
            }
          />
          <DropdownMenuContent align="end" className="min-w-40">
            {state === "active" ? <DropdownMenuItem onClick={() => openDialog("rotate")}>Rotar…</DropdownMenuItem> : null}
            <DropdownMenuItem variant="destructive" onClick={() => openDialog("revoke")}>
              Revocar…
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ) : (
        // Keeps the rows aligned: a revoked key has nothing left to do.
        <span className="size-8 shrink-0" aria-hidden="true" />
      )}

      <ConfirmDialog
        open={dialog === "rotate"}
        onOpenChange={(open) => {
          if (!open) {
            setDialog(null);
            setError(null);
            setGrace("24");
          }
        }}
        title={`¿Rotar ${apiKey.prefix_snippet}?`}
        description="Se crea una clave nueva para este mismo cliente y se muestra una sola vez. La actual sigue valiendo durante las horas de gracia, para que su sistema cambie a la nueva sin cortes."
        confirmLabel="Rotar clave"
        confirmDisabled={!graceValid}
        onConfirm={rotate}
        error={error ?? undefined}
        // The new key's input, which the panel shows above the list.
        returnFocus={() => (done.current === "rotated" ? document.getElementById("fresh-key") : null)}
      >
        <Label htmlFor={`grace-${apiKey.id}`}>Horas de gracia (0 a 336)</Label>
        <Input
          id={`grace-${apiKey.id}`}
          type="number"
          inputMode="numeric"
          min={0}
          max={336}
          step={1}
          value={grace}
          onChange={(e) => setGrace(e.target.value)}
          aria-invalid={!graceValid || undefined}
          aria-describedby={`grace-help-${apiKey.id}`}
          className="max-w-32 tabular-nums"
        />
        <p id={`grace-help-${apiKey.id}`} className={graceValid ? "text-xs text-muted-foreground" : "text-xs text-destructive"}>
          {graceValid ? "Con 0, la clave actual deja de valer al instante." : "Un número entero de 0 a 336 (14 días)."}
        </p>
      </ConfirmDialog>

      <ConfirmDialog
        open={dialog === "revoke"}
        onOpenChange={(open) => {
          if (!open) {
            setDialog(null);
            setError(null);
          }
        }}
        title={`¿Revocar ${apiKey.prefix_snippet}?`}
        description="Deja de valer ahora mismo, sin gracia. Si su sistema la sigue usando, sus envíos fallan. No se puede deshacer."
        confirmLabel="Revocar ahora"
        destructive
        onConfirm={revoke}
        error={error ?? undefined}
        returnFocus={() => (done.current === "revoked" ? afterRevoke.current : null)}
      />
    </li>
  );
}
