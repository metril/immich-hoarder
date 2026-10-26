export class ApiError extends Error {
  status: number;
  detail: unknown;
  fieldErrors: Record<string, string>;

  constructor(status: number, message: string, detail: unknown, fieldErrors: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
  }
}

interface ValidationItem {
  loc?: unknown[];
  msg?: string;
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null;
}

function build(status: number, error: unknown, statusText: string): ApiError {
  const detail = isRecord(error) ? error.detail : undefined;
  let message = statusText || `HTTP ${status}`;
  const fieldErrors: Record<string, string> = {};
  if (typeof detail === "string") {
    if (detail) message = detail;
  } else if (Array.isArray(detail)) {
    for (const item of detail as ValidationItem[]) {
      if (!isRecord(item) || !Array.isArray(item.loc) || typeof item.msg !== "string") continue;
      fieldErrors[item.loc.slice(1).join(".") || "root"] = item.msg;
    }
    const first = Object.values(fieldErrors)[0];
    if (first) message = first;
  } else if (isRecord(detail) && typeof detail.msg === "string") {
    message = detail.msg;
  }
  return new ApiError(status, message, detail, fieldErrors);
}

/** Return `data`, or throw an ApiError built from the error body. */
export function unwrap<T>(r: { data?: T; error?: unknown; response: Response }): T {
  if (r.error !== undefined || r.data === undefined) {
    if (r.response.ok && r.error === undefined) return r.data as T; // e.g. 204
    throw build(r.response.status, r.error, r.response.statusText);
  }
  return r.data;
}
