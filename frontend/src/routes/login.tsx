import { useEffect, useState } from "react";
import { createFileRoute, redirect } from "@tanstack/react-router";
import { keys } from "../api/keys";

export const Route = createFileRoute("/login")({
  beforeLoad: ({ context }) => {
    if (context.queryClient.getQueryData(keys.me())) throw redirect({ to: "/" });
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
    <main className="flex min-h-dvh items-center justify-center bg-background p-4 text-foreground">
      <div className="w-full max-w-sm space-y-4 rounded-lg border bg-card p-6 text-center text-card-foreground">
        <h1 className="text-xl font-semibold">Immich Hoarder</h1>
        <a
          href="/api/v1/auth/login"
          className="inline-flex h-10 w-full items-center justify-center rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          Sign in with SSO
        </a>
        {status === 503 && (
          <p role="status" className="text-sm text-muted-foreground">
            OIDC is not configured
          </p>
        )}
      </div>
    </main>
  );
}
