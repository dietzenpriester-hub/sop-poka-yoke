function base64UrlDecode(str: string): string {
  let base64 = str.replace(/-/g, "+").replace(/_/g, "/");
  while (base64.length % 4) base64 += "=";
  return atob(base64);
}

export function parseJwtPayload(token: string): Record<string, unknown> | null {
  try {
    return JSON.parse(base64UrlDecode(token.split(".")[1]));
  } catch {
    return null;
  }
}

export function isTokenExpired(token: string): boolean {
  const payload = parseJwtPayload(token);
  if (!payload || typeof payload.exp !== "number") return true;
  return Date.now() / 1000 > payload.exp;
}

export function getJwtRole(token: string): string | null {
  const payload = parseJwtPayload(token);
  if (!payload || typeof payload.role !== "string") return null;
  return payload.role;
}
