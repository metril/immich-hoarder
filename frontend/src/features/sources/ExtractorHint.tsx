import { useEffect, useState } from "react";
import { useExtractors } from "./hooks";

function hostOf(url: string): string | null {
  try {
    return new URL(url.includes("://") ? url : `https://${url}`).hostname.toLowerCase();
  } catch {
    return null;
  }
}

export function ExtractorHint({ url }: { url: string }) {
  const [debounced, setDebounced] = useState(url);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(url), 300);
    return () => clearTimeout(t);
  }, [url]);
  const { data } = useExtractors();
  if (!debounced.trim() || !data) return null;
  const host = hostOf(debounced);
  const labels = host ? host.split(".") : [];
  const hit = host
    ? data.items.find((e) => {
        const c = e.category.toLowerCase().replace(/[\s_-]+/g, "");
        return c.length > 1 && (labels.includes(c) || host.replace(/\./g, "").includes(c));
      })
    : undefined;
  return (
    <p className="text-xs text-muted-foreground" aria-live="polite">
      {hit ? `Supported: ${hit.category}` : "Not obviously supported — the server will validate"}
    </p>
  );
}
