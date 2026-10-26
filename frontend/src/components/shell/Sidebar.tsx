import { Link } from "@tanstack/react-router";
import { Aperture } from "lucide-react";
import type { MeOut } from "../../api/me";
import { Badge } from "../ui/badge";
import { GROUPS, initials, navFor } from "./nav";

export function Logo() {
  return (
    <div className="flex h-16 shrink-0 items-center gap-2.5 px-5">
      <span className="grid size-8 place-items-center rounded-lg bg-primary/15 text-primary">
        <Aperture className="size-5" aria-hidden />
      </span>
      <span className="font-display text-base font-semibold tracking-tight">Immich Hoarder</span>
    </div>
  );
}


export function Sidebar({
  admin,
  me,
  label = "Main",
  onNavigate,
}: {
  admin: boolean;
  me?: MeOut;
  label?: string;
  onNavigate?: () => void;
}) {
  const items = navFor(admin);
  return (
    <div className="flex h-full min-h-0 flex-col">
      <Logo />
      <nav aria-label={label} className="min-h-0 flex-1 space-y-5 overflow-y-auto px-3 py-2">
        {GROUPS.map((g) => {
          const list = items.filter((n) => n.group === g);
          if (!list.length) return null;
          return (
            <div key={g} className="space-y-1">
              <p className="px-3 pb-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground">{g}</p>
              {list.map(({ to, label: text, icon: Icon, shortcut }) => (
                <Link
                  key={to}
                  to={to}
                  activeOptions={{ exact: to === "/" }}
                  aria-keyshortcuts={shortcut}
                  onClick={onNavigate}
                  className="relative flex h-10 items-center gap-3 rounded-lg px-3 text-sm text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-foreground focus-visible:outline-2 focus-visible:outline-sidebar-ring"
                  activeProps={{
                    className:
                      "bg-sidebar-primary/10 font-medium text-sidebar-foreground before:absolute before:inset-y-2 before:left-0 before:w-[3px] before:rounded-r-full before:bg-sidebar-primary",
                    "aria-current": "page",
                  }}
                >
                  <Icon className="size-4" aria-hidden />
                  {text}
                </Link>
              ))}
            </div>
          );
        })}
      </nav>
      {me && (
        <div className="m-3 flex items-center gap-3 rounded-xl border bg-card/60 p-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-full bg-primary/15 text-xs font-semibold text-primary" aria-hidden>
            {initials(me)}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{me.name ?? me.email ?? `User ${me.id}`}</p>
            <Badge tone="neutral" className="mt-0.5">{me.role}</Badge>
          </div>
        </div>
      )}
    </div>
  );
}
