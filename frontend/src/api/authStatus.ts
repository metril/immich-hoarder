import { queryOptions, useQuery } from "@tanstack/react-query";
import { api } from "./client";
import { unwrap } from "./errors";
import type { components } from "./schema";

export type AuthStatus = components["schemas"]["AuthStatus"];

export const authStatusQuery = queryOptions({
  queryKey: ["auth-status"] as const,
  queryFn: async (): Promise<AuthStatus> => unwrap(await api.GET("/api/v1/auth/status")),
  staleTime: 30_000,
});

export const useAuthStatus = () => useQuery(authStatusQuery);
