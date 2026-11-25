"use client";

import * as React from "react";

import { cn } from "@nexus/ui";

/**
 * Un importe rápido que se elige (spec 072 §6.1). Asignar saldo y Comprar
 * saldo eligen el importe igual: un clic **elige**, no compra ni asigna. El
 * elegido queda marcado con un tinte del primario y su borde, nunca relleno
 * como un segundo botón principal: el único botón principal es el que dice el
 * importe («Asignar 20,00 USD», «Comprar 50,00 USD»).
 *
 * Es un `radio` nativo dentro de su etiqueta: las flechas recorren los
 * importes y un lector de pantalla dice cuál está elegido.
 */
export function AmountOption({
  name,
  checked,
  onChange,
  size = "sm",
  children,
}: {
  name: string;
  checked: boolean;
  onChange: () => void;
  /** `sm`: píldora en línea (Asignar saldo). `lg`: casilla de la rejilla (Comprar saldo). */
  size?: "sm" | "lg";
  children: React.ReactNode;
}) {
  return (
    <label
      data-slot="amount-option"
      data-checked={checked || undefined}
      className={cn(
        "inline-flex cursor-pointer items-center justify-center border font-medium tabular-nums transition-colors duration-150 motion-reduce:transition-none",
        "has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring has-[:focus-visible]:ring-offset-2",
        size === "sm" ? "h-8 rounded-full px-3 text-sm" : "h-12 rounded-lg px-3 text-md",
        checked ? "border-primary bg-primary/10 text-foreground" : "border-border bg-background hover:bg-muted",
      )}
    >
      <input type="radio" name={name} className="sr-only" checked={checked} onChange={onChange} />
      {children}
    </label>
  );
}
