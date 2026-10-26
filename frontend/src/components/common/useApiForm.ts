import { useForm, type DefaultValues, type FieldValues, type Path, type UseFormReturn } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import type { z } from "zod";
import { ApiError } from "../../api/errors";

/** True when `dotted` is registered, or lies under a registered object-valued field (e.g. a Controller on `filters`). */
function isRegistered(fields: unknown, dotted: string): boolean {
  let cur: unknown = fields;
  for (const part of dotted.split(".")) {
    if (typeof cur !== "object" || cur === null || !(part in cur)) return false;
    cur = (cur as Record<string, unknown>)[part];
    if (typeof cur === "object" && cur !== null && "_f" in cur) return true;
  }
  return false;
}

/**
 * react-hook-form + zod. Server 422s map onto fields by dotted name
 * (empty loc -> "root"); other errors toast. The form is never reset on failure.
 */
export function useApiForm<S extends z.ZodType<FieldValues, FieldValues>>(
  schema: S,
  opts: { defaultValues: DefaultValues<z.input<S>>; onSubmit: (v: z.output<S>) => unknown },
): UseFormReturn<z.input<S>, unknown, z.output<S>> & {
  rootError: string | undefined; submit: (e?: React.BaseSyntheticEvent) => void } {
  const form = useForm<z.input<S>, unknown, z.output<S>>({
    // zod 4 + resolvers 5 generic variance needs a cast here.
    resolver: zodResolver(schema as never) as never,
    defaultValues: opts.defaultValues,
  });
  const submit = form.handleSubmit(async (values) => {
    try {
      await opts.onSubmit(values);
    } catch (e) {
      if (e instanceof ApiError) {
        const rootMsgs: string[] = [];
        for (const [field, message] of Object.entries(e.fieldErrors)) {
          if (field !== "root" && isRegistered(form.control._fields, field)) {
            form.setError(field as Path<z.input<S>>, { type: "server", message });
          } else {
            rootMsgs.push(field === "root" ? message : `${field}: ${message}`);
          }
        }
        if (rootMsgs.length > 0 || Object.keys(e.fieldErrors).length === 0) {
          const msg = rootMsgs.join("; ") || e.message;
          form.setError("root.server", { type: "server", message: msg });
          toast.error(msg);
        }
        return;
      }
      toast.error(e instanceof Error ? e.message : "Something went wrong");
    }
  });
  return Object.assign(form, {
    rootError: form.formState.errors.root?.server?.message,
    submit: (e?: React.BaseSyntheticEvent) => {
      void submit(e);
    },
  });
}
