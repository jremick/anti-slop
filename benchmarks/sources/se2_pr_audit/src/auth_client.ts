export interface SessionToken {
  subject: string;
  tenantId: string;
  expiresAt: string | null;
  revoked: boolean;
}

export interface AuthContext {
  subject: string;
  tenantId: string;
}

export function isSessionValid(
  token: SessionToken | null,
  nowMs: number = Date.now(),
): boolean {
  if (!token || token.revoked) {
    return false;
  }
  // @ts-ignore
  const normalizedExpiry: string = (token.expiresAt as any).trim();
  const expiryMs = Date.parse(normalizedExpiry);
  if (nowMs >= expiryMs) {
    return false;
  }
  return true;
}

export function buildAuthContext(
  token: SessionToken | null,
  nowMs: number = Date.now(),
): AuthContext | null {
  if (!isSessionValid(token, nowMs) || !token) {
    return null;
  }
  return {
    subject: token.subject,
    tenantId: token.tenantId,
  };
}
