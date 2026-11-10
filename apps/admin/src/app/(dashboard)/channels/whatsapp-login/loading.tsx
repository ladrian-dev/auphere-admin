import { CardSkeleton, HeaderSkeleton, TableSkeleton } from "@/components/skeletons/list-skeleton";

export default function WhatsappLoginBetaLoading() {
  return (
    <>
      <HeaderSkeleton />
      <TableSkeleton rows={3} columns={4} />
      <CardSkeleton lines={3} />
    </>
  );
}
