import { Suspense, lazy, useEffect, useState } from "react";
import { Link, Outlet, useNavigate, useRouterState } from "@tanstack/react-router";
import { Search } from "lucide-react";
import { Fragment } from "react";
import { isAdmin, useMe, type MeOut } from "../../api/me";
import { useDashboardStream } from "../../live/useDashboardStream";
import { BreakGlassBanner } from "../../features/auth/BreakGlassBanner";
import { MobileNav } from "./MobileNav";
import { ShortcutHelp } from "./ShortcutHelp";
import { Sidebar } from "./Sidebar";
import { ThemeToggle } from "./ThemeToggle";
import { UserMenu } from "./UserMenu";
import { crumbsFor, navFor, titleFor } from "./nav";
import { TabBar } from "./TabBar";
import { PageContainer } from "../ui/page";
import { TooltipProvider } from "../ui/tooltip";
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
  const [navOpen, setNavOpen] = useState(false);
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

  const crumbs = crumbsFor(pathname);

  return (
    <TooltipProvider delayDuration={300}>
    <div className="flex h-dvh bg-background text-foreground">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:bg-background focus:p-2">
        Skip to content
      </a>
      <aside className="hidden w-64 shrink-0 border-r bg-sidebar text-sidebar-foreground md:block">
        <Sidebar admin={admin} me={me} />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <BreakGlassBanner />
        <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center gap-3 border-b bg-background/70 px-3 backdrop-blur sm:px-6">
          <MobileNav admin={admin} me={me} open={navOpen} onOpenChange={setNavOpen} />
          <nav aria-label="Breadcrumb" className="min-w-0">
            <ol className="flex items-center gap-1.5 text-sm text-muted-foreground">
              {crumbs.map((c, i) => (
                <Fragment key={c.label}>
                  {i > 0 && <li aria-hidden>/</li>}
                  <li className={i === crumbs.length - 1 ? "truncate font-medium text-foreground" : "truncate"}>
                    {c.to ? (
                      <Link to={c.to} className="hover:text-foreground">
                        {c.label}
                      </Link>
                    ) : (
                      c.label
                    )}
                  </li>
                </Fragment>
              ))}
            </ol>
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <button
              type="button"
              onClick={openPalette}
              className="inline-flex h-9 items-center gap-2 rounded-lg border bg-muted/40 px-3 text-sm text-muted-foreground transition-colors hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring md:w-72 lg:w-96"
            >
              <Search className="size-4 shrink-0" aria-hidden />
              <span className="sr-only">Open command palette</span>
              <span className="hidden flex-1 truncate text-left md:inline">Search or jump to…</span>
              <kbd className="hidden rounded-md border bg-background px-1.5 py-0.5 font-mono text-[11px] md:inline">{modLabel()} K</kbd>
            </button>
            <ThemeToggle />
            <UserMenu me={me} />
          </div>
        </header>
        <main id="main" className="min-h-0 min-w-0 flex-1 overflow-auto pb-20 md:pb-0">
          <PageContainer>
            <Outlet />
          </PageContainer>
        </main>
      </div>
      <TabBar onMore={() => setNavOpen(true)} />
      <ShortcutHelp open={help} onClose={() => setHelp(false)} admin={admin} />
      {paletteLoaded && (
        <Suspense fallback={null}>
          <CommandPalette open={palette} onOpenChange={setPalette} me={me} />
        </Suspense>
      )}
    </div>
    </TooltipProvider>
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

