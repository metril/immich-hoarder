import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { api } from "../../api/client";
import { keys } from "../../api/keys";

/** POST logout, drop every cached query, then show the login screen. */
export function useSignOut() {
  const qc = useQueryClient();
  const navigate = useNavigate();
  return async () => {
    try {
      await api.POST("/api/v1/auth/logout");
    } finally {
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== "me" });
      qc.setQueryData(keys.me(), null);
      await navigate({ to: "/login" });
    }
  };
}
