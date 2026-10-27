import { z } from "zod";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { FormField, FormRootError } from "../../components/common/FormField";
import { useApiForm } from "../../components/common/useApiForm";

const loginSchema = z.object({ username: z.string().trim().min(1, "Required"), password: z.string().min(1, "Required"), reset_token: z.string().optional() });
const setupSchema = z.object({ username: z.string().trim().min(1, "Required"), password: z.string().min(8, "Min 8 characters"), reset_token: z.string().optional() });

/** Username + password form used by both local login and first-run setup. */
export function CredentialsForm({
  mode,
  resetToken = false,
  onSubmit,
}: {
  mode: "login" | "setup";
  resetToken?: boolean;
  onSubmit: (v: { username: string; password: string; reset_token?: string }) => Promise<unknown>;
}) {
  const form = useApiForm(mode === "setup" ? setupSchema : loginSchema, { defaultValues: { username: "", password: "", reset_token: "" }, onSubmit });
  const e = form.formState.errors;
  return (
    <form onSubmit={form.submit} className="grid gap-4" noValidate>
      <FormField label="Username" error={e.username?.message}>
        <Input autoComplete="username" {...form.register("username")} />
      </FormField>
      <FormField label="Password" error={e.password?.message} hint={mode === "setup" ? "At least 8 characters" : undefined}>
        <Input type="password" autoComplete={mode === "setup" ? "new-password" : "current-password"} {...form.register("password")} />
      </FormField>
      {mode === "setup" && resetToken && (
        <FormField label="Reset token" error={e.reset_token?.message} hint="Printed in the server log at startup (IH_BREAK_GLASS_RESET)">
          <Input autoComplete="off" {...form.register("reset_token")} />
        </FormField>
      )}
      <FormRootError message={form.rootError} />
      <Button type="submit" size="lg" loading={form.formState.isSubmitting}>
        {mode === "setup" ? "Create admin account" : "Sign in"}
      </Button>
    </form>
  );
}
