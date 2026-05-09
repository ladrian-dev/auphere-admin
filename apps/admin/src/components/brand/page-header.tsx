import { cn } from "@/lib/utils";
import { Eyebrow } from "./eyebrow";

/**
 * Page header — editorial layout the rest of the panel inherits.
 *
 * Density rules:
 *  - Title is display weight, ``--text-2xl`` mobile and ``--text-3xl``
 *    on tablet+. Tracking ``--tracking-tight``. Never larger; this is
 *    ops UI, not a hero.
 *  - Eyebrow lives above the title with the section index. It carries
 *    the brand's mono uppercase voice without needing illustrations.
 *  - Right-aligned actions slot stays vertically centred to the title;
 *    keep it to 1–2 buttons max.
 */
export function PageHeader({
  eyebrow,
  eyebrowIndex,
  title,
  description,
  actions,
  className,
}: {
  eyebrow?: string;
  eyebrowIndex?: string;
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <header
      className={cn(
        "flex flex-col gap-3 border-b border-border pb-6 md:flex-row md:items-end md:justify-between",
        className,
      )}
    >
      <div className="flex flex-col gap-2">
        {eyebrow ? (
          <Eyebrow index={eyebrowIndex}>{eyebrow}</Eyebrow>
        ) : null}
        <h1
          className="text-2xl md:text-3xl font-semibold leading-tight"
          style={{ letterSpacing: "var(--tracking-tight)" }}
        >
          {title}
        </h1>
        {description ? (
          <p className="text-muted-foreground text-base max-w-prose">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex items-center gap-2 shrink-0">{actions}</div>
      ) : null}
    </header>
  );
}
