export function formatDateTime(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString("zh-CN");
  } catch {
    return ts;
  }
}
