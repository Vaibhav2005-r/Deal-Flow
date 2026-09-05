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
}

export function hasScope(scope: Scope): boolean {
  return tokenFor(scope) !== null;
}
