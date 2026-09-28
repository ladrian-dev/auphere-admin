"use client";

import {
  Brush,
  Flower2,
  HeartPulse,
  MessageCircle,
  Package,
  PenLine,
  Receipt,
  Scissors,
  Search,
  ShoppingCart,
  Smile,
  Sparkles,
  Stethoscope,
  Syringe,
  UtensilsCrossed,
  type LucideIcon,
} from "lucide-react";
import * as React from "react";

import { Button, EmptyState, Input, cn } from "@nexus/ui";

import { useT } from "@/i18n/client";
import type { SeedTemplate } from "@/lib/backend/onboarding";

/**
 * A qué se dedica el negocio (spec 019, R2). La primera pregunta del alta.
 *
 * **Primera porque decide el resto**: la plantilla fija el prompt, las
 * herramientas y qué campos existen siquiera, así que elegirla antes estrecha
 * todo lo demás.
 *
 * **Y nada viene marcado.** Hasta la spec 019 venía seleccionada la que la API
 * devuelve primera —por orden alfabético, no por encaje— y daba la casualidad
 * de ser la más pesada de las trece: quien daba de alta una barbería
 * aterrizaba en un formulario de medicina estética pidiéndole la credencial
 * del titular. Una elección arbitraria es peor que ninguna.
 *
 * Cada tarjeta dice **para qué sirve y cuánto trae**, no su clave interna.
 * Eso es lo que convierte trece nombres en una decisión.
 */

/** El rubro, de un vistazo. Trece nombres en una rejilla se leen uno a uno. */
const ICONOS: Record<string, LucideIcon> = {
  barbershop: Scissors,
  beauty_salon: Sparkles,
  nail_studio: Brush,
  spa: Flower2,
  dental: Smile,
  clinica: Stethoscope,
  medspa: Syringe,
  aesthetic_clinic: HeartPulse,
  restaurante: UtensilsCrossed,
  generic: MessageCircle,
  cobranza: Receipt,
  inventario: Package,
  woocommerce_sales: ShoppingCart,
};

/** Una plantilla que el catálogo añada mañana no se queda sin cara. */
function iconoDe(template: SeedTemplate): LucideIcon {
  return ICONOS[template.name.replace(/_v\d+$/, "")] ?? MessageCircle;
}

export function TemplatePicker({
  templates,
  value,
  onChange,
}: {
  /** `null` cuando el catálogo no se pudo leer. */
  templates: SeedTemplate[] | null;
  value: string | null;
  onChange: (name: string | null) => void;
}) {
  const t = useT();
  const [q, setQ] = React.useState("");
  const todas = React.useMemo(() => templates ?? [], [templates]);
  const aguja = q.trim().toLowerCase();
  const visibles = React.useMemo(
    () => (aguja ? todas.filter((x) => x.display_name.toLowerCase().includes(aguja)) : todas),
    [todas, aguja],
  );

  // `value` es `string | null`, y `null` es una elección legítima —«ninguna de
  // estas»—, así que «aún no ha elegido» necesita su propio estado.
  const [tocado, setTocado] = React.useState(false);
  function elegir(next: string | null) {
    setTocado(true);
    onChange(next);
  }

  return (
    <div className="flex flex-col gap-4">
      {templates === null ? (
        <p role="alert" className="text-sm text-pretty text-muted-foreground">
          {t("wizard.template.unreadable")}
        </p>
      ) : (
        <div className="flex flex-wrap items-center gap-3">
          <span className="relative inline-flex min-w-0 flex-1 basis-64 items-center">
            <Search aria-hidden="true" className="absolute left-3 size-4 text-muted-foreground" />
            <Input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              aria-label={t("wizard.template.search")}
              placeholder={t("wizard.template.search.placeholder", { n: todas.length })}
              className="w-full pl-9"
            />
          </span>
          <span className="text-sm text-muted-foreground tabular-nums" aria-live="polite">
            {t("wizard.template.count", { shown: visibles.length, total: todas.length })}
          </span>
        </div>
      )}

      {templates !== null && visibles.length === 0 ? (
        <EmptyState
          icon={Search}
          title={t("wizard.template.noResults", { q: q.trim() })}
          description={t("wizard.template.noResults.body")}
          action={
            <Button variant="outline" onClick={() => setQ("")}>
              {t("common.cancel")}
            </Button>
          }
        />
      ) : null}

      <div role="radiogroup" aria-label={t("wizard.template.title")} className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        {visibles.map((tpl) => {
          const Icono = iconoDe(tpl);
          const elegida = tocado && value === tpl.name;
          return (
            <button
              key={tpl.name}
              type="button"
              role="radio"
              aria-checked={elegida}
              onClick={() => elegir(tpl.name)}
              className={cn(OPCION, elegida && ELEGIDA)}
            >
              <span className="flex min-w-0 items-center gap-2">
                <Icono aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
                <span className="min-w-0 truncate font-medium">{tpl.display_name}</span>
              </span>
              <span className="text-xs text-muted-foreground tabular-nums">
                {t("wizard.template.skills", { n: tpl.tools_count })}
              </span>
            </button>
          );
        })}

        {/* No encontrar la tuya no puede ser un callejón: esta opción está
            siempre, también con el buscador sin resultados. */}
        <button
          type="button"
          role="radio"
          aria-checked={tocado && value === null}
          onClick={() => elegir(null)}
          className={cn(OPCION, "border-dashed", tocado && value === null && ELEGIDA)}
        >
          <span className="flex min-w-0 items-center gap-2">
            <PenLine aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
            <span className="font-medium">{t("wizard.template.none")}</span>
          </span>
          <span className="text-sm text-pretty text-muted-foreground">{t("wizard.template.none.body")}</span>
        </button>
      </div>
    </div>
  );
}

const OPCION =
  "flex min-w-0 cursor-pointer flex-col items-start gap-1 rounded-md border border-border px-3 py-2 text-left transition-colors hover:bg-muted/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";
const ELEGIDA = "border-foreground bg-muted";
