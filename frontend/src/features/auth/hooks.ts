import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { api } from "../../api/client";
import { unwrap, ApiError } from "../../api/errors";
import { keys } from "../../api/keys";

type Creds = { username: string; password: string; reset_token?: string };

/** POST credentials, seed the `me` cache, go to the dashboard. */
function useSessionPost(kind: "setup" | "login") {
  const qc = useQueryClient();
  const navigate = useNavigate();
  return async (body: Creds) => {
    const r = kind === "setup" ? await api.POST("/api/v1/auth/setup", { body: { ...body, reset_token: body.reset_token || undefined } }) : await api.POST("/api/v1/auth/local/login", { body: { username: body.username, password: body.password } });
    if (r.response.status === 429) {
      const wait = r.response.headers.get("Retry-After");
      throw new ApiError(429, `Too many attempts. Try again${wait ? ` in ${wait}s` : " later"}.`, null);
    }
    const me = unwrap(r);
    qc.setQueryData(keys.me(), me);
    await qc.invalidateQueries({ queryKey: ["auth-status"] });
    await navigate({ to: "/" });
  };
}

export const useSetup = () => useSessionPost("setup");
export const useLocalLogin = () => useSessionPost("login");
