"use client";

import * as React from "react";

import { ConfirmDialog } from "@nexus/ui";

import { useT } from "@/i18n/client";

/**
 * No perder lo escrito — spec 056 (requisito 12.3). Un diálogo con datos
 * escritos pregunta antes de cerrarse (Escape, el fondo, la X o «Cancelar»);
 * sin nada escrito se cierra como siempre. Guardar con éxito llama a `onClose`
 * directamente y no pregunta.
 *
 * ```tsx
 * const guard = useDiscardGuard(dirty, onClose);
 * <Dialog open onOpenChange={guard.onOpenChange}>… <Button onClick={guard.close}>Cancelar</Button>
 * {guard.dialog}
 * ```
 *
 * La pregunta es la de Apple para descartar (lo destructivo en rojo, con
 * «Seguir editando» como salida segura y con el foco). Hoy la usan los diálogos
 * de Reservas, por eso sus textos viven en ese carril (`reservas.discard.*`).
 */
export function useDiscardGuard(dirty: boolean, onClose: () => void) {
  const t = useT();
  const [asking, setAsking] = React.useState(false);
  const close = React.useCallback(() => (dirty ? setAsking(true) : onClose()), [dirty, onClose]);
  const onOpenChange = React.useCallback((open: boolean) => (open ? undefined : close()), [close]);
  const dialog = (
    <ConfirmDialog
      open={asking}
      onOpenChange={(open) => (open ? undefined : setAsking(false))}
      title={t("reservas.discard.title")}
      description={t("reservas.discard.body")}
      confirmLabel={t("reservas.discard.confirm")}
      cancelLabel={t("reservas.discard.keep")}
      destructive
      onConfirm={() => {
        setAsking(false);
        onClose();
      }}
    />
  );
  return { close, onOpenChange, dialog, asking };
}
