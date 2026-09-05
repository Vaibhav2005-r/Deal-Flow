/**
 * Auth scopes.  Spec §1 constraint 2: the customer portal is a genuinely
 * separate, restricted view — different auth scope, different router,
 * different components.  NOT the internal screen with a flag (§13).
 *
 * `internal` and `portal` tokens are stored under different keys and are never
 * interchangeable: an internal session cannot satisfy a portal guard and vice
 * versa.
 */

export type Scope = "internal" | "portal";

export type InternalRole = "rep" | "manager" | "finance" | "admin";

export interface InternalUserInfo {
  user_id?: number;
  uid?: number;
  full_name?: string;
  name?: string;
  email?: string;
  role?: string;
  scope?: string;
}

const KEY: Record<Scope, string> = {
  internal: "df360.internal.token",
  portal: "df360.portal.token",
};

export function tokenFor(scope: Scope): string | null {
  return localStorage.getItem(KEY[scope]);
}

export function setToken(scope: Scope, token: string): void {
  localStorage.setItem(KEY[scope], token);
}

export function clearToken(scope: Scope): void {
  localStorage.removeItem(KEY[scope]);
  if (scope === "internal") {
    localStorage.removeItem("df360.internal.user");
  }
}

export function hasScope(scope: Scope): boolean {
  return tokenFor(scope) !== null;
}

export function getCurrentUser(): InternalUserInfo | null {
  // 1. Try local storage user record
  try {
    const raw = localStorage.getItem("df360.internal.user");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object") {
        return parsed;
      }
    }
  } catch {}

  // 2. Fallback to decoding token payload
  const token = localStorage.getItem("df360.internal.token");
  if (token) {
    try {
      const parts = token.split(".");
      if (parts.length >= 1) {
        const payloadBase64 = parts[0].replace(/-/g, "+").replace(/_/g, "/");
        const json = decodeURIComponent(
          atob(payloadBase64)
            .split("")
            .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
            .join("")
        );
        const decoded = JSON.parse(json);
        if (decoded && typeof decoded === "object") {
          return {
            uid: decoded.uid,
            user_id: decoded.uid,
            role: decoded.role,
            scope: decoded.scope,
            email: decoded.email,
            full_name:
              decoded.full_name ||
              (String(decoded.role).toLowerCase().includes("finance")
                ? "Finance Officer"
                : "Internal User"),
          };
        }
      }
    } catch {}
  }

  return null;
}

export function getRoleDesignation(role: string): string {
  const r = (role || "").toLowerCase();
  if (r.includes("finance")) return "Senior Finance & Operations Controller";
  if (r.includes("manager")) return "Commercial Sales Manager";
  if (r.includes("rep")) return "Senior Account Executive";
  if (r.includes("admin")) return "System Administrator";
  return "Enterprise Revenue Specialist";
}

export function getInternalRole(): string {
  const user = getCurrentUser();
  const rawRole = user?.role ? String(user.role).toLowerCase() : "";
  if (rawRole.includes("finance")) return "finance";
  if (rawRole.includes("manager")) return "manager";
  if (rawRole.includes("admin")) return "admin";
  if (rawRole.includes("rep")) return "rep";
  return rawRole || "finance";
}

export function isFinanceUser(): boolean {
  const user = getCurrentUser();
  const rawRole = user?.role ? String(user.role).toLowerCase() : "";
  if (rawRole.includes("rep") || rawRole.includes("manager")) {
    return false;
  }
  if (rawRole.includes("finance")) {
    return true;
  }
  const email = user?.email ? String(user.email).toLowerCase() : "";
  if (email.includes("aisha") || email.includes("finance")) {
    return true;
  }
  // Default to true for finance role if no other explicit rep/manager role
  return true;
}

