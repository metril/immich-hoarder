import type { ComponentProps } from "react";
import type { components } from "../../api/schema";
import { Badge } from "../../components/ui/badge";

type Tone = NonNullable<ComponentProps<typeof Badge>["tone"]>;
const TONE: Record<components["schemas"]["JobStatus"], Tone> = {
  queued: "neutral",
  running: "info",
  succeeded: "success",
  failed: "danger",
  cancelled: "warning",
};

export function StatusBadge({ status }: { status: components["schemas"]["JobStatus"] }) {
  return (
    <Badge tone={TONE[status]} dot>
      {status}
    </Badge>
  );
}

export function OutcomeBadge({ outcome }: { outcome: string }) {
  const tone: Tone =
    outcome === "failed" ? "danger" : outcome === "uploaded" || outcome === "linked" ? "success" : outcome === "filtered" ? "warning" : "neutral";
  return <Badge tone={tone}>{outcome}</Badge>;
}
