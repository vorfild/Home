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

export type CalendarEvent = {
  id: string;
  source_type: "task" | "shopping" | "maintenance" | "meter" | "warranty" | "storage";
  source_id: string;
  title: string;
  starts_at: string;
  status: string;
  user_ids: string[];
  scope: "personal" | "shared";
  editable: boolean;
  recurring: boolean;
};

export type UserPreference = {
  user_id: string;
  channels: { in_app: boolean; push: boolean; email: boolean };
  event_rules: Record<string, boolean>;
  reminder_minutes: number;
  repeat_minutes: number | null;
  quiet_start: string | null;
  quiet_end: string | null;
  email: string | null;
  theme: "system" | "light" | "dark";
  font_scale: "small" | "normal" | "large";
  density: "compact" | "comfortable";
};

export type ModuleSettings = {
  meters: boolean;
  email: boolean;
  shopping_prices: boolean;
  maintenance_finances: boolean;
  task_photos: boolean;
};

export type ServerSettings = {
  timezone: string;
  domain: string | null;
  https_enabled: boolean;
  files_dir: string;
  app_version: string;
  web_push_configured: boolean;
  smtp_configured: boolean;
};

export type AppNotification = {
  id: string;
  event_type: string;
  title: string;
  body: string;
  source_type: string | null;
  source_id: string | null;
  read_at: string | null;
  created_at: string;
};

export type FamilyStats = {
  user_id: string;
  today_tasks: number;
  overdue_tasks: number;
  queue_tasks: number;
  awaiting_review: number;
  pending_requests: number;
};

export type SyncConflict = {
  id: string;
  entity_type: string;
  entity_id: string;
  field_name: string;
  base_version: number;
  server_version: number;
  server_value: unknown;
  alternative_value: unknown;
  proposed_by_id: string;
  status: string;
  created_at: string;
};

export type EntityConflictStatus = {
  entity_type: string;
  entity_id: string;
  count: number;
  latest_changed_at: string;
  latest_actor_id: string;
};

export type SyncEvent = {
  sequence: number;
  entity_type: string;
  entity_id: string;
  action: string;
  changed_fields: string[];
  actor_id: string | null;
  version: number | null;
  created_at: string;
};

export type FileAsset = {
  id: string;
  entity_type: string;
  entity_id: string;
  purpose: string;
  original_name: string;
  original_mime: string;
  stored_mime: string;
  size_bytes: number;
  width: number | null;
  height: number | null;
  is_primary: boolean;
  created_at: string;
};

export type BackupArchive = {
  id: string;
  kind: "monthly" | "manual" | "insurance";
  checksum: string;
  size_bytes: number;
  app_version: string;
  schema_version: string;
  status: string;
  manifest: Record<string, unknown>;
  verified_at: string;
  created_at: string;
};

export type DataStatus = {
  monthly: BackupArchive | null;
  manual: BackupArchive[];
  insurance: BackupArchive[];
  files_bytes: number;
  backups_bytes: number;
  app_version: string;
  schema_version: string;
};

export type RestoreReport = {
  id: string;
  status: string;
  source_name: string;
  source_checksum: string;
  counts_before: Record<string, number>;
  counts_after: Record<string, number>;
  warnings: string[];
  details: string | null;
  created_at: string;
  completed_at: string | null;
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
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");
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

export function uploadFile(
  file: File,
  entityType: string,
  entityId: string,
  purpose: "photo" | "document" | "attachment" | "avatar" = "attachment",
  primary = false,
): Promise<FileAsset> {
  const query = new URLSearchParams({
    entity_type: entityType,
    entity_id: entityId,
    purpose,
    primary: String(primary),
  });
  return api<FileAsset>(`/files?${query}`, {
    method: "POST",
    headers: {
      "Content-Type": file.type || "application/octet-stream",
      "X-Filename": encodeURIComponent(file.name),
    },
    body: file,
  });
}
