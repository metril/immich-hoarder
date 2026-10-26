import type { MeOut } from "../../api/me";
import type { LinkProps } from "@tanstack/react-router";
import { Database, Key, KeyRound, LayoutDashboard, ListChecks, Settings, Target, Users, type LucideIcon } from "lucide-react";

export interface NavItem {
  to: LinkProps["to"] & string;
  label: string;
  icon: LucideIcon;
  admin?: boolean;
  shortcut: string;
  group: NavGroup;
}

export type NavGroup = "Overview" | "Library" | "Access" | "System";
export const GROUPS: NavGroup[] = ["Overview", "Library", "Access", "System"];

export const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, shortcut: "g d", group: "Overview" },
  { to: "/jobs", label: "Jobs", icon: ListChecks, shortcut: "g j", group: "Overview" },
  { to: "/sources", label: "Sources", icon: Database, shortcut: "g s", group: "Library" },
  { to: "/targets", label: "Targets", icon: Target, shortcut: "g t", group: "Library" },
  { to: "/credentials", label: "Credentials", icon: KeyRound, shortcut: "g c", group: "Access" },
  { to: "/api-keys", label: "API Keys", icon: Key, shortcut: "g k", group: "Access" },
  { to: "/users", label: "Users", icon: Users, admin: true, shortcut: "g u", group: "Access" },
  { to: "/settings", label: "Settings", icon: Settings, admin: true, shortcut: "g ,", group: "System" },
];

export const navFor = (admin: boolean) => NAV.filter((n) => !n.admin || admin);

export function titleFor(pathname: string): string {
  const hit = NAV.filter((n) => (n.to === "/" ? pathname === "/" : pathname.toLowerCase() === n.to || pathname.toLowerCase().startsWith(`${n.to}/`))).sort(
    (a, b) => b.to.length - a.to.length,
  )[0];
  return hit?.label ?? "Immich Hoarder";
}

/** Breadcrumb trail for a pathname: section label plus any detail segment. */
export function crumbsFor(pathname: string): { label: string; to?: string }[] {
  const hit = NAV.filter((n) => n.to !== "/" && (pathname.toLowerCase() === n.to || pathname.toLowerCase().startsWith(`${n.to}/`))).sort(
    (a, b) => b.to.length - a.to.length,
  )[0];
  if (!hit) return [{ label: "Dashboard" }];
  const rest = pathname.slice(hit.to.length).split("/").filter(Boolean);
  const out: { label: string; to?: string }[] = [{ label: hit.label, to: rest.length ? hit.to : undefined }];
  if (rest.length) out.push({ label: /^\d+$/.test(rest[0]!) ? `#${rest[0]}` : rest[0]! });
  return out;
}

export const initials = (me: MeOut) => (me.name ?? me.email ?? "?").trim().slice(0, 2).toUpperCase();
