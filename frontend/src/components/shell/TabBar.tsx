import { Link } from "@tanstack/react-router";
import { ActiveJobsBadge } from "./ActiveJobsBadge";
import { Database, Ellipsis, LayoutDashboard, ListChecks, type LucideIcon } from "lucide-react";

const TABS: { to: "/" | "/sources" | "/jobs"; label: string; icon: LucideIcon }[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/sources", label: "Sources", icon: Database },
  { to: "/jobs", label: "Jobs", icon: ListChecks },
];

const base = "flex flex-1 flex-col items-center justify-center gap-0.5 text-[11px] text-muted-foreground focus-visible:outline-2 focus-visible:outline-ring";

/** Mobile bottom tab bar; "More" opens the full navigation drawer. */
export function TabBar({ onMore }: { onMore: () => void }) {
  return (
    <nav
      aria-label="Tabs"
      className="fixed inset-x-0 bottom-0 z-30 flex h-16 border-t bg-background/80 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden"
    >
      {TABS.map(({ to, label, icon: Icon }) => (
        <Link
          key={to}
          to={to}
          activeOptions={{ exact: to === "/" }}
          className={base}
          activeProps={{ className: "!text-primary font-medium", "aria-current": "page" }}
        >
          <span className="relative">
            <Icon className="size-5" aria-hidden />
            {to === "/jobs" ? <ActiveJobsBadge className="absolute -top-2 left-3 px-1.5 py-0 text-[10px]" /> : null}
          </span>
          {label}
        </Link>
      ))}
      <button type="button" className={base} onClick={onMore}>
        <Ellipsis className="size-5" aria-hidden />
        More
      </button>
    </nav>
  );
}
