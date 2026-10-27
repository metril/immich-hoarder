import { Button } from "../../components/ui/button";
import { useAuthStatus } from "../../api/authStatus";
import { AuthShell } from "./AuthShell";
import { CredentialsForm } from "./CredentialsForm";
import { useLocalLogin } from "./hooks";

export default function LoginPage() {
  const { data: status } = useAuthStatus();
  const login = useLocalLogin();
  const oidc = status?.oidc_enabled ?? false;
  const local = status?.local_login_enabled ?? false;
  return (
    <AuthShell title="Immich Hoarder">
      {oidc && (
        <Button asChild size="lg" className="w-full">
          <a href="/api/v1/auth/login">Sign in with SSO</a>
        </Button>
      )}
      {oidc && local && <p className="text-center text-xs uppercase tracking-wide text-muted-foreground">or</p>}
      {local && <CredentialsForm mode="login" onSubmit={login} />}
      {status && !oidc && !local && (
        <p role="status" className="text-center text-sm text-muted-foreground">
          No sign-in method is enabled
        </p>
      )}
    </AuthShell>
  );
}
