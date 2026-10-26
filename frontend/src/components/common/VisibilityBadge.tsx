import type { components } from "../../api/schema";
import { Badge } from "../ui/badge";

const TONE: Record<components["schemas"]["Visibility"], "neutral" | "info" | "warning"> = {
  private: "neutral",
  everyone: "info",
  restricted: "warning",
};

export function VisibilityBadge({ visibility }: { visibility: components["schemas"]["Visibility"] }) {
  return <Badge tone={TONE[visibility]}>{visibility}</Badge>;
}
