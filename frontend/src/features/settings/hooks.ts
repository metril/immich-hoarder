import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { unwrap } from "../../api/errors";
import { keys } from "../../api/keys";
import type { components } from "../../api/schema";

export type SettingsDoc = components["schemas"]["SettingsDoc"];
export type ImportResult = components["schemas"]["ImportResult"];

export function useSettings() {
  return useQuery({
    queryKey: keys.settings(),
    queryFn: async () => unwrap(await api.GET("/api/v1/settings")),
  });
}

/** PUT merges per key; send only the tab's own key. */
export function useSaveSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: SettingsDoc) => unwrap(await api.PUT("/api/v1/settings", { body })),
    onSuccess: (doc) => qc.setQueryData(keys.settings(), doc),
  });
}

export function useBackups() {
  return useQuery({
    queryKey: keys.backups(),
    queryFn: async () => unwrap(await api.GET("/api/v1/admin/backups")),
  });
}

export function useBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => unwrap(await api.POST("/api/v1/admin/backup")),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.backups() }),
  });
}

export function usePrune() {
  return useMutation({ mutationFn: async () => unwrap(await api.POST("/api/v1/admin/maintenance/prune")) });
}

export async function importYaml(text: string, dryRun: boolean): Promise<ImportResult> {
  return unwrap(
    await api.POST("/api/v1/admin/import", {
      params: { query: { dry_run: dryRun } },
      body: text,
      bodySerializer: (b) => b,
      headers: { "Content-Type": "application/yaml" },
    }),
  );
}

/** Fetch the config export and save it as a file. */
export async function downloadExport(secrets: "omit" | "encrypted"): Promise<void> {
  const text = unwrap(await api.GET("/api/v1/admin/export", { params: { query: { secrets } }, parseAs: "text" }));
  const url = URL.createObjectURL(new Blob([text], { type: "application/yaml" }));
  try {
    const a = document.createElement("a");
    a.href = url;
    a.download = "immich-hoarder-config.yaml";
    document.body.appendChild(a);
    a.click();
    a.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
}

export function useOidcTest() {
  return useMutation({
    mutationFn: async (issuer: string | null) =>
      unwrap(await api.POST("/api/v1/settings/oidc/test", { body: { issuer: issuer || null } })),
  });
}

export function useChangeLocalPassword() {
  return useMutation({
    mutationFn: async (body: { current_password?: string; new_password: string }) =>
      unwrap(await api.PUT("/api/v1/settings/local-admin", { body })),
  });
}
