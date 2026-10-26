import { useEffect, useState } from "react";
import { createFileRoute, redirect } from "@tanstack/react-router";
import { Aperture } from "lucide-react";
import { meQuery } from "../api/me";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";

export const Route = createFileRoute("/login")({
  beforeLoad: async ({ context }) => {
    if (await context.queryClient.ensureQueryData(meQuery)) throw redirect({ to: "/" });
  },
  component: Login,
});

function Login() {
  const [status, setStatus] = useState<number | null>(null);
  useEffect(() => {
    const ac = new AbortController();
    fetch(`${location.origin}/api/v1/auth/login`, { method: "HEAD", redirect: "manual", signal: ac.signal })
      .then((r) => setStatus(r.status))
      .catch(() => {});
    return () => ac.abort();
  }, []);
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
      <div className="flex items-center justify-center p-4">
        <Card className="w-full max-w-sm space-y-6 p-8 text-center">
          <div className="space-y-3">
            <span className="mx-auto grid size-12 place-items-center rounded-xl bg-primary/15 text-primary">
              <Aperture className="size-7" aria-hidden />
            </span>
            <h1 className="font-display text-2xl font-semibold tracking-tight">Immich Hoarder</h1>
          </div>
          <Button asChild size="lg" className="w-full">
            <a href="/api/v1/auth/login">Sign in with SSO</a>
          </Button>
          {status === 503 && (
            <p role="status" className="text-sm text-muted-foreground">
              OIDC is not configured
            </p>
          )}
        </Card>
      </div>
    </main>
  );
}
