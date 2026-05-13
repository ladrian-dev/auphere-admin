"use client";

/**
 * Block Q — "Insertar patrón" button next to the prompt textarea.
 *
 * Opens a dialog with curated snippets filtered by the tenant's
 * vertical (when known). Clicking a snippet appends its body to the
 * current prompt — the operator reviews and edits before saving. NO
 * placeholder substitution happens here; snippets carry
 * ``{policies.cancellation.…}`` style tokens that the operator fills
 * by hand or via the improve-prompt pass.
 *
 * Snippets are fetched client-side on dialog open (no SSR overhead
 * for users who never click the button).
 */

import { BookOpen, Plus, Search } from "lucide-react";
import { useState, useTransition } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { backend, type PromptSnippet, type PromptSnippetCategory } from "@/lib/backend";

const CATEGORIES: Array<{ value: PromptSnippetCategory; label: string }> = [
  { value: "tone", label: "Tono" },
  { value: "edge_case", label: "Edge case" },
  { value: "escalation", label: "Escalation" },
  { value: "output_format", label: "Output" },
  { value: "tool_calling", label: "Tool calling" },
  { value: "policy", label: "Política" },
];

export function InsertPatternButton({
  vertical,
  onInsert,
}: {
  /** Vertical of the current draft so we filter snippets meaningfully.
   *  Pass ``null`` when no seed is applied yet — we show all snippets. */
  vertical: string | null;
  onInsert: (snippetBody: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [pending, start] = useTransition();
  const [snippets, setSnippets] = useState<PromptSnippet[] | null>(null);
  const [category, setCategory] = useState<PromptSnippetCategory | null>(null);
  const [filterQuery, setFilterQuery] = useState("");

  function onOpenChange(next: boolean) {
    if (pending) return;
    setOpen(next);
    if (next && snippets === null) {
      start(async () => {
        try {
          const data = await backend.listPromptLibrary({
            vertical: vertical ?? undefined,
          });
          setSnippets(data);
        } catch (err) {
          toast.error(
            `No se pudieron cargar patrones: ${err instanceof Error ? err.message : String(err)}`,
          );
          setSnippets([]);
        }
      });
    }
    if (!next) {
      setCategory(null);
      setFilterQuery("");
    }
  }

  function onPick(snippet: PromptSnippet) {
    onInsert(snippet.body);
    toast.success(`Patrón "${snippet.title}" agregado`, {
      description: "Revisalo en el textarea y rellená los placeholders.",
    });
    onOpenChange(false);
  }

  const filtered = (snippets ?? []).filter((s) => {
    if (category && s.category !== category) return false;
    if (filterQuery.trim()) {
      const q = filterQuery.toLowerCase();
      return (
        s.title.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q) ||
        s.tags.some((t) => t.toLowerCase().includes(q))
      );
    }
    return true;
  });

  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onOpenChange(true)}
        className="inline-flex items-center gap-1.5"
      >
        <BookOpen className="size-3.5" />
        Insertar patrón
      </Button>

      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-w-3xl">
          <DialogHeader>
            <DialogTitle className="inline-flex items-center gap-2">
              <BookOpen className="size-4" /> Prompt library
            </DialogTitle>
            <DialogDescription>
              Patrones curados por Auphere. Click en uno para agregarlo al
              final del prompt actual. Después rellená los
              <code className="mx-1 font-mono">{"{placeholders}"}</code>
              {vertical ? (
                <>
                  {" · "}filtrados para{" "}
                  <Badge variant="outline" className="font-mono">
                    {vertical}
                  </Badge>
                </>
              ) : null}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Search className="size-3.5 text-muted-foreground" />
              <Input
                value={filterQuery}
                onChange={(e) => setFilterQuery(e.target.value)}
                placeholder="Buscar por título, tag…"
                className="flex-1 min-w-[200px]"
              />
              <button
                type="button"
                onClick={() => setCategory(null)}
                className={
                  "rounded-full border px-3 py-1 text-xs " +
                  (category === null
                    ? "border-foreground bg-foreground text-background"
                    : "border-border bg-transparent text-muted-foreground hover:text-foreground")
                }
              >
                Todas
              </button>
              {CATEGORIES.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  onClick={() =>
                    setCategory((prev) => (prev === c.value ? null : c.value))
                  }
                  className={
                    "rounded-full border px-3 py-1 text-xs " +
                    (category === c.value
                      ? "border-foreground bg-foreground text-background"
                      : "border-border bg-transparent text-muted-foreground hover:text-foreground")
                  }
                >
                  {c.label}
                </button>
              ))}
            </div>

            <div className="grid gap-2 max-h-[55vh] overflow-y-auto pr-1">
              {pending && snippets === null ? (
                <div className="rounded-md border border-dashed border-border bg-muted/30 px-4 py-8 text-center text-sm text-muted-foreground">
                  Cargando…
                </div>
              ) : filtered.length === 0 ? (
                <div className="rounded-md border border-dashed border-border bg-muted/30 px-4 py-8 text-center text-sm text-muted-foreground">
                  Sin patrones para el filtro actual.
                </div>
              ) : (
                filtered.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    onClick={() => onPick(s)}
                    className="text-left rounded-md border border-border bg-card px-3 py-2 hover:border-foreground/40 transition-colors grid gap-1"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium">{s.title}</span>
                      <div className="flex items-center gap-1 shrink-0">
                        <Badge variant="outline" className="text-[10px] uppercase">
                          {s.category}
                        </Badge>
                        <Plus className="size-3.5 text-muted-foreground" />
                      </div>
                    </div>
                    {s.description ? (
                      <p className="text-xs text-muted-foreground line-clamp-2">
                        {s.description}
                      </p>
                    ) : null}
                    {s.tags.length > 0 ? (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {s.tags.map((t) => (
                          <span
                            key={t}
                            className="text-[10px] font-mono text-muted-foreground"
                          >
                            #{t}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </button>
                ))
              )}
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
              disabled={pending}
            >
              Cerrar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
