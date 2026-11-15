import { HeaderSkeleton, Skeleton } from "@nexus/ui";
import { ROUTER_PANEL_VISIBLE } from "@/lib/router-panel";

import { DeploymentsTableSkeleton } from "./deployments-table";

/**
 * The page as it will be drawn: the header, the bar of states (36 px, one
 * row from `sm`) and the table with its own columns and rows of a model's
 * height — not a generic grid that jumps when the catalog arrives.
 */
export default function ModelsLoading() {
  return (
    <>
      <HeaderSkeleton label="Cargando" />
      <Skeleton className="h-9 w-full sm:w-md" />
      <DeploymentsTableSkeleton routerVisible={ROUTER_PANEL_VISIBLE} />
    </>
  );
}
