import { Button } from "@/components/ui/button";
import { FormRootError } from "../../components/common/FormField";

export function SaveBar({ root, busy }: { root?: string; busy: boolean }) {
  return (
    <>
      <FormRootError message={root} />
      <div>
        <Button type="submit" loading={busy}>
          Save
        </Button>
      </div>
    </>
  );
}
