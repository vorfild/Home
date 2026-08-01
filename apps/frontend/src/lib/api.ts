export type Role = "admin" | "adult" | "child";

export type Absence = {
  id: string;
  starts_on: string;
  ends_on: string;
  substitute_user_id: string | null;
  note: string | null;
};

export type User = {
  id: string;
  name: string;
  login: string;
  role: Role;
  color: string;
  avatar_path: string | null;
  must_change_password: boolean;
  is_active: boolean;
  active_absence: Absence | null;
};

export type AuthResponse = { user: User; csrf_token: string };
export type SetupStatus = { setup_required: boolean };
export type TabletStatus = { trusted: boolean; name: string | null };
export type UserCreated = { user: User; temporary_password: string };

let csrfToken = "";

function csrfFromCookie(): string {
  const item = document.cookie.split("; ").find((cookie) => cookie.startsWith("domovoy_csrf="));
  return item ? decodeURIComponent(item.split("=").slice(1).join("=")) : "";
}

export function rememberCsrf(token: string) {
  csrfToken = token;
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function errorMessage(payload: unknown): string {
  if (typeof payload === "object" && payload !== null && "detail" in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((item) =>
          typeof item === "object" && item !== null && "msg" in item
            ? String((item as { msg: unknown }).msg).replace(/^Value error, /, "")
            : String(item),
        )
        .join(". ");
    }
  }
  return "Не удалось выполнить запрос";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const token = csrfToken || csrfFromCookie();
    if (token) headers.set("X-CSRF-Token", token);
  }
  const response = await fetch(`/api/v1${path}`, { ...init, headers, credentials: "include" });
  const payload: unknown = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, errorMessage(payload));
  return payload as T;
}

export function jsonBody(value: unknown): Pick<RequestInit, "body"> {
  return { body: JSON.stringify(value) };
}
