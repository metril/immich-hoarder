import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

export function EmptyState({ title, hint, action, icon }: { title: string; hint?: string; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed p-8 text-center">
      <span aria-hidden className="grid size-10 place-items-center rounded-full bg-muted text-muted-foreground [&_svg]:size-5">
        {icon ?? <Inbox />}
      </span>
      <div className="min-w-0 space-y-1">
        <p className="text-base font-medium">{title}</p>
        {hint && <p className="text-sm text-muted-foreground">{hint}</p>}
      </div>
      {action}
    </div>
  );
}
