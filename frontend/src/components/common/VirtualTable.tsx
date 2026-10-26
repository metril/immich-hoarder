import { useEffect, useRef, type ReactNode } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { cn } from "../../lib/utils";
import { useMediaQuery } from "./useMediaQuery";

export interface Column<T> {
  id: string;
  header: string;
  cell: (r: T) => ReactNode;
  width?: string;
  hideBelow?: "md";
}

interface Props<T> {
  rows: T[];
  columns: Column<T>[];
  rowHeight?: number;
  onEndReached?: () => void;
  getRowId: (r: T) => string | number;
  onRowClick?: (r: T) => void;
  empty?: ReactNode;
  label?: string;
}

export function VirtualTable<T>({
  rows,
  columns,
  rowHeight = 44,
  onEndReached,
  getRowId,
  onRowClick,
  empty,
  label = "Table",
}: Props<T>) {
  const mobile = useMediaQuery("(max-width: 767px)");
  const scrollRef = useRef<HTMLDivElement>(null);
  const cardH = mobile ? Math.max(rowHeight, 96) : rowHeight;
  // eslint-disable-next-line react-hooks/incompatible-library
  const v = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => cardH,
    overscan: 10,
    initialRect: { width: 1024, height: 800 },
  });
  const items = v.getVirtualItems();
  const last = items.at(-1)?.index ?? -1;
  useEffect(() => {
    if (onEndReached && rows.length > 0 && last >= rows.length - 20) onEndReached();
  }, [last, rows.length, onEndReached]);

  if (rows.length === 0 && empty) return <>{empty}</>;

  const cols = columns.filter((c) => !c.hideBelow || !mobile);
  const template = cols.map((c) => c.width ?? "minmax(0,1fr)").join(" ");
  const clickable = (r: T) =>
    onRowClick
      ? {
          onClick: () => onRowClick(r),
          onKeyDown: (e: React.KeyboardEvent) => {
            if (e.key === "Enter") onRowClick(r);
          },
          tabIndex: 0,
        }
      : {};

  return (
    <div role="table" aria-label={label} aria-rowcount={rows.length + 1} className="flex h-full min-h-0 flex-col rounded-md border">
      {!mobile && (
        <div role="rowgroup" className="sticky top-0 z-10 border-b bg-muted">
          <div role="row" className="grid px-3 py-2 text-xs font-medium text-muted-foreground" style={{ gridTemplateColumns: template }}>
            {cols.map((c) => (
              <div key={c.id} role="columnheader">
                {c.header}
              </div>
            ))}
          </div>
        </div>
      )}
      <div ref={scrollRef} role="rowgroup" className="min-h-0 flex-1 overflow-auto" style={{ maxHeight: "70vh" }}>
        <div style={{ height: v.getTotalSize(), position: "relative" }}>
          {items.map((vi) => {
            const r = rows[vi.index];
            if (r === undefined) return null;
            const pos = { position: "absolute", top: 0, left: 0, width: "100%", height: vi.size, transform: `translateY(${vi.start}px)` } as const;
            return mobile ? (
              <div key={getRowId(r)} role="row" aria-rowindex={vi.index + 2} style={pos} className="p-1">
                <div
                  className={cn("flex h-full flex-col gap-1 overflow-hidden rounded-md border bg-card p-3 text-sm", onRowClick && "cursor-pointer focus-visible:outline-2 focus-visible:outline-ring")}
                  {...clickable(r)}
                >
                  {cols.map((c) => (
                    <div key={c.id} role="cell" className="flex justify-between gap-2">
                      <span className="text-muted-foreground">{c.header}</span>
                      <span className="min-w-0 truncate">{c.cell(r)}</span>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div
                key={getRowId(r)}
                role="row"
                aria-rowindex={vi.index + 2}
                style={{ ...pos, gridTemplateColumns: template }}
                className={cn("grid items-center border-b px-3 text-sm hover:bg-accent/50", onRowClick && "cursor-pointer focus-visible:outline-2 focus-visible:outline-ring")}
                {...clickable(r)}
              >
                {cols.map((c) => (
                  <div key={c.id} role="cell" className="min-w-0 truncate">
                    {c.cell(r)}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
