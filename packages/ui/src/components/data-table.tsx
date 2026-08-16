"use client";

import {
  type ColumnDef,
  type Row,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";
import * as React from "react";

import { cn } from "../lib/utils";
import { EmptyState } from "./empty-state";
import { ErrorState } from "./error-state";
import { TableSkeleton } from "./skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "./table";

type DataTableProps<TData, TValue> = {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  /** Five states — the table renders the right one, callers never branch. */
  loading?: boolean;
  error?: React.ReactNode;
  onRetry?: () => void;
  empty?: React.ReactNode;
  /** Rows are links/buttons: the whole row is the target. */
  onRowClick?: (row: Row<TData>) => void;
  rowHref?: (row: Row<TData>) => string | undefined;
  /** Client-side sorting (server-side lists pass sorted data and omit). */
  sortable?: boolean;
  initialSorting?: SortingState;
  /** aria-label for the table. */
  label?: string;
  className?: string;
  /** Column count hint for the skeleton before columns resolve. */
  skeletonRows?: number;
};

/**
 * The one DataTable (TanStack Table v8). Lives inside its own
 * ``overflow-x:auto`` container so the page body never scrolls
 * horizontally; every cell truncates with a ``title``; numeric cells are
 * ``tabular-nums`` (callers add ``text-right`` via ``meta.align``).
 */
function DataTable<TData, TValue>({
  columns,
  data,
  loading,
  error,
  onRetry,
  empty,
  onRowClick,
  rowHref,
  sortable,
  initialSorting = [],
  label,
  className,
  skeletonRows = 6,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = React.useState<SortingState>(initialSorting);
  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: sortable ? getSortedRowModel() : undefined,
    enableSorting: !!sortable,
  });

  if (loading) {
    return <TableSkeleton rows={skeletonRows} columns={Math.max(columns.length, 1)} className={className} />;
  }
  if (error) {
    return <ErrorState title={error} onRetry={onRetry} className={className} />;
  }
  if (data.length === 0) {
    return empty ?? <EmptyState title="Nothing here yet" readonly className={className} />;
  }

  return (
    <div data-slot="data-table" className={cn("min-w-0 rounded-md ring-1 ring-foreground/10", className)}>
      <Table aria-label={label}>
        <TableHeader>
          {table.getHeaderGroups().map((hg) => (
            <TableRow key={hg.id}>
              {hg.headers.map((header) => {
                const align = (header.column.columnDef.meta as { align?: "right" } | undefined)?.align;
                const canSort = sortable && header.column.getCanSort();
                const dir = header.column.getIsSorted();
                return (
                  <TableHead key={header.id} className={cn(align === "right" && "text-right")} aria-sort={dir === "asc" ? "ascending" : dir === "desc" ? "descending" : undefined}>
                    {header.isPlaceholder ? null : canSort ? (
                      <button
                        type="button"
                        className="inline-flex items-center gap-1 rounded-sm font-medium hover:text-foreground"
                        onClick={header.column.getToggleSortingHandler()}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {dir === "asc" ? (
                          <ArrowUp className="size-3" aria-hidden="true" />
                        ) : dir === "desc" ? (
                          <ArrowDown className="size-3" aria-hidden="true" />
                        ) : (
                          <ArrowUpDown className="size-3 opacity-50" aria-hidden="true" />
                        )}
                      </button>
                    ) : (
                      flexRender(header.column.columnDef.header, header.getContext())
                    )}
                  </TableHead>
                );
              })}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows.map((row) => {
            const href = rowHref?.(row);
            const interactive = !!onRowClick || !!href;
            return (
              <TableRow
                key={row.id}
                data-interactive={interactive || undefined}
                className={cn(interactive && "cursor-pointer")}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={
                  onRowClick
                    ? (e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onRowClick(row);
                        }
                      }
                    : undefined
                }
                tabIndex={onRowClick ? 0 : undefined}
              >
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta as { align?: "right"; truncate?: boolean } | undefined;
                  const raw = cell.getValue();
                  return (
                    <TableCell
                      key={cell.id}
                      className={cn("max-w-64 min-w-0", meta?.align === "right" && "text-right tabular-nums")}
                    >
                      <div
                        className={cn(meta?.truncate !== false && "truncate")}
                        title={meta?.truncate !== false && typeof raw === "string" ? raw : undefined}
                      >
                        {href && cell.column.getIndex() === 0 ? (
                          <a href={href} className="after:absolute after:inset-0 focus-visible:outline-none">
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                          </a>
                        ) : (
                          flexRender(cell.column.columnDef.cell, cell.getContext())
                        )}
                      </div>
                    </TableCell>
                  );
                })}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}

export { DataTable, type DataTableProps };
export type { ColumnDef, Row, SortingState } from "@tanstack/react-table";
