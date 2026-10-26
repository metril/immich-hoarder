import { formatRelative } from "./formatRelative";

export function RelativeTime({ iso }: { iso: string | null | undefined }) {
  if (!iso) return <span>—</span>;
  return (
    <time dateTime={iso} title={new Date(iso).toLocaleString()}>
      {formatRelative(iso)}
    </time>
  );
}
