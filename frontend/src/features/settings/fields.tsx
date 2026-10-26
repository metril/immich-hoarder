import { FormRootError } from "../../components/common/FormField";


export function SaveBar({ root, busy }: { root?: string; busy: boolean }) {
  return (
    <>
      <FormRootError message={root} />
      <div>
        <button
          type="submit"
          disabled={busy}
          className="rounded-md bg-primary px-4 py-1.5 text-sm text-primary-foreground focus-visible:outline-2 focus-visible:outline-ring disabled:opacity-50"
        >
          Save
        </button>
      </div>
    </>
  );
}
