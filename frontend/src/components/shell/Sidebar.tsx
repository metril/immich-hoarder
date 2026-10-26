import { Link } from "@tanstack/react-router";
import { navFor } from "./nav";

export function Sidebar({ admin, label = "Main", onNavigate }: { admin: boolean; label?: string; onNavigate?: () => void }) {
  return (
    <nav aria-label={label} className="flex flex-col gap-1 p-3">
      {navFor(admin).map(({ to, label: text, icon: Icon, shortcut }) => (
        <Link
          key={to}
          to={to}
          activeOptions={{ exact: to === "/" }}
          aria-keyshortcuts={shortcut}
          onClick={onNavigate}
          className="flex items-center gap-3 rounded-md px-3 py-2 text-sm text-sidebar-foreground hover:bg-sidebar-accent focus-visible:outline-2 focus-visible:outline-sidebar-ring"
          activeProps={{ className: "bg-sidebar-accent font-medium", "aria-current": "page" }}
        >
          <Icon className="size-4" aria-hidden />
          {text}
        </Link>
      ))}
    </nav>
  );
}
