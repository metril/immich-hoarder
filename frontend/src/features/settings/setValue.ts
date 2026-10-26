export const num = { setValueAs: (v: string) => (v === "" || v == null ? null : Number(v)) };
export const str = { setValueAs: (v: string | null) => (v == null || v.trim() === "" ? null : v.trim()) };
