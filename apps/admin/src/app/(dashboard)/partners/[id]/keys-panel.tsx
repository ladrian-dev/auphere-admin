"use client";

import { useState, useTransition } from "react";
import { toast } from "sonner";

import { StatusDot } from "@/components/brand/status-dot";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type {
  PartnerApiKeyCreatedOut,
  PartnerApiKeyOut,
  PartnerApiKeyType,
} from "@/lib/backend";
import { relativeTime } from "@/lib/format";

import {
  createPartnerKeyAction,
  revokePartnerKeyAction,
  rotatePartnerKeyAction,
} from "../actions";
import {
  KEY_STATE_LABEL,
  KEY_STATE_TONE,
  partnerKeyState,
} from "./key-state";
import { PlaintextKeyDialog } from "./plaintext-key-dialog";

/** Scopes que el backend acepta hoy (default del ApiKeyCreateIn). */
const AVAILABLE_SCOPES = ["provision", "widget_sessions"] as const;

/**
 * Keys tab surface. Client component porque el flujo crear/rotar termina
 * en el dialog de plaintext (estado compartido entre la tabla y ambos
 * dialogs) — el fetch de la lista sigue siendo del server component padre.
 */
export function KeysPanel({
  partnerId,
  keys,
}: {
  partnerId: string;
  keys: PartnerApiKeyOut[];
}) {
  const [createdKey, setCreatedKey] = useState<PartnerApiKeyCreatedOut | null>(
    null,
  );

  return (
    <div className="grid gap-4">
      <div className="flex justify-end">
        <CreateKeyDialog partnerId={partnerId} onCreated={setCreatedKey} />
      </div>

      {keys.length === 0 ? (
        <div className="rounded-md border border-dashed border-border py-12 text-center text-sm text-muted-foreground">
          Sin API keys todavía. Crea la primera con &quot;Nueva key&quot;
          arriba a la derecha — el partner la necesita para autenticarse
          server-to-server.
        </div>
      ) : (
        <div className="rounded-md border border-border bg-card overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Key</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead className="hidden md:table-cell">Scopes</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead className="hidden sm:table-cell text-right">
                  Último uso
                </TableHead>
                <TableHead className="hidden md:table-cell text-right">
                  Creada
                </TableHead>
                <TableHead className="w-40 text-right" aria-label="Acciones" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((key) => {
                const state = partnerKeyState(key);
                return (
                  <TableRow key={key.id}>
                    <TableCell className="font-mono text-xs">
                      {key.prefix_snippet}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="font-mono">
                        {key.type}
                      </Badge>
                    </TableCell>
                    <TableCell className="hidden md:table-cell">
                      <span className="flex flex-wrap gap-1">
                        {key.scopes.length === 0 ? (
                          <span className="text-muted-foreground">—</span>
                        ) : (
                          key.scopes.map((scope) => (
                            <Badge
                              key={scope}
                              variant="secondary"
                              className="font-mono text-[10px]"
                            >
                              {scope}
                            </Badge>
                          ))
                        )}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="inline-flex items-center gap-2">
                        <StatusDot tone={KEY_STATE_TONE[state]} />
                        <span>{KEY_STATE_LABEL[state]}</span>
                        {state === "grace" && key.grace_expires_at ? (
                          <span className="text-xs text-muted-foreground">
                            hasta {relativeTime(key.grace_expires_at)}
                          </span>
                        ) : null}
                      </span>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell text-right text-muted-foreground tabular-nums">
                      {key.last_used_at
                        ? relativeTime(key.last_used_at)
                        : "Nunca"}
                    </TableCell>
                    <TableCell className="hidden md:table-cell text-right text-muted-foreground tabular-nums">
                      {relativeTime(key.created_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      {state === "active" || state === "expired" ? (
                        <KeyRowActions
                          partnerId={partnerId}
                          apiKey={key}
                          onRotated={setCreatedKey}
                        />
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}

      <PlaintextKeyDialog
        createdKey={createdKey}
        onClose={() => setCreatedKey(null)}
      />
    </div>
  );
}

// ── crear key ────────────────────────────────────────────────────────────────

function CreateKeyDialog({
  partnerId,
  onCreated,
}: {
  partnerId: string;
  onCreated: (key: PartnerApiKeyCreatedOut) => void;
}) {
  const [open, setOpen] = useState(false);
  const [type, setType] = useState<PartnerApiKeyType>("live");
  const [scopes, setScopes] = useState<string[]>([...AVAILABLE_SCOPES]);
  const [expiresAt, setExpiresAt] = useState("");
  const [pending, start] = useTransition();

  function toggleScope(scope: string, checked: boolean) {
    setScopes((prev) =>
      checked ? [...prev, scope] : prev.filter((s) => s !== scope),
    );
  }

  function onSubmit() {
    start(async () => {
      const res = await createPartnerKeyAction(partnerId, {
        type,
        scopes,
        expires_at: expiresAt
          ? new Date(`${expiresAt}T00:00:00Z`).toISOString()
          : null,
      });
      if (!res.ok) {
        toast.error("No se pudo crear la key", { description: res.error });
        return;
      }
      setOpen(false);
      setType("live");
      setScopes([...AVAILABLE_SCOPES]);
      setExpiresAt("");
      toast.success("Key creada — guarda el plaintext ahora");
      onCreated(res.data);
    });
  }

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Nueva key
      </Button>
      <Dialog
        open={open}
        onOpenChange={(o) => {
          if (!pending) setOpen(o);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nueva API key</DialogTitle>
            <DialogDescription>
              El plaintext se muestra una única vez después de crearla.
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-4">
            <div className="grid gap-2">
              <Label htmlFor="key-type">Tipo</Label>
              <Select
                value={type}
                onValueChange={(v) => setType(v as PartnerApiKeyType)}
              >
                <SelectTrigger id="key-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="live">
                    live — producción del partner
                  </SelectItem>
                  <SelectItem value="test">
                    test — integración / sandbox
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>

            <fieldset className="grid gap-2">
              <legend className="text-sm font-medium">Scopes</legend>
              {AVAILABLE_SCOPES.map((scope) => (
                <label
                  key={scope}
                  className="flex items-center gap-2 text-sm"
                  htmlFor={`scope-${scope}`}
                >
                  <Checkbox
                    id={`scope-${scope}`}
                    checked={scopes.includes(scope)}
                    onCheckedChange={(checked) =>
                      toggleScope(scope, checked === true)
                    }
                  />
                  <span className="font-mono text-xs">{scope}</span>
                </label>
              ))}
              {scopes.length === 0 ? (
                <p className="text-xs text-destructive">
                  Selecciona al menos un scope.
                </p>
              ) : null}
            </fieldset>

            <div className="grid gap-2">
              <Label htmlFor="key-expires">Expira (opcional)</Label>
              <Input
                id="key-expires"
                type="date"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Vacío = sin expiración. UTC, medianoche del día elegido.
              </p>
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setOpen(false)}
              disabled={pending}
            >
              Cancelar
            </Button>
            <Button
              size="sm"
              onClick={onSubmit}
              disabled={pending || scopes.length === 0}
            >
              {pending ? "Creando…" : "Crear key"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

// ── rotar / revocar ──────────────────────────────────────────────────────────

function KeyRowActions({
  partnerId,
  apiKey,
  onRotated,
}: {
  partnerId: string;
  apiKey: PartnerApiKeyOut;
  onRotated: (key: PartnerApiKeyCreatedOut) => void;
}) {
  const [rotateOpen, setRotateOpen] = useState(false);
  const [revokeOpen, setRevokeOpen] = useState(false);
  const [graceHours, setGraceHours] = useState("24");
  const [pending, start] = useTransition();

  const graceParsed = Number(graceHours);
  const graceValid =
    Number.isInteger(graceParsed) && graceParsed >= 0 && graceParsed <= 336;

  function onRotate() {
    if (!graceValid) return;
    start(async () => {
      const res = await rotatePartnerKeyAction(
        partnerId,
        apiKey.id,
        graceParsed,
      );
      if (!res.ok) {
        toast.error("No se pudo rotar la key", { description: res.error });
        return;
      }
      setRotateOpen(false);
      setGraceHours("24");
      toast.success(
        `Key rotada — la anterior sigue válida ${graceParsed} h más`,
      );
      onRotated(res.data);
    });
  }

  function onRevoke() {
    start(async () => {
      const res = await revokePartnerKeyAction(partnerId, apiKey.id);
      if (!res.ok) {
        toast.error("No se pudo revocar la key", { description: res.error });
        return;
      }
      setRevokeOpen(false);
      toast.success(`Key ${apiKey.prefix_snippet} revocada de inmediato`);
    });
  }

  return (
    <span className="inline-flex items-center justify-end gap-2">
      <Button
        variant="outline"
        size="sm"
        disabled={pending}
        onClick={() => setRotateOpen(true)}
      >
        Rotar
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="text-destructive hover:text-destructive"
        disabled={pending}
        onClick={() => setRevokeOpen(true)}
      >
        Revocar
      </Button>

      <Dialog
        open={rotateOpen}
        onOpenChange={(o) => {
          if (!pending) setRotateOpen(o);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rotar {apiKey.prefix_snippet}</DialogTitle>
            <DialogDescription>
              Se genera una key nueva con los mismos scopes. La
              actual queda revocada pero sigue autenticando durante el
              período de gracia — tiempo para que el partner despliegue el
              secreto nuevo sin downtime.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor={`grace-${apiKey.id}`}>
              Horas de gracia (0–336)
            </Label>
            <Input
              id={`grace-${apiKey.id}`}
              type="number"
              min={0}
              max={336}
              step={1}
              value={graceHours}
              onChange={(e) => setGraceHours(e.target.value)}
              className="max-w-32 tabular-nums"
              aria-invalid={!graceValid}
            />
            {!graceValid ? (
              <p className="text-xs text-destructive">
                Entero entre 0 y 336 (14 días).
              </p>
            ) : (
              <p className="text-xs text-muted-foreground">
                Default 24 h. Con 0, la key vieja muere al instante.
              </p>
            )}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setRotateOpen(false)}
              disabled={pending}
            >
              Cancelar
            </Button>
            <Button
              size="sm"
              onClick={onRotate}
              disabled={pending || !graceValid}
            >
              {pending ? "Rotando…" : "Rotar key"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={revokeOpen}
        onOpenChange={(o) => {
          if (!pending) setRevokeOpen(o);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revocar {apiKey.prefix_snippet}</DialogTitle>
            <DialogDescription>
              Revocación inmediata, <strong>sin gracia</strong>: la key y
              todos los session tokens del widget emitidos con ella dejan de
              funcionar ahora mismo. Si el partner la sigue usando, su
              integración se cae. No se puede deshacer.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setRevokeOpen(false)}
              disabled={pending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={onRevoke}
              disabled={pending}
            >
              {pending ? "Revocando…" : "Revocar ahora"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </span>
  );
}
