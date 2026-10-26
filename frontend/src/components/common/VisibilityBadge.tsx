import type { components } from "../../api/schema";

const STYLE: Record<components["schemas"]["Visibility"], string> = {
  private: "bg-secondary text-secondary-foreground",
  everyone: "bg-accent text-accent-foreground",
  restricted: "bg-muted text-foreground",
};

export function VisibilityBadge({ visibility }: { visibility: components["schemas"]["Visibility"] }) {
  return <span className={`rounded-full border px-2 py-0.5 text-xs ${STYLE[visibility]}`}>{visibility}</span>;
}
