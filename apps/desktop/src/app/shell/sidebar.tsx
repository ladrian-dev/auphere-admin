/**
 * La lista lateral — spec 010, Requisitos 1.2 y 1.4.
 *
 * **Una sola navegación.** Arriba lo que se opera, abajo lo que se administra
 * —que son las mismas secciones que la consola ya ofrece, con sus mismos
 * permisos— y al pie quién eres, tu plan y tu máquina.
 *
 * Lo que esta lista arregla, y que costaba entender antes: las secciones de
 * administrar dejan de vivir en otra superficie a la que se llegaba por el menú
 * Ver. Aquí son entradas como las demás, y la consola se pinta en el panel.
 *
 * Una sección que el rol de la persona no permite **no se ofrece**: no hay
 * entrada apagada esperando un clic que dará un «no puedes» (§V).
 */
import {
  BarChart3,
  Bell,
  BookOpen,
  Building2,
  Home,
  Inbox,
  KeyRound,
  Laptop,
  type LucideIcon,
  Receipt,
  ScrollText,
  Sun,
  Users,
} from "lucide-react";

import { Skeleton } from "@nexus/ui";

import { type MyState, isIdle } from "../../app-state";
import { CONSOLE_SECTIONS, type Section } from "../../sections";
import { useAppT } from "../i18n";

/**
 * Un icono por sección, y los mismos que usa la consola para las suyas: dentro
 * de la misma ventana, «Clientes» no puede ser un edificio en un sitio y otra
 * cosa en el otro.
 */
const ICONS: Record<string, LucideIcon> = {
  hoy: Sun,
  pendientes: Inbox,
  inicio: Home,
  clientes: Building2,
  conocimiento: BookOpen,
  puesto: Laptop,
  consumo: BarChart3,
  auditoria: ScrollText,
  notificaciones: Bell,
  equipo: Users,
  claves: KeyRound,
  facturacion: Receipt,
};

export type SidebarProps = {
  active: Section;
  onSelect: (section: Section) => void;
  /** Los permisos de la consola que tiene esta persona. */
  permissions: readonly string[];
  /** Cuántas decisiones esperan. Sale del derivado único (R5.4). */
  waiting: number;
  /** Los teammates, para navegar a su hilo sin pasar por una lista intermedia. */
  teammates: ReadonlyArray<{ id: string; name: string; unread: boolean; state?: MyState }>;
  /**
   * En qué punto está esa lista — spec 010, R4.1.
   *
   * El 2026-09-17, con la aplicación instalada, el equipo tardaba en llegar y
   * esta lista no enseñaba **nada**: exactamente lo mismo que enseña cuando de
   * verdad no tienes teammates. Cargando y vacío no pueden verse igual.
   */
  rosterStatus?: "loading" | "ready" | "empty" | "error";
  selectedTeammate: string | null;
  onSelectTeammate: (id: string) => void;
  onCreateTeammate?: () => void;
  onRetryRoster?: () => void;
  /** El pie: identidad, plan y máquina. Lo compone quien tiene esos datos. */
  footer?: React.ReactNode;
};

