/**
 * La búsqueda de acciones y objetos (⌘K) — spec 010, Requisito 1.8.
 *
 * Una sola, para todo: secciones, teammates y las órdenes del armazón. Y cada
 * acción **enseña su atajo**, que es como se aprenden — la alternativa es una
 * aplicación llena de atajos que sólo conoce quien los escribió.
 *
 * Se monta sobre el diálogo del sistema de diseño en vez de traer una librería:
 * `cmdk`, que es la que se usaría, lleva sin publicar desde marzo de 2025 y
 * arrastra otro juego de primitivas.
 */
import { useEffect, useMemo, useRef, useState } from "react";

import { useAppT } from "../i18n";

export type Command = {
  id: string;
  label: string;
  /** El grupo con el que se agrupa en la lista: secciones, teammates, acciones. */
  group: string;
  /** El atajo, si lo tiene. Se enseña para que se aprenda. */
  shortcut?: string;
  run: () => void;
};

export function Palette({
  open,
  commands,
  onClose,
}: {
  open: boolean;
  commands: readonly Command[];
  onClose: () => void;
}) {
  const t = useAppT();
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setCursor(0);
      input.current?.focus();
    }
  }, [open]);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter((c) => `${c.group} ${c.label}`.toLowerCase().includes(needle));
  }, [commands, query]);

  if (!open) return null;

  const run = (command: Command | undefined) => {
    if (!command) return;
    command.run();
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-background/80 pt-24"
      // Pulsar fuera cierra: es una búsqueda, no una decisión.
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div role="dialog" aria-modal="true" aria-label={t("shell.search")} className="w-full max-w-lg rounded-md border border-border bg-card shadow-2">
        <input
          ref={input}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setCursor(0);
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") onClose();
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setCursor((c) => Math.min(matches.length - 1, c + 1));
            }
            if (event.key === "ArrowUp") {
              event.preventDefault();
              setCursor((c) => Math.max(0, c - 1));
            }
            if (event.key === "Enter") {
              event.preventDefault();
              run(matches[cursor]);
            }
          }}
          placeholder={t("shell.search.placeholder")}
          aria-label={t("shell.search")}
          className="w-full border-b border-border bg-transparent px-4 py-3 text-base outline-none"
        />

        <ul className="max-h-80 overflow-y-auto p-1" role="listbox" aria-label={t("shell.search")}>
          {matches.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-muted-foreground">{t("shell.search.empty")}</li>
          ) : (
            matches.map((command, index) => (
              <li key={command.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={index === cursor}
                  onMouseEnter={() => setCursor(index)}
                  onClick={() => run(command)}
                  className="flex min-h-7 w-full items-center gap-3 rounded-sm px-3 text-left text-ui transition-colors aria-[selected=true]:bg-muted"
                >
                  <span className="shrink-0 text-xs text-muted-foreground">{command.group}</span>
                  <span className="min-w-0 flex-1 truncate">{command.label}</span>
                  {command.shortcut ? <kbd className="shrink-0 font-mono text-xs text-muted-foreground">{command.shortcut}</kbd> : null}
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
