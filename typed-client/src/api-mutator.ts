// Custom fetch mutator used by every generated hook (see orval.config.js's
// override.mutator). Centralizes base URL + auth header handling in one
// place instead of duplicating it per generated call.
export type ApiFetchOptions = {
  url: string;
  method: string;
  params?: unknown;
  data?: unknown;
  headers?: HeadersInit;
  signal?: AbortSignal;
};

const BASE_URL =
  (typeof process !== 'undefined' && process.env.NEXT_PUBLIC_API_BASE_URL) ||
  'http://localhost:8000';

// Placeholder - the real Next.js app will replace this with whatever reads
// the signed-in user's Supabase access token (session/cookie helper).
// Kept here so generated hooks type-check standalone during this
// codegen/scoping phase, before the frontend project exists.
function getAccessToken(): string | null {
  return null;
}

export async function apiFetch<T>({
  url,
  method,
  params,
  data,
  headers,
  signal,
}: ApiFetchOptions): Promise<T> {
  const query = params
    ? '?' + new URLSearchParams(params as Record<string, string>).toString()
    : '';
  const token = getAccessToken();

  const res = await fetch(`${BASE_URL}${url}${query}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    body: data !== undefined ? JSON.stringify(data) : undefined,
    signal,
  });

  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`API ${method} ${url} failed: ${res.status} ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
