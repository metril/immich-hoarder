import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";
import { PageSkeleton } from "../../components/common/PageSkeleton";

const TABS = ["rip", "runtime", "notify", "auth", "admin"] as const;
export type SettingsTab = (typeof TABS)[number];

export const Route = createFileRoute("/_app/settings")({
  staticData: { admin: true },
  // Hand-rolled: zod stays out of the eager bundle (R3).
  validateSearch: (s: Record<string, unknown>): { tab?: SettingsTab } =>
    typeof s.tab === "string" && (TABS as readonly string[]).includes(s.tab) ? { tab: s.tab as SettingsTab } : {},
  component: lazyRouteComponent(() => import("../../features/settings/SettingsPage")),
  pendingComponent: PageSkeleton,
});
