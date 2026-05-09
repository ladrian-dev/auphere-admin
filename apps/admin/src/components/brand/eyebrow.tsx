import { cn } from "@/lib/utils";

/**
 * Editorial eyebrow — the small uppercase mono label above section
 * headers ("01 — TENANTS", "02 — INTEGRATIONS"). Direct translation of
 * the brand's "tracked uppercase" pattern from the website hero.
 *
 * Use sparingly: at most one per page section. The signal degrades the
 * moment every block has one.
 */
export function Eyebrow({
  index,
  children,
  className,
}: {
  index?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "font-mono text-xs uppercase text-muted-foreground",
        className,
      )}
      style={{ letterSpacing: "var(--tracking-eyebrow)" }}
    >
      {index ? <span aria-hidden="true">{index} — </span> : null}
      {children}
    </span>
  );
}
