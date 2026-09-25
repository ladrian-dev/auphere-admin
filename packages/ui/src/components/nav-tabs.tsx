import type { ReactNode } from "react";

import { cn } from "../lib/utils";
import { NativeSelect } from "./native-select";
import { StatusDot } from "./status-dot";

/** Lo que una pestaña quiere señalar sin sacar al usuario de donde está. */
type NavTabMark = "draft" | "incident";

type NavTabItem = {
  /** Identidad estable de la pestaña; `current` se compara contra esto. */
  key: string;
  label: ReactNode;
  href: string;
  mark?: NavTabMark;
};

type NavTabGroup = {
  key: string;
  /** El rótulo del grupo: «Observar», «Configurar», «Conectar». */
  label: string;
  items: NavTabItem[];
};

type NavTabLinkProps = {
  href: string;
  className: string;
  children: ReactNode;
  "aria-current"?: "page";
};

type NavTabsProps = {
  groups: NavTabGroup[];
  /** La `key` de la pestaña actual. */
  current: string;
  ariaLabel: string;
  /** Por debajo del punto de ruptura, un `select` en vez de tres filas. */
  compact?: boolean;
  /** El router del consumidor: en la consola, el `Link` de Next. */
  renderLink?: (props: NavTabLinkProps) => ReactNode;
  /** Nombre accesible de cada marca; sin él, el punto es decorativo. */
  marks?: Partial<Record<NavTabMark, string>>;
  /** Sufijo del texto de la opción en modo compacto («Agente · sin publicar»). */
  markSuffix?: Partial<Record<NavTabMark, string>>;
  className?: string;
};

const MARK_TONE: Record<NavTabMark, "info" | "danger"> = { draft: "info", incident: "danger" };

/**
 * Las pestañas de la ficha de cliente (spec 017, R2): diez destinos que en
 * una fila plana no se pueden leer, agrupados en tres preguntas — qué está
 * pasando, cómo se configura, con qué se conecta.
 *
 * Un grupo que se queda sin pestañas (porque el rol no las ve) no deja el
 * rótulo huérfano: desaparece entero.
 */
function NavTabs({ groups, current, ariaLabel, compact, renderLink, marks, markSuffix, className }: NavTabsProps) {
  const visible = groups.filter((g) => g.items.length > 0);

  if (compact) {
    return (
      <NativeSelect aria-label={ariaLabel} defaultValue={current} wrapperClassName={cn("w-full", className)}>
        {visible.map((group) => (
          <optgroup key={group.key} label={group.label}>
            {group.items.map((item) => {
              const suffix = item.mark ? markSuffix?.[item.mark] : undefined;
              return (
                <option key={item.key} value={item.key}>
                  {typeof item.label === "string" ? item.label : item.key}
                  {suffix ? ` · ${suffix}` : ""}
                </option>
              );
            })}
          </optgroup>
        ))}
      </NativeSelect>
    );
  }

  return (
    <nav aria-label={ariaLabel} className={cn("flex flex-wrap gap-x-10 gap-y-2 border-b border-border", className)} data-slot="nav-tabs">
      {visible.map((group) => (
        <div key={group.key} className="flex flex-col gap-1">
          <span className="px-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">{group.label}</span>
          {/* El grupo envuelve: en una pantalla estrecha, una pestaña que se
              sale no tiene scroll con el que rescatarla. */}
          <ul className="flex flex-wrap gap-1">
            {group.items.map((item) => {
              const isCurrent = item.key === current;
              const linkClass = cn(
                "-mb-px inline-flex items-center gap-2 border-b-2 px-2 py-2 text-sm",
                isCurrent ? "border-foreground font-medium text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
              );
              const content = (
                <>
                  {item.label}
                  {item.mark ? <StatusDot tone={MARK_TONE[item.mark]} label={marks?.[item.mark]} /> : null}
                </>
              );
              const linkProps: NavTabLinkProps = {
                href: item.href,
                className: linkClass,
                children: content,
                ...(isCurrent ? { "aria-current": "page" as const } : {}),
              };
              return (
                <li key={item.key} className="inline-flex items-center">
                  {renderLink ? (
                    renderLink(linkProps)
                  ) : (
                    <a href={item.href} aria-current={isCurrent ? "page" : undefined} className={linkClass}>
                      {content}
                    </a>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

export { NavTabs, type NavTabGroup, type NavTabItem, type NavTabLinkProps, type NavTabMark, type NavTabsProps };
