import { useForm, type DefaultValues, type FieldValues, type Path, type UseFormReturn } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";
import type { z } from "zod";
import { ApiError } from "../../api/errors";

/**
 * react-hook-form + zod. Server 422s map onto fields by dotted name
 * (empty loc -> "root"); other errors toast. The form is never reset on failure.
 */
export function useApiForm<S extends z.ZodType<FieldValues, FieldValues>>(
  schema: S,
  opts: { defaultValues: DefaultValues<z.input<S>>; onSubmit: (v: z.output<S>) => unknown },
): UseFormReturn<z.input<S>, unknown, z.output<S>> & { submit: (e?: React.BaseSyntheticEvent) => void } {
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
        const entries = Object.entries(e.fieldErrors);
        if (entries.length > 0) {
          for (const [field, message] of entries) {
            form.setError(field as Path<z.input<S>>, { type: "server", message });
          }
          return;
        }
        toast.error(e.message);
        return;
      }
      toast.error(e instanceof Error ? e.message : "Something went wrong");
    }
  });
  return Object.assign(form, {
    submit: (e?: React.BaseSyntheticEvent) => {
      void submit(e);
    },
  });
}
