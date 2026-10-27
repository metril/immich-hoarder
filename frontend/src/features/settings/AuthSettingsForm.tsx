import { Controller } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { FormField, FormRootError } from "../../components/common/FormField";
import { SecretInput } from "../../components/common/SecretInput";
import { useApiForm } from "../../components/common/useApiForm";
import { SaveBar } from "./fields";
import { useChangeLocalPassword, useOidcTest, useSaveSettings, type SettingsDoc } from "./hooks";
import { useState } from "react";

const csv = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const optional = (s: string) => (s.trim() === "" ? null : s.trim());

const schema = z.object({
  public_url: z.string().trim(),
  local_enabled: z.boolean(),
  enabled: z.boolean(),
  issuer: z.string().trim(),
  client_id: z.string().trim(),
  client_secret: z.string(),
  admin_groups: z.string(),
  user_groups: z.string(),
  groups_claim: z.string().trim().min(1, "Required"),
});

export function AuthSettingsForm({ value }: { value?: SettingsDoc }) {
  const save = useSaveSettings();
  const oidc = value?.oidc;
  const form = useApiForm(schema, {
    defaultValues: {
      public_url: value?.auth?.public_url ?? "",
      local_enabled: value?.auth?.local_enabled ?? true,
      enabled: oidc?.enabled ?? false,
      issuer: oidc?.issuer ?? "",
      client_id: oidc?.client_id ?? "",
      client_secret: "",
      admin_groups: (oidc?.admin_groups ?? ["hoarder-admins"]).join(", "),
      user_groups: (oidc?.user_groups ?? ["hoarder-users"]).join(", "),
      groups_claim: oidc?.groups_claim ?? "groups",
    },
    onSubmit: async (v) => {
      await save.mutateAsync({
        auth: { public_url: optional(v.public_url), local_enabled: v.local_enabled },
        oidc: {
          enabled: v.enabled,
          issuer: optional(v.issuer),
          client_id: optional(v.client_id),
          // Blank keeps the stored secret.
          client_secret: v.client_secret === "" ? null : v.client_secret,
          admin_groups: csv(v.admin_groups),
          user_groups: csv(v.user_groups),
          groups_claim: v.groups_claim,
          client_secret_set: oidc?.client_secret_set ?? false,
        },
      });
      form.setValue("client_secret", "");
      toast.success("Authentication settings saved");
    },
  });
  const e = form.formState.errors;
  const test = useOidcTest();
  const [result, setResult] = useState<{ ok: boolean; error?: string | null } | null>(null);
  const runTest = async () => {
    setResult(null);
    try {
      setResult(await test.mutateAsync(optional(form.getValues("issuer"))));
    } catch (err) {
      setResult({ ok: false, error: err instanceof Error ? err.message : "Test failed" });
    }
  };
  return (
    <div className="grid gap-8">
      <form onSubmit={form.submit} className="grid gap-5" noValidate>
        <FormField label="Public URL" error={e.public_url?.message} hint="Externally visible base URL used for OIDC redirects. Empty derives it from the request.">
          <Input type="url" placeholder="https://hoarder.example.com" {...form.register("public_url")} />
        </FormField>
        <Controller
          control={form.control}
          name="enabled"
          render={({ field }) => (
            <div className="flex items-center gap-3">
              <Switch id="oidc-enabled" checked={field.value} onCheckedChange={field.onChange} />
              <Label htmlFor="oidc-enabled">Enable OIDC single sign-on</Label>
            </div>
          )}
        />
        <FormField label="Issuer URL" error={e.issuer?.message}>
          <Input type="url" placeholder="https://auth.example.com/application/o/hoarder/" {...form.register("issuer")} />
        </FormField>
        <FormField label="Client ID" error={e.client_id?.message}>
          <Input autoComplete="off" {...form.register("client_id")} />
        </FormField>
        <FormField
          label="Client secret"
          error={e.client_secret?.message}
          hint={oidc?.client_secret_set ? "A secret is set. Leave blank to keep it." : "No secret set yet."}
        >
          <SecretInput saved={oidc?.client_secret_set ?? false} {...form.register("client_secret")} />
        </FormField>
        <FormField label="Admin groups" error={e.admin_groups?.message} hint="Comma-separated OIDC groups granted the admin role">
          <Input {...form.register("admin_groups")} />
        </FormField>
        <FormField label="User groups" error={e.user_groups?.message} hint="Comma-separated OIDC groups granted the user role">
          <Input {...form.register("user_groups")} />
        </FormField>
        <FormField label="Groups claim" error={e.groups_claim?.message}>
          <Input {...form.register("groups_claim")} />
        </FormField>
        <div className="flex flex-wrap items-center gap-3">
          <Button type="button" variant="outline" loading={test.isPending} onClick={() => void runTest()}>
            Test issuer
          </Button>
          {result && (
            <p role="status" className={result.ok ? "text-sm text-success" : "text-sm text-destructive"}>
              {result.ok ? "Issuer reachable" : (result.error ?? "Issuer check failed")}
            </p>
          )}
        </div>
        <Controller
          control={form.control}
          name="local_enabled"
          render={({ field }) => (
            <div className="grid gap-1.5">
              <div className="flex items-center gap-3">
                <Switch id="local-enabled" checked={field.value} onCheckedChange={field.onChange} />
                <Label htmlFor="local-enabled">Allow local username/password login</Label>
              </div>
              <p className="text-xs text-muted-foreground">Can only be turned off while OIDC is enabled and working.</p>
            </div>
          )}
        />
        <SaveBar root={form.rootError} busy={form.formState.isSubmitting} />
      </form>
      <ChangePasswordForm />
    </div>
  );
}

const pwSchema = z.object({ current_password: z.string(), new_password: z.string().min(8, "Min 8 characters") });

function ChangePasswordForm() {
  const change = useChangeLocalPassword();
  const form = useApiForm(pwSchema, {
    defaultValues: { current_password: "", new_password: "" },
    onSubmit: async (v) => {
      await change.mutateAsync({ current_password: v.current_password || undefined, new_password: v.new_password });
      form.reset();
      toast.success("Password changed");
    },
  });
  const e = form.formState.errors;
  return (
    <form onSubmit={form.submit} className="grid gap-5 border-t pt-6" noValidate>
      <h3 className="text-sm font-semibold">Change local admin password</h3>
      <FormField label="Current password" error={e.current_password?.message}>
        <Input type="password" autoComplete="current-password" {...form.register("current_password")} />
      </FormField>
      <FormField label="New password" error={e.new_password?.message} hint="At least 8 characters">
        <Input type="password" autoComplete="new-password" {...form.register("new_password")} />
      </FormField>
      <FormRootError message={form.rootError} />
      <div>
        <Button type="submit" loading={form.formState.isSubmitting}>
          Change password
        </Button>
      </div>
    </form>
  );
}
