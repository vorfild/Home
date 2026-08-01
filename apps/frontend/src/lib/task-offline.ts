import { api, jsonBody, TaskItem } from "./api";

const QUEUE_KEY = "domovoy.tasks.queue";
const TODAY_KEY = "domovoy.today.cache";

export type TaskCompletionOperation = {
  kind: "complete-task";
  operationId: string;
  taskId: string;
  completedSubtaskIds: string[];
};

type TodayCache = {
  userId: string;
  scope: "mine" | "all";
  savedAt: string;
  tasks: TaskItem[];
};

function operations(): TaskCompletionOperation[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(QUEUE_KEY) ?? "[]");
    return Array.isArray(value)
      ? value.filter(
          (item): item is TaskCompletionOperation =>
            typeof item === "object" &&
            item !== null &&
            (item as TaskCompletionOperation).kind === "complete-task",
        )
      : [];
  } catch {
    return [];
  }
}

export function newOperationId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `offline-${Date.now()}-${Math.random()}`;
}

export function queueTaskCompletion(operation: TaskCompletionOperation) {
  if (operations().some((item) => item.operationId === operation.operationId)) return;
  localStorage.setItem(QUEUE_KEY, JSON.stringify([...operations(), operation]));
}

export function pendingTaskCount(): number {
  return operations().length;
}

export async function completeTaskOperation(
  task: Pick<TaskItem, "id" | "subtasks">,
  operationId = newOperationId(),
): Promise<TaskItem> {
  return api<TaskItem>(`/tasks/${task.id}/complete`, {
    method: "POST",
    ...jsonBody({
      client_operation_id: operationId,
      completed_subtask_ids: task.subtasks.map((item) => item.id),
    }),
  });
}

export async function syncTaskQueue(): Promise<number> {
  const remaining: TaskCompletionOperation[] = [];
  for (const operation of operations()) {
    try {
      await api<TaskItem>(`/tasks/${operation.taskId}/complete`, {
        method: "POST",
        ...jsonBody({
          client_operation_id: operation.operationId,
          completed_subtask_ids: operation.completedSubtaskIds,
        }),
      });
    } catch {
      remaining.push(operation);
    }
  }
  localStorage.setItem(QUEUE_KEY, JSON.stringify(remaining));
  return remaining.length;
}

export function cacheToday(userId: string, scope: "mine" | "all", tasks: TaskItem[]) {
  const value: TodayCache = { userId, scope, tasks, savedAt: new Date().toISOString() };
  localStorage.setItem(TODAY_KEY, JSON.stringify(value));
}

export function cachedToday(userId: string, scope: "mine" | "all"): TaskItem[] | null {
  try {
    const value = JSON.parse(localStorage.getItem(TODAY_KEY) ?? "null") as TodayCache | null;
    return value?.userId === userId && value.scope === scope ? value.tasks : null;
  } catch {
    return null;
  }
}
