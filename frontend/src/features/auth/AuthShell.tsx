import type { ReactNode } from "react";
import { Aperture } from "lucide-react";
import { Card } from "../../components/ui/card";
import { BreakGlassBanner } from "./BreakGlassBanner";

/** Two-pane layout shared by the login and first-run setup screens. */
export function AuthShell({ title, children }: { title: string; children: ReactNode }) {
  return (
    <main className="grid min-h-dvh bg-background text-foreground lg:grid-cols-2">
      <div className="relative hidden overflow-hidden bg-sidebar lg:block" aria-hidden>
        <div className="absolute -left-24 -top-24 size-[32rem] rounded-full bg-gradient-to-br from-primary to-info opacity-40 blur-3xl" />
        <div className="absolute -bottom-32 right-0 size-[28rem] rounded-full bg-gradient-to-tr from-info to-primary opacity-30 blur-3xl" />
        <div className="relative flex h-full flex-col justify-end p-12">
          <Aperture className="mb-6 size-12 text-primary" />
          <p className="font-display text-4xl font-semibold tracking-tight">Every frame, kept.</p>
          <p className="mt-3 max-w-sm text-muted-foreground">Rip, archive and hand off your media to Immich.</p>
        </div>
      </div>
      <div className="flex flex-col">
        <BreakGlassBanner />
        <div className="flex flex-1 items-center justify-center p-4">
          <Card className="w-full max-w-sm space-y-6 p-8">
            <div className="space-y-3 text-center">
              <span className="mx-auto grid size-12 place-items-center rounded-xl bg-primary/15 text-primary">
                <Aperture className="size-7" aria-hidden />
              </span>
              <h1 className="font-display text-2xl font-semibold tracking-tight">{title}</h1>
            </div>
            {children}
          </Card>
        </div>
      </div>
    </main>
  );
}
