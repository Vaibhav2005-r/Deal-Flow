/** Thin fetch wrapper. The typed client is generated from OpenAPI (§11). */

import { type Scope, tokenFor } from "./auth";

const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

export async function apiFetch<T>(
  path: string,
  scope: Scope,
  init: RequestInit = {},
): Promise<T> {
  const token = tokenFor(scope);
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json() as Promise<T>;
}
