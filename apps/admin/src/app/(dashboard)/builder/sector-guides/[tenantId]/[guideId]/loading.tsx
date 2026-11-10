import { HeaderSkeleton } from "@/components/skeletons/list-skeleton";

import { GeneratedGuideSkeleton } from "../../skeletons";

export default function GeneratedGuideLoading() {
  return (
    <>
      <HeaderSkeleton />
      <GeneratedGuideSkeleton />
    </>
  );
}
