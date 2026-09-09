import { CardSkeleton, Skeleton } from "@nexus/ui";

/** El esqueleto imita las dos tarjetas reales: lista blanca arriba, máquinas
 *  abajo. Mismas alturas para que nada salte al llegar los datos. */
export default function Loading() {
  return (
    <div className="flex flex-col gap-6" aria-busy="true">
      <Skeleton className="h-8 w-48" />
      <CardSkeleton lines={4} />
      <CardSkeleton lines={2} />
    </div>
  );
}
