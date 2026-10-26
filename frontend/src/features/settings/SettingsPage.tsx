import { getRouteApi, useNavigate } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { PageSkeleton } from "../../components/common/PageSkeleton";
import { AdminTools } from "./AdminTools";
import { useSettings } from "./hooks";
import { NotifySettingsForm } from "./NotifySettingsForm";
import { RipSettingsForm } from "./RipSettingsForm";
import { RuntimeSettingsForm } from "./RuntimeSettingsForm";

const route = getRouteApi("/_app/settings");
const TABS = [
  { id: "rip", label: "Rip" },
  { id: "runtime", label: "Runtime" },
  { id: "notify", label: "Notifications" },
  { id: "admin", label: "Admin tools" },
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
  return (
    <div className="grid gap-4">
      <h1 className="text-xl font-semibold">Settings</h1>
      <div role="tablist" aria-label="Settings sections" className="flex flex-wrap gap-1 border-b">
        {TABS.map((t, i) => (
          <button
            key={t.id}
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
            className="-mb-px border-b-2 border-transparent px-3 py-2 text-sm hover:bg-accent focus-visible:outline-2 focus-visible:outline-ring aria-selected:border-primary aria-selected:font-medium"
          >
            {t.label}
          </button>
        ))}
      </div>
      <section role="tabpanel" id="settings-panel" aria-labelledby={`tab-${tab}`} className="max-w-2xl">
        {body}
      </section>
    </div>
  );
}
