import { CardSkeleton, HeaderSkeleton } from "@nexus/ui";

/**
 * The plain page skeleton of the console: a header and three cards. The
 * partner's pages that have no skeleton of their own load with it (and,
 * since spec 045, the client's pages that have none either).
 */
export function PageSkeleton({ label }: { label: string }) {
  return (
    <>
      <HeaderSkeleton label={label} />
      <div className="grid gap-4 md:grid-cols-3">
        <CardSkeleton label={label} />
        <CardSkeleton label={label} />
        <CardSkeleton label={label} />
      </div>
    </>
  );
}
