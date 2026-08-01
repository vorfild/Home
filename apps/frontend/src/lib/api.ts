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

export type TaskItem = {
  id: string;
  definition_id: string;
  title: string;
  description: string | null;
  room: string | null;
  category: string;
  due_at: string | null;
  estimated_minutes: number | null;
  priority: "low" | "normal" | "high" | "urgent";
  assignment_mode: "fixed" | "anyone" | "multiple" | "queue";
  assignee_ids: string[];
  queue_user_ids: string[];
  current_queue_user_id: string | null;
  next_queue_user_id: string | null;
  subtasks: { id: string; title: string; completed: boolean }[];
  repeat: { kind: string; [key: string]: unknown };
  requires_photo: boolean;
  requires_adult_review: boolean;
  status: "open" | "awaiting_review" | "rejected" | "completed";
  completed_by_id: string | null;
  completed_at: string | null;
  review_comment: string | null;
  source_type: string | null;
};

export type ShoppingItem = {
  id: string;
  list_id: string;
  name: string;
  quantity: string;
  unit: string;
  category: string;
  note: string | null;
  added_by_id: string | null;
  recipient_id: string | null;
  purchased: boolean;
  photo_id: string | null;
  price: string | null;
  store: string | null;
  proposal_status: "pending" | "accepted" | "rejected";
  duplicate_warning: boolean;
};

export type ShoppingList = {
  id: string;
  title: string;
  store: string | null;
  scheduled_at: string | null;
  responsible_id: string | null;
  status: "no_date" | "planned" | "in_progress" | "completed";
  comment: string | null;
  completed_at: string | null;
  items: ShoppingItem[];
  total: string | null;
};

export type StorageNode = {
  id: string;
  parent_id: string | null;
  name: string;
  node_type: string;
  sort_order: number;
  path: { id: string; name: string }[];
  has_qr: boolean;
};

export type StorageItem = {
  id: string;
  node_id: string;
  name: string;
  photo_ids: string[];
  primary_photo_id: string | null;
  quantity: string | null;
  unit: string | null;
  category: string | null;
  owner_id: string | null;
  description: string | null;
  tags: string[];
  item_status: string;
  placed_at: string | null;
  location_since: string;
  last_used_at: string | null;
  value: string | null;
  purchased_on: string | null;
  manufacturer: string | null;
  model: string | null;
  serial_number: string | null;
  warranty_until: string | null;
  comment: string | null;
  review_at: string | null;
  review_status: "none" | "active" | "decision_required";
  path: { id: string; name: string }[];
};

export type StorageContents = {
  node: StorageNode | null;
  children: StorageNode[];
  items: StorageItem[];
};

export type StorageQr = { node_id: string; token: string; path: string };

export type Equipment = {
  id: string;
  storage_item_id: string | null;
  name: string;
  photo_ids: string[];
  category: string | null;
  location: string | null;
  manufacturer: string | null;
  model: string | null;
  serial_number: string | null;
  acquired_on: string | null;
  warranty_until: string | null;
  document_ids: string[];
  condition: string;
  responsible_id: string | null;
};

export type MaintenancePlan = {
  id: string;
  equipment_id: string | null;
  title: string;
  interval_days: number;
  previous_on: string | null;
  next_on: string;
  responsible_id: string | null;
  checklist: string[];
  materials: string[];
  estimated_cost: string | null;
  requires_photo: boolean;
  is_active: boolean;
  open_task_id: string | null;
};

export type RepairRecord = {
  id: string;
  equipment_id: string | null;
  plan_id: string | null;
  task_instance_id: string | null;
  record_type: "repair" | "maintenance";
  title: string;
  performed_on: string;
  comment: string | null;
  actual_cost: string | null;
  photo_ids: string[];
  attachment_ids: string[];
  keep_forever: boolean;
  purge_after: string | null;
};

export type Meter = {
  id: string;
  meter_type: string;
  unit: string;
  serial_number: string | null;
  location: string | null;
  last_value: string | null;
  next_submission_on: string | null;
  responsible_id: string | null;
  reset_sequence: number;
  is_active: boolean;
};

export type MeterReading = {
  id: string;
  meter_id: string;
  value: string;
  read_on: string;
  photo_id: string | null;
  comment: string | null;
  consumption: string | null;
  decrease_warning: boolean;
  reset_sequence: number;
};

export type HomeOverview = {
  meters_enabled: boolean;
  maintenance_due: MaintenancePlan[];
  warranties_expiring: Equipment[];
  meter_deadlines: Meter[];
  equipment_attention: Equipment[];
};

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
