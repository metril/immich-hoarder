import { Suspense, lazy, useEffect, useState } from "react";
import { Outlet, useNavigate, useRouterState } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { isAdmin, useMe, type MeOut } from "../../api/me";
import { useDashboardStream } from "../../live/useDashboardStream";
import { MobileNav } from "./MobileNav";
import { ShortcutHelp } from "./ShortcutHelp";
import { Sidebar } from "./Sidebar";
import { ThemeToggle } from "./ThemeToggle";
import { UserMenu } from "./UserMenu";
import { navFor, titleFor } from "./nav";
import { modLabel, useShortcuts } from "./shortcuts";
import { useTheme } from "./theme";

// cmdk loads only on first open (ruling R3).
const CommandPalette = lazy(() => import("./CommandPalette"));

function Shell({ me }: { me: MeOut }) {
  const admin = isAdmin(me);
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const [palette, setPalette] = useState(false);
  const [paletteLoaded, setPaletteLoaded] = useState(false);
  const [help, setHelp] = useState(false);
  useTheme();
  useDashboardStream();

  const openPalette = () => {
    setPaletteLoaded(true);
    setPalette(true);
  };

  const map: Record<string, () => void> = {
    "mod+k": () => (palette ? setPalette(false) : openPalette()),
    "?": () => setHelp(true),
    "/": () => document.querySelector<HTMLElement>("[data-page-search]")?.focus(),
    n: () => document.querySelector<HTMLElement>("[data-new-action]")?.click(),
  };
  for (const n of navFor(admin)) map[n.shortcut] = () => void navigate({ to: n.to });
  useShortcuts(map);

  // Keep document title in sync for screen readers / history.
  const title = titleFor(pathname);
  useEffect(() => {
    document.title = title === "Immich Hoarder" ? title : `${title} · Immich Hoarder`;
  }, [title]);

  return (
    <div className="flex h-dvh bg-background text-foreground">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-background focus:p-2">
        Skip to content
      </a>
      <aside className="hidden w-56 shrink-0 border-r bg-sidebar text-sidebar-foreground md:block">
        <div className="px-6 py-4 text-sm font-semibold">Immich Hoarder</div>
        <Sidebar admin={admin} />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-2 border-b px-3 sm:px-4">
          <MobileNav admin={admin} />
          <h1 className="truncate text-base font-semibold">{title}</h1>
          <div className="ml-auto flex items-center gap-1">
            <button
              type="button"
              onClick={openPalette}
              aria-label="Open command palette"
              className="inline-flex h-9 items-center gap-2 rounded-md border px-2 text-sm text-muted-foreground hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring"
            >
              <Search className="size-4" aria-hidden />
              <kbd className="hidden font-mono text-xs sm:inline">{modLabel()} K</kbd>
            </button>
            <ThemeToggle />
            <UserMenu me={me} />
          </div>
        </header>
        <main id="main" className="min-h-0 flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
      <ShortcutHelp open={help} onClose={() => setHelp(false)} admin={admin} />
      {paletteLoaded && (
        <Suspense fallback={null}>
          <CommandPalette open={palette} onOpenChange={setPalette} me={me} />
        </Suspense>
      )}
    </div>
  );
}

export function AppLayout() {
  const { data: me } = useMe();
  const navigate = useNavigate();
  // Session dropped (401 anywhere, or sign-out): show the login screen.
  useEffect(() => {
    if (me === null) void navigate({ to: "/login" });
  }, [me, navigate]);
  if (!me) return null;
  return <Shell me={me} />;
}

