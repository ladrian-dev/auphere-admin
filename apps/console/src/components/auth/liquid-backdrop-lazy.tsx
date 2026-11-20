"use client";

import dynamic from "next/dynamic";

/**
 * El líquido, cargado después de pintar (spec 066, R2.8). El servidor no lo
 * pinta (`ssr: false`): mientras llega, se ve el respaldo CSS del panel, que
 * tiene los mismos verdes y el mismo tamaño, así que nada se mueve de sitio.
 */
export const LiquidBackdropLazy = dynamic(() => import("./liquid-backdrop").then((m) => m.LiquidBackdrop), {
  ssr: false,
  loading: () => null,
});
