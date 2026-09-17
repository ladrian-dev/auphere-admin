"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { Button } from "./Button";

export interface DialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel: string;
  cancelLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
  children?: ReactNode;
}

/** Diálogo modal sobre <dialog> nativo: foco atrapado y Escape gratis. */
export function Dialog({ open, title, description, confirmLabel, cancelLabel = "Cancelar", onConfirm, onCancel, children }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby="dialog-title"
      aria-describedby={description ? "dialog-desc" : undefined}
      onCancel={(e) => {
        e.preventDefault();
        onCancel();
      }}
      onClick={(e) => {
        if (e.target === ref.current) onCancel();
      }}
      className="m-auto w-[min(92vw,26rem)] rounded-lg border border-line bg-surface p-0 text-ink shadow-3 backdrop:bg-brand-navy/60 backdrop:backdrop-blur-sm"
    >
      <div className="p-6">
        <h2 id="dialog-title" className="font-display text-xl font-semibold">
          {title}
        </h2>
        {description ? (
          <p id="dialog-desc" className="mt-2 text-sm text-ink-muted">
            {description}
          </p>
        ) : null}
        {children}
        <div className="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button variant="secondary" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button variant="primary" onClick={onConfirm} autoFocus>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </dialog>
  );
}
