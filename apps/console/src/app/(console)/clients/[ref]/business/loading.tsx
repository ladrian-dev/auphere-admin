import { Skeleton } from "@nexus/ui";

/**
 * Cargando Negocio (spec 047, T060): el índice y las cinco secciones con su
 * tamaño final, para que nada salte cuando llegan los datos.
 */
export default function BusinessLoading() {
  return (
    <div className="grid min-w-0 gap-6 lg:grid-cols-[13rem_minmax(0,1fr)]" aria-busy="true">
      <div className="hidden gap-2 lg:grid">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
      <div className="grid min-w-0 gap-6">
        <Skeleton className="h-5 w-2/3 max-w-prose" />
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-48 w-full rounded-md" />
        ))}
      </div>
    </div>
  );
}
