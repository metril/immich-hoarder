import { useState } from "react";
import { useQueryClient, type InfiniteData } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Command } from "cmdk";
import type { MeOut } from "../../api/me";
import { navFor } from "./nav";
import { useSignOut } from "./session";
import { useTheme } from "./theme";

type Row = { id: number; name?: string | null };

const itemCls = "flex cursor-pointer items-center justify-between rounded-sm px-2 py-1.5 text-sm aria-selected:bg-accent";
const groupCls = "px-1 py-1 text-xs text-muted-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1";

/** Lazy chunk (cmdk): loaded on first open only. */
export default function CommandPalette({ open, onOpenChange, me }: { open: boolean; onOpenChange: (o: boolean) => void; me: MeOut }) {
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const qc = useQueryClient();
  const { theme, setTheme } = useTheme();
  const signOut = useSignOut();

  // Routes added by later tasks are untyped until they exist.
  const go = (to: string, search?: Record<string, unknown>) => {
    onOpenChange(false);
    void navigate({ to, search } as never);
  };
  const run = (fn: () => void) => () => {
    onOpenChange(false);
    fn();
  };

  const recent = qc
    .getQueriesData<InfiniteData<{ items: Row[] }>>({ queryKey: ["list", "sources"] })
    .flatMap(([, d]) => d?.pages.flatMap((p) => p.items) ?? [])
    .filter((s, i, a) => a.findIndex((x) => x.id === s.id) === i)
    .slice(0, 5);
  const jobId = /^#?(\d+)$/.exec(q.trim())?.[1];

  return (
    <Command.Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o);
        if (!o) setQ("");
      }}
      label="Command palette"
      overlayClassName="fixed inset-0 z-50 bg-black/50"
      contentClassName="fixed left-1/2 top-[15%] z-50 w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 overflow-hidden rounded-lg border bg-popover text-popover-foreground shadow-xl"
    >
      <Command.Input value={q} onValueChange={setQ} placeholder="Type a command or search…" className="w-full border-b bg-transparent px-4 py-3 text-sm outline-none placeholder:text-muted-foreground" />
      <Command.List className="max-h-80 overflow-auto p-1">
        <Command.Empty className="px-3 py-6 text-center text-sm text-muted-foreground">No results.</Command.Empty>
        {jobId && (
          <Command.Group heading="Jobs" className={groupCls}>
            <Command.Item forceMount value={`go to job ${jobId}`} className={itemCls} onSelect={() => go(`/jobs/${jobId}`)}>
              Go to job #{jobId}
            </Command.Item>
          </Command.Group>
        )}
        <Command.Group heading="Navigate" className={groupCls}>
          {navFor(me.role === "admin").map(({ to, label, icon: Icon, shortcut }) => (
            <Command.Item key={to} value={`nav ${label}`} className={itemCls} onSelect={() => go(to)}>
              <span className="flex items-center gap-2">
                <Icon className="size-4" aria-hidden />
                {label}
              </span>
              <kbd className="text-xs text-muted-foreground">{shortcut}</kbd>
            </Command.Item>
          ))}
        </Command.Group>
        <Command.Group heading="Actions" className={groupCls}>
          <Command.Item value="action New source" className={itemCls} onSelect={() => go("/sources", { new: 1 })}>
            New source
          </Command.Item>
          <Command.Item value="action New target" className={itemCls} onSelect={() => go("/targets", { new: 1 })}>
            New target
          </Command.Item>
          <Command.Item value="action Toggle theme" className={itemCls} onSelect={run(() => setTheme(theme === "dark" ? "light" : "dark"))}>
            Toggle theme
          </Command.Item>
          <Command.Item value="action Sign out" className={itemCls} onSelect={run(() => void signOut())}>
            Sign out
          </Command.Item>
        </Command.Group>
        {recent.length > 0 && (
          <Command.Group heading="Recent sources" className={groupCls}>
            {recent.map((s) => (
              <Command.Item key={s.id} value={`source ${s.id} ${s.name ?? ""}`} className={itemCls} onSelect={() => go("/sources", { q: s.name ?? String(s.id) })}>
                {s.name ?? `Source #${s.id}`}
              </Command.Item>
            ))}
          </Command.Group>
        )}
      </Command.List>
    </Command.Dialog>
  );
}
