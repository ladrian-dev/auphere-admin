import { cn } from "@/lib/utils";

/**
 * Editorial text wordmark for the panel.
 *
 * Brand-system explicitly deprecates the existing wordmark-a/b SVGs
 * (legacy gold accent system). Until the type designer ships the final
 * type-set wordmark in Phase 2/3, we render lowercase "auphere" in
 * Inter Tight semibold with tight tracking — quiet, editorial, ages
 * gracefully when the proper mark lands.
 *
 * Variant ``compact`` (the dot prefix) reads as a built-in mark: a
 * single mountain-meadow square aligned to the wordmark's x-height.
 * It's the only "logo" we draw in code; full lockup waits for type.
 */
export function Wordmark({
  className,
  variant = "compact",
}: {
  className?: string;
  variant?: "compact" | "plain";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-baseline gap-2 select-none",
        className,
      )}
      aria-label="auphere"
    >
      {variant === "compact" ? (
        <span
          aria-hidden="true"
          className="block size-2 translate-y-[1px] rounded-[2px] bg-[color:var(--color-primary-deep)]"
        />
      ) : null}
      <span
        className="text-base font-semibold lowercase"
        style={{ letterSpacing: "var(--tracking-tight)" }}
      >
        auphere
      </span>
      <span
        aria-hidden="true"
        className="font-mono text-[11px] uppercase text-muted-foreground"
        style={{ letterSpacing: "var(--tracking-eyebrow)" }}
      >
        nexus
      </span>
    </span>
  );
}
