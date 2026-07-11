// Thin fetch wrapper. Attaches the bearer token and normalizes errors.

const TOKEN_KEY = "soc_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string) {
  localStorage.setItem(TOKEN_KEY, t);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function handle(res: Response) {
  if (res.status === 401) {
    clearToken();
    if (!location.pathname.startsWith("/login")) location.href = "/login";
    throw new ApiError("Session expired. Please sign in again.", 401);
  }
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(detail, res.status);
  }
  const ct = res.headers.get("content-type") || "";
  return ct.includes("application/json") ? res.json() : res.text();
}

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

export const api = {
  async get(path: string) {
    return handle(await fetch(path, { headers: { ...authHeaders() } }));
  },
  async post(path: string, body?: unknown) {
    return handle(
      await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
    );
  },
  async put(path: string, body?: unknown) {
    return handle(
      await fetch(path, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(body),
      })
    );
  },
  async patch(path: string, body?: unknown) {
    return handle(
      await fetch(path, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: body === undefined ? undefined : JSON.stringify(body),
      })
    );
  },
  async del(path: string) {
    return handle(await fetch(path, { method: "DELETE", headers: { ...authHeaders() } }));
  },
  async upload(path: string, form: FormData) {
    return handle(await fetch(path, { method: "POST", headers: { ...authHeaders() }, body: form }));
  },
  // Fetch a file with auth and trigger a browser download.
  async download(path: string, filename: string) {
    const res = await fetch(path, { headers: { ...authHeaders() } });
    if (!res.ok) return handle(res); // throws with a normalized message
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  async login(username: string, password: string) {
    const form = new URLSearchParams({ username, password });
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form,
    });
    const data = await handle(res);
    setToken(data.access_token);
    return data;
  },
};
