import { getRouteApi, useNavigate } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page";
import { PageSkeleton } from "../../components/common/PageSkeleton";
import { AdminTools } from "./AdminTools";
import { useSettings } from "./hooks";
import { NotifySettingsForm } from "./NotifySettingsForm";
import { RipSettingsForm } from "./RipSettingsForm";
import { RuntimeSettingsForm } from "./RuntimeSettingsForm";

const route = getRouteApi("/_app/settings");
const TABS = [
  { id: "rip", label: "Rip", blurb: "Upload and rate-limit behaviour for rips." },
  { id: "runtime", label: "Runtime", blurb: "Retention, backups and job concurrency." },
  { id: "notify", label: "Notifications", blurb: "Where and when job events are announced." },
  { id: "admin", label: "Admin tools", blurb: "" },
] as const;

export default function SettingsPage() {
  const tab = route.useSearch().tab ?? "rip";
  const navigate = useNavigate();
  const settings = useSettings();
  let body: ReactNode;
  if (tab === "admin") body = <AdminTools />;
  else if (settings.isPending) body = <PageSkeleton />;
  else if (settings.isError) body = <p role="alert" className="text-destructive">{settings.error.message}</p>;
  else if (tab === "rip") body = <RipSettingsForm value={settings.data.rip} />;
  else if (tab === "runtime") body = <RuntimeSettingsForm value={settings.data.runtime} />;
  else body = <NotifySettingsForm value={settings.data.notify} />;
  const current = TABS.find((t) => t.id === tab) ?? TABS[0];
  return (
    <>
      <PageHeader title="Settings" description="Tune ripping, runtime behaviour, notifications and maintenance." />
      <div className="grid gap-6 lg:grid-cols-[13rem_minmax(0,1fr)] lg:gap-10">
        <nav aria-label="Settings sections" className="min-w-0 lg:sticky lg:top-6 lg:self-start">
          <div role="tablist" aria-label="Settings sections" aria-orientation="horizontal" className="flex gap-1 overflow-x-auto border-b pb-px lg:flex-col lg:overflow-visible lg:border-b-0 lg:pb-0">
            {TABS.map((t, i) => (
              <button
                key={t.id}
                type="button"
                role="tab"
                id={`tab-${t.id}`}
                aria-selected={tab === t.id}
                tabIndex={tab === t.id ? 0 : -1}
                onKeyDown={(ev) => {
                  const d = ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0;
                  if (!d) return;
                  ev.preventDefault();
                  const n = TABS[(i + d + TABS.length) % TABS.length]!;
                  void navigate({ to: "/settings", search: { tab: n.id }, replace: true });
                  document.getElementById(`tab-${n.id}`)?.focus();
                }}
                aria-controls="settings-panel"
                onClick={() => void navigate({ to: "/settings", search: { tab: t.id }, replace: true })}
                className="shrink-0 whitespace-nowrap rounded-md px-3 py-2 text-left text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground focus-visible:outline-2 focus-visible:outline-ring aria-selected:bg-accent aria-selected:font-medium aria-selected:text-accent-foreground"
              >
                {t.label}
              </button>
            ))}
          </div>
        </nav>
        <section role="tabpanel" id="settings-panel" aria-labelledby={`tab-${tab}`} className="min-w-0 max-w-2xl">
          {tab === "admin" ? (
            body
          ) : (
            <Card>
              <CardHeader>
                <CardTitle>{current.label}</CardTitle>
                <CardDescription>{current.blurb}</CardDescription>
              </CardHeader>
              <CardContent>{body}</CardContent>
            </Card>
          )}
        </section>
      </div>
    </>
  );
}
