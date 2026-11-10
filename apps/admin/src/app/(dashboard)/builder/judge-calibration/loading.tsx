import { CardSkeleton, HeaderSkeleton, TableSkeleton } from "@/components/skeletons/list-skeleton";

export default function JudgeCalibrationLoading() {
  return (
    <>
      <HeaderSkeleton />
      <CardSkeleton lines={2} />
      <TableSkeleton rows={8} columns={5} />
    </>
  );
}
