import { Skeleton } from "@nexus/ui";

/** Cargando la página de un canal (spec 047, historia 11): la cabecera y sus secciones con su tamaño final. */
export default function ChannelConfigLoading() {
  return (
    <div className="grid min-w-0 gap-6" aria-busy="true">
      <div className="grid gap-2">
        <Skeleton className="h-7 w-56 max-w-full" />
        <Skeleton className="h-5 w-40 max-w-full" />
      </div>
      {Array.from({ length: 4 }, (_, i) => (
        <Skeleton key={i} className="h-36 w-full" />
      ))}
    </div>
  );
}
