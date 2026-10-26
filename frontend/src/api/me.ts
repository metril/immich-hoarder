import { queryOptions, useQuery } from "@tanstack/react-query";
import { api } from "./client";
import { unwrap, ApiError } from "./errors";
import { keys } from "./keys";
import type { components } from "./schema";

export type MeOut = components["schemas"]["MeOut"];

export const meQuery = queryOptions({
  queryKey: keys.me(),
  queryFn: async (): Promise<MeOut | null> => {
    const r = await api.GET("/api/v1/auth/me");
    if (r.response.status === 401) return null;
    try {
      return unwrap(r);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) return null;
      throw e;
    }
  },
  staleTime: 5 * 60_000,
});

export const useMe = () => useQuery(meQuery);

export const isAdmin = (me: MeOut | null | undefined): boolean => me?.role === "admin";
