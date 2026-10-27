import { AuthShell } from "./AuthShell";
import { CredentialsForm } from "./CredentialsForm";
import { useAuthStatus } from "../../api/authStatus";
import { useSetup } from "./hooks";

export default function SetupPage() {
  const setup = useSetup();
  const needsToken = useAuthStatus().data?.reset_token_required ?? false;
  return (
    <AuthShell title="Welcome to Immich Hoarder">
      <p className="text-center text-sm text-muted-foreground">Create the first admin account to get started. You can configure SSO afterwards in Settings.</p>
      <CredentialsForm mode="setup" resetToken={needsToken} onSubmit={setup} />
    </AuthShell>
  );
}
