import { useEffect, useRef, type ReactNode } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { cn } from "../ui/cn";
import { Truncate } from "../ui/truncate";
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
  /** Tailwind min-width class for the desktop table (default min-w-[44rem]). */
  minWidth?: string;
}

export function VirtualTable<T>({
  rows,
  columns,
  rowHeight = 56,
  onEndReached,
  getRowId,
  onRowClick,
  empty,
  label = "Table",
  minWidth = "min-w-[44rem]",
}: Props<T>) {
  const mobile = useMediaQuery("(max-width: 767px)");
  const scrollRef = useRef<HTMLDivElement>(null);
  const cardH = mobile ? Math.max(rowHeight, 140) : rowHeight;
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
  const endRef = useRef(onEndReached);
  useEffect(() => {
    endRef.current = onEndReached;
  });
  useEffect(() => {
    if (rows.length > 0 && last >= rows.length - 20) endRef.current?.();
  }, [last, rows.length]);

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

  const cell = (c: Column<T>, r: T) => {
    const v = c.cell(r);
    return typeof v === "string" || typeof v === "number" ? <Truncate>{v}</Truncate> : v;
  };

  return (
    <div className={cn("overflow-x-auto", !mobile && "rounded-xl border bg-card")}>
      <div role="table" aria-label={label} aria-rowcount={mobile ? rows.length : rows.length + 1} className={cn("flex min-h-0 flex-col", !mobile && minWidth)}>
        <div ref={scrollRef} role="rowgroup" className="min-h-0 flex-1 overflow-y-auto max-h-[calc(100dvh-14rem)]">
          {!mobile && (
            <div role="rowgroup" className="sticky top-0 z-10 border-b bg-muted">
              <div role="row" className="grid gap-3 px-4 py-3 text-xs font-medium text-muted-foreground" style={{ gridTemplateColumns: template }}>
                {cols.map((c) => (
                  <div key={c.id} role="columnheader" className="min-w-0 truncate">
                    {c.header}
                  </div>
                ))}
              </div>
            </div>
          )}
          <div style={{ height: v.getTotalSize(), position: "relative" }}>
            {items.map((vi) => {
              const r = rows[vi.index];
              if (r === undefined) return null;
              const pos = { position: "absolute", top: 0, left: 0, width: "100%", transform: `translateY(${vi.start}px)` } as const;
              return mobile ? (
                <div key={getRowId(r)} role="row" aria-rowindex={vi.index + 1} data-index={vi.index} ref={v.measureElement} style={pos} className="pb-3">
                  <div
                    className={cn("flex flex-col gap-2 rounded-lg border bg-background p-4 text-sm", onRowClick && "cursor-pointer focus-visible:outline-2 focus-visible:outline-ring")}
                    {...clickable(r)}
                  >
                    {cols.map((c) => (
                      <div key={c.id} role="cell" className="flex min-w-0 items-center justify-between gap-3">
                        <span className="shrink-0 text-muted-foreground">{c.header}</span>
                        <span className="min-w-0 text-right">{cell(c, r)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div
                  key={getRowId(r)}
                  role="row"
                  aria-rowindex={vi.index + 2}
                  data-index={vi.index}
                  ref={v.measureElement}
                  style={{ ...pos, gridTemplateColumns: template }}
                  className={cn("grid min-h-14 items-center gap-3 border-b px-4 py-2 text-sm hover:bg-accent/50", onRowClick && "cursor-pointer focus-visible:outline-2 focus-visible:outline-ring")}
                  {...clickable(r)}
                >
                  {cols.map((c) => (
                    <div key={c.id} role="cell" className="min-w-0">
                      {cell(c, r)}
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
