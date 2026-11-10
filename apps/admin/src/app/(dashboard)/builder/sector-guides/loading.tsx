import { HeaderSkeleton } from "@/components/skeletons/list-skeleton";

import { SectorGuidesSkeleton } from "./skeletons";

export default function SectorGuidesLoading() {
  return (
    <>
      <HeaderSkeleton />
      <SectorGuidesSkeleton />
    </>
  );
}
