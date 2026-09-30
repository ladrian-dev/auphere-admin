"use client";

import { BookOpen, Check } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import {
  Button,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  EmptyState,
} from "@nexus/ui";

import { listCatalogsAction, setCatalogAction } from "@/app/(console)/clients/[ref]/channels/actions";
import { useT } from "@/i18n/client";
import type { MessageKey } from "@/i18n/messages";
import type { Catalog, CatalogSummary } from "@/lib/backend/channels";

/**
 * Pure: la frase para un rechazo de la API del catálogo. Lo que Meta dice se
 * enseña como dato dentro de una frase nuestra (constitución III); un código
 * que no conozcamos cae en la frase genérica de la consola.
 */
export function catalogFailureKey(code: string | null | undefined): MessageKey | null {
  switch (code) {
    case "catalog_permission_missing":
      return "ch.catalog.permission";
    case "catalog_not_owned":
      return "ch.catalog.err.catalog_not_owned";
    case "meta_unavailable":
      return "ch.catalog.err.meta_unavailable";
    case "catalog_meta_rejected":
      return "ch.catalog.err.catalog_meta_rejected";
    case "channel_has_no_credentials":
      return "ch.catalog.err.channel_has_no_credentials";
    default:
      return null;
  }
}

/** Pure: cambiar de catálogo pide confirmar (Q3); conectar el primero, no. */
export function replacementNeeded(current: Catalog | null, chosenId: string): boolean {
  return current !== null && current.id !== chosenId;
}

type Loaded =
  | { kind: "loading" }
  | { kind: "error"; code: string | null; message: string | null }
  | { kind: "ready"; items: CatalogSummary[]; linkedId: string | null };

/**
 * El cuerpo del selector, sin el diálogo alrededor: lista, vacío diseñado,
 * error con frase. Separado para poder probarlo sin abrir un diálogo de
 * Base UI bajo jsdom.
 */
export function CatalogPickerBody({
  state,
  current,
  busy,
  onChoose,
}: {
  state: Loaded;
  current: Catalog | null;
  busy: boolean;
  onChoose: (item: CatalogSummary) => void;
}) {
  const t = useT();
  if (state.kind === "loading") {
    return (
      <p role="status" className="text-sm text-muted-foreground">
        {t("ch.catalog.picker.loading")}
      </p>
    );
  }
  if (state.kind === "error") {
    const key = catalogFailureKey(state.code);
    return (
      <p role="alert" className="text-sm text-destructive">
        {key ? t(key, { message: state.message ?? "" }) : t("common.error.backend")}
      </p>
    );
  }
  if (state.items.length === 0) {
    return <EmptyState icon={BookOpen} title={t("ch.catalog.picker.empty.title")} description={t("ch.catalog.picker.empty.body")} readonly />;
  }
  return (
    <ul className="flex flex-col gap-2" aria-label={t("ch.catalog.picker.title")}>
      {state.items.map((item) => {
        const linked = item.id === (current?.id ?? state.linkedId);
        return (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => onChoose(item)}
              disabled={busy || linked}
              aria-current={linked ? "true" : undefined}
              className="flex w-full items-center justify-between gap-3 rounded-md border border-border px-3 py-2 text-left text-sm hover:bg-muted disabled:opacity-70"
            >
              <span className="flex min-w-0 flex-col">
                <span className="truncate font-medium">{item.name ?? item.id}</span>
                {item.product_count !== null ? (
                  <span className="text-xs text-muted-foreground">{t("ch.catalog.picker.products", { n: item.product_count })}</span>
                ) : null}
              </span>
              {linked ? (
                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <Check aria-hidden="true" className="size-4" />
                  {t("ch.catalog.picker.linked")}
                </span>
              ) : null}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * El diálogo que conecta (o cambia) el catálogo del número. `offer` es la
 * variante que el alta abre al terminar (Historia 2): el botón de cerrar
 * dice «Ahora no».
 */
export function CatalogPicker({
  refId,
  channelId,
  current,
  open,
  onOpenChange,
  offer = false,
}: {
  refId: string;
  channelId: string;
  current: Catalog | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  offer?: boolean;
}) {
  const t = useT();
  const router = useRouter();
  // `null` es «aún no se ha pedido»: se pide al abrir y se olvida al cerrar
  // (en el manejador de cierre), para que la lista sea siempre la de esta
  // apertura y no una vieja.
  const [loaded, setLoaded] = React.useState<Loaded | null>(null);
  const [chosen, setChosen] = React.useState<CatalogSummary | null>(null);
  const [pending, startTransition] = React.useTransition();
  const state: Loaded = loaded ?? { kind: "loading" };

  React.useEffect(() => {
    if (!open) return;
    let alive = true;
    void listCatalogsAction({ ref: refId, channelId }).then((res) => {
      if (!alive) return;
      if (!res.ok) return void setLoaded({ kind: "error", code: res.code ?? null, message: res.message ?? null });
      setLoaded({ kind: "ready", items: res.data.items, linkedId: res.data.linked_id });
    });
    return () => {
      alive = false;
    };
  }, [open, refId, channelId]);

  function close(next: boolean) {
    if (pending) return;
    if (!next) setLoaded(null);
    onOpenChange(next);
  }

  function apply(item: CatalogSummary) {
    startTransition(async () => {
      const res = await setCatalogAction({ ref: refId, channelId, catalogId: item.id });
      if (!res.ok) {
        const key = catalogFailureKey(res.code);
        return void toast.error(key ? t(key, { message: res.message ?? "" }) : t("common.error.backend"));
      }
      setChosen(null);
      setLoaded(null);
      onOpenChange(false);
      if (res.data.catalog) toast.success(t("ch.catalog.done", { name: res.data.catalog.name ?? res.data.catalog.id }));
      else if (res.data.catalog_error) {
        const key = catalogFailureKey(res.data.catalog_error.code);
        toast.error(key ? t(key, { message: res.data.catalog_error.message ?? "" }) : t("common.error.backend"));
      }
      router.refresh();
    });
  }

  function choose(item: CatalogSummary) {
    if (replacementNeeded(current, item.id)) setChosen(item);
    else apply(item);
  }

  return (
    <>
      <Dialog open={open} onOpenChange={close}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("ch.catalog.picker.title")}</DialogTitle>
            <DialogDescription>{t("ch.catalog.picker.help")}</DialogDescription>
          </DialogHeader>
          <CatalogPickerBody state={state} current={current} busy={pending} onChoose={choose} />
          <DialogFooter>
            <Button variant="outline" onClick={() => close(false)} disabled={pending}>
              {offer ? t("ch.catalog.picker.later") : t("common.cancel")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={chosen !== null}
        onOpenChange={(o) => !o && setChosen(null)}
        title={t("ch.catalog.replace.title", { from: current?.name ?? current?.id ?? "", to: chosen?.name ?? chosen?.id ?? "" })}
        description={t("ch.catalog.replace.body", { from: current?.name ?? current?.id ?? "", to: chosen?.name ?? chosen?.id ?? "" })}
        confirmLabel={t("ch.catalog.replace.confirm")}
        cancelLabel={t("common.cancel")}
        onConfirm={async () => {
          if (chosen) apply(chosen);
        }}
      />
    </>
  );
}
