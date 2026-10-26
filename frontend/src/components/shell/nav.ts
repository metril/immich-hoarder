import { Database, Key, KeyRound, LayoutDashboard, ListChecks, Settings, Target, Users, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  admin?: boolean;
  shortcut: string;
}

export const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, shortcut: "g d" },
  { to: "/sources", label: "Sources", icon: Database, shortcut: "g s" },
  { to: "/jobs", label: "Jobs", icon: ListChecks, shortcut: "g j" },
  { to: "/targets", label: "Targets", icon: Target, shortcut: "g t" },
  { to: "/credentials", label: "Credentials", icon: KeyRound, shortcut: "g c" },
  { to: "/api-keys", label: "API Keys", icon: Key, shortcut: "g k" },
  { to: "/users", label: "Users", icon: Users, admin: true, shortcut: "g u" },
  { to: "/settings", label: "Settings", icon: Settings, admin: true, shortcut: "g ," },
];

export const navFor = (admin: boolean) => NAV.filter((n) => !n.admin || admin);

export const isAdminPath = (pathname: string) =>
  NAV.some((n) => n.admin && (pathname === n.to || pathname.startsWith(`${n.to}/`)));

export function titleFor(pathname: string): string {
  const hit = NAV.filter((n) => (n.to === "/" ? pathname === "/" : pathname === n.to || pathname.startsWith(`${n.to}/`))).sort(
    (a, b) => b.to.length - a.to.length,
  )[0];
  return hit?.label ?? "Immich Hoarder";
}
