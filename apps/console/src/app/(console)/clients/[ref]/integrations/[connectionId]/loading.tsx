import { Skeleton } from "@nexus/ui";

/** Cargando la página de un conector (spec 047, historia 21): la cabecera y sus dos secciones con su tamaño final. */
export default function ConnectionLoading() {
  return (
    <div className="grid min-w-0 gap-6" aria-busy="true">
      <Skeleton className="h-5 w-40 max-w-full" />
      <div className="flex items-center gap-3">
        <Skeleton className="size-10" />
        <Skeleton className="h-7 w-56 max-w-full" />
      </div>
      <Skeleton className="h-36 w-full" />
      <Skeleton className="h-48 w-full" />
    </div>
  );
}
