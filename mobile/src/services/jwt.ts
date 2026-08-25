export function decodeJwtPayload(token: string): Record<string, unknown> {
  try {
    const part = token.split('.')[1];
    if (!part) return {};
    const normalized = part.replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(decodeURIComponent(escape(atob(normalized)))) as Record<string, unknown>;
  } catch {
    try {
      const part = token.split('.')[1] || '';
      return JSON.parse(atob(part)) as Record<string, unknown>;
    } catch {
      return {};
    }
  }
}
