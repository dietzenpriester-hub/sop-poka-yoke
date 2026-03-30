export function severityTagType(
  severity: string
): "" | "success" | "warning" | "danger" | "info" {
  const s = severity?.toUpperCase() ?? "";
  if (s === "CRITICAL" || s === "ERROR") return "danger";
  if (s === "WARN") return "warning";
  if (s === "INFO") return "info";
  return "";
}
