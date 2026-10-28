import { Skeleton } from "@nexus/ui";

/**
 * Cargando la pantalla del agente (spec 047, historia 7): la cabecera, los
 * bloques y las propuestas con su tamaño final, para que nada salte.
 */
export default function AgentScreenLoading() {
  return (
    <div className="grid min-w-0 gap-6" aria-busy="true">
      <div className="grid gap-2">
        <Skeleton className="h-7 w-48" />
        <Skeleton className="h-6 w-72 max-w-full" />
      </div>
      <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
        <div className="grid min-w-0 gap-4">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-32 w-full" />
          ))}
        </div>
        <Skeleton className="hidden h-48 w-full lg:block" />
      </div>
    </div>
  );
}
