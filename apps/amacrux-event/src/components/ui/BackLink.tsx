"use client";

import { useRouter } from "next/navigation";

import { ArrowLeftIcon } from "./icons";

/** Vuelve a la página anterior; si no hay historial (llegó por enlace directo), va al inicio. */
export function BackLink({ label = "Volver" }: { label?: string }) {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={() => {
        if (window.history.length > 1) router.back();
        else router.push("/");
      }}
      className="inline-flex h-11 items-center gap-2 rounded-md px-2 font-display font-semibold text-ink hover:bg-surface"
    >
      <ArrowLeftIcon size={20} />
      {label}
    </button>
  );
}