export function Sidebar({
  active,
  onSelect,
  permissions,
  waiting,
  teammates,
  rosterStatus,
  selectedTeammate,
  onSelectTeammate,
  onCreateTeammate,
  onRetryRoster,
  footer,
}: SidebarProps) {
  const t = useAppT();
  const roster = rosterStatus ?? (teammates.length > 0 ? "ready" : "empty");
  const manage = CONSOLE_SECTIONS.filter((s) => s.permission === null || permissions.includes(s.permission));

  return (
    <nav className="flex h-full min-w-0 flex-col border-r border-border bg-sidebar" aria-label={t("shell.sidebar.operate")}>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        <Group label={t("shell.sidebar.operate")}>
          <Item label={t("shell.today")} icon={ICONS.hoy} active={active === "hoy"} onSelect={() => onSelect("hoy")} />
          <Item
            label={t("shell.pending")}
            icon={ICONS.pendientes}
            active={active === "pendientes"}
            onSelect={() => onSelect("pendientes")}
            badge={waiting}
          />
        </Group>

        <Group label={t("shell.teammates")}>
          {roster === "loading" ? (
            <li role="status" aria-busy="true" className="flex flex-col gap-1 px-2 py-1">
              <span className="sr-only">{t("roster.loading")}</span>
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-4 w-full" />
              ))}
            </li>
          ) : roster === "error" ? (
            <li className="flex flex-col items-start gap-1 px-2 py-1">
              <p className="text-xs text-pretty text-muted-foreground">{t("roster.error")}</p>
              <button
                type="button"
                onClick={onRetryRoster}
                className="min-h-6 rounded-sm text-xs font-medium text-primary underline-offset-2 hover:underline"
              >
                {t("roster.retry")}
              </button>
            </li>
          ) : roster === "empty" ? (
            /* Un hueco no dice nada. Aquí vive el primer paso, donde se mira. */
            <li className="flex flex-col items-start gap-1 px-2 py-1">
              <p className="text-xs text-pretty text-muted-foreground">{t("shell.teammates.empty")}</p>
              <button
                type="button"
                onClick={onCreateTeammate}
                className="min-h-6 rounded-sm text-xs font-medium text-primary underline-offset-2 hover:underline"
              >
                {t("roster.create")}
              </button>
            </li>
          ) : (
            teammates.map((teammate) => (
              <Item
                key={teammate.id}
                label={teammate.name}
                active={active === "teammate" && selectedTeammate === teammate.id}
                onSelect={() => onSelectTeammate(teammate.id)}
                dot={teammate.unread}
                /* R4.7: una espera se dice con palabras. El ocio no se dice —
                   la ausencia se diseña—, y así lo que sí se dice se lee. */
                note={
                  teammate.state && !isIdle(teammate.state) ? t(`state.${teammate.state}`) : undefined
                }
              />
            ))
          )}
        </Group>

        <Group label={t("shell.sidebar.manage")}>
          {manage.map((section) => (
            <Item
              key={section.key}
              label={t(`shell.section.${section.key}`)}
              icon={ICONS[section.key]}
              active={active === section.key}
              onSelect={() => onSelect(section.key)}
            />
          ))}
        </Group>
      </div>

      {footer ? <div className="shrink-0 border-t border-border p-2">{footer}</div> : null}
    </nav>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-3">
      <h2 className="px-2 py-1 text-xs font-medium tracking-wide text-muted-foreground uppercase">{label}</h2>
      <ul className="flex flex-col">{children}</ul>
    </div>
  );
}

function Item({
  label,
  active,
  onSelect,
  badge,
  dot,
  note,
  icon: Icon,
}: {
  label: string;
  active: boolean;
  onSelect: () => void;
  badge?: number;
  dot?: boolean;
  /** Lo que está esperando, en palabras. Nunca sólo un color (WCAG 1.4.1). */
  note?: string;
  icon?: LucideIcon;
}) {
  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={active ? "page" : undefined}
        className="flex min-h-7 w-full items-center gap-2 rounded-sm px-2 text-left text-ui transition-colors hover:bg-muted aria-[current=page]:bg-muted aria-[current=page]:font-medium"
      >
        {Icon ? <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" /> : null}
        <span className="min-w-0 flex-1 truncate">{label}</span>
        {note ? <span className="shrink-0 truncate text-xs text-muted-foreground">{note}</span> : null}
        {dot ? <span className="size-2 shrink-0 rounded-full bg-primary" aria-hidden="true" /> : null}
        {badge !== undefined && badge > 0 ? (
          <span className="shrink-0 rounded-full bg-primary px-2 text-xs tabular-nums text-primary-foreground">{badge}</span>
        ) : null}
      </button>
    </li>
  );
}
