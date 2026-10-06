const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

const sessionExpiredListeners = new Set<() => void>();
let refreshPromise: Promise<void> | null = null;

export function onSessionExpired(listener: () => void): () => void {
  sessionExpiredListeners.add(listener);
  return () => { sessionExpiredListeners.delete(listener); };
}

function expireSession() {
  sessionExpiredListeners.forEach((listener) => listener());
}

function refreshSession(): Promise<void> {
  // Concurrent API requests must share one cookie refresh.
  refreshPromise ??= request<void>("/api/auth/refresh", { method: "POST" }, false)
    .finally(() => { refreshPromise = null; });
  return refreshPromise;
}

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, message: string, body?: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function errorMessage(body: unknown, status: number): string {
  const fallback = `Request failed with status ${status}`;
  if (typeof body !== "object" || body === null || !("detail" in body)) return fallback;
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  const items = Array.isArray(detail) ? detail : [detail];
  const messages = items.flatMap((item: unknown) => {
    if (typeof item === "string") return [item];
    if (typeof item !== "object" || item === null || !("msg" in item)) return [];
    const error = item as { msg: unknown; loc?: unknown };
    if (typeof error.msg !== "string") return [];
    const field = Array.isArray(error.loc)
      ? error.loc.filter((part) => typeof part === "string" && part !== "body").join(".")
      : "";
    return [field ? `${field}: ${error.msg}` : error.msg];
  });
  return messages.join("; ") || fallback;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  allowRefresh = true,
): Promise<T> {
  const isFormData = typeof FormData !== "undefined" && options.body instanceof FormData;
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      ...(!isFormData ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });

  const protectedRequest = !path.startsWith("/api/auth/") || path === "/api/auth/me";
  if (res.status === 401 && protectedRequest) {
    if (allowRefresh) {
      try {
        await refreshSession();
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) expireSession();
        throw err;
      }
      return request<T>(path, options, false);
    }
    expireSession();
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const contentType = res.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json")
    ? await res.json()
    : await res.text();

  if (!res.ok) {
    const message = errorMessage(body, res.status);
    throw new ApiError(res.status, message, body);
  }

  return body as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: data !== undefined ? JSON.stringify(data) : undefined,
    }),
  upload: <T>(path: string, data: FormData) =>
    request<T>(path, { method: "POST", body: data }),
  patch: <T>(path: string, data?: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: data !== undefined ? JSON.stringify(data) : undefined,
    }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
};
