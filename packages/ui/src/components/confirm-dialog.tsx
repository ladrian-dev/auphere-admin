"use client";

import * as React from "react";

import { Button } from "./button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "./dialog";
import { Input } from "./input";
import { Label } from "./label";

type ConfirmDialogProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: React.ReactNode;
  description?: React.ReactNode;
  confirmLabel?: React.ReactNode;
  cancelLabel?: React.ReactNode;
  /** Destructive styling + the confirm button waits for ``typeToConfirm``. */
  destructive?: boolean;
  /**
   * When set, the user must type this exact string (e.g. the client's
   * name) before the confirm button enables. Irreversible actions only.
   */
  typeToConfirm?: string;
  typeToConfirmLabel?: React.ReactNode;
  /** Async allowed; the dialog shows a pending state and closes on resolve. */
  onConfirm: () => void | Promise<void>;
  /** Error message from a failed confirm — shown inline, form is kept. */
  error?: React.ReactNode;
};

/**
 * The one confirmation dialog. Escape/overlay cancel; Enter confirms
 * (when enabled); focus lands on the least destructive control.
 */
function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  typeToConfirm,
  typeToConfirmLabel,
  onConfirm,
  error,
}: ConfirmDialogProps) {
  const [typed, setTyped] = React.useState("");
  const [pending, setPending] = React.useState(false);
  const inputId = React.useId();

  React.useEffect(() => {
    if (!open) {
      setTyped("");
      setPending(false);
    }
  }, [open]);

  const enabled = !pending && (typeToConfirm ? typed.trim() === typeToConfirm : true);

  async function confirm() {
    if (!enabled) return;
    setPending(true);
    try {
      await onConfirm();
    } finally {
      setPending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => onOpenChange(next)}>
      <DialogContent showCloseButton={false} aria-busy={pending || undefined}>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description ? <DialogDescription>{description}</DialogDescription> : null}
        </DialogHeader>
        {typeToConfirm ? (
          <form
            className="grid gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void confirm();
            }}
          >
            <Label htmlFor={inputId}>
              {typeToConfirmLabel ?? (
                <>
                  Type <span className="font-mono font-semibold">{typeToConfirm}</span> to confirm
                </>
              )}
            </Label>
            <Input
              id={inputId}
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              autoComplete="off"
              spellCheck={false}
              aria-invalid={error ? true : undefined}
            />
          </form>
        ) : null}
        {error ? (
          <p role="alert" className="text-sm text-status-danger">
            {error}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pending} autoFocus>
            {cancelLabel}
          </Button>
          <Button
            variant={destructive ? "destructive" : "default"}
            onClick={() => void confirm()}
            disabled={!enabled}
          >
            {confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export { ConfirmDialog, type ConfirmDialogProps };
