import { beforeEach, describe, expect, it, vi } from "vitest";

import { pendingTaskCount, queueTaskCompletion, syncTaskQueue } from "./task-offline";

describe("task offline queue", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("keeps each client operation once", () => {
    const operation = {
      kind: "complete-task" as const,
      operationId: "operation-123",
      taskId: "task-1",
      completedSubtaskIds: ["subtask-1"],
      photoIds: [],
    };
    queueTaskCompletion(operation);
    queueTaskCompletion(operation);
    expect(pendingTaskCount()).toBe(1);
  });

  it("removes a completion only after server confirmation", async () => {
    queueTaskCompletion({
      kind: "complete-task",
      operationId: "operation-456",
      taskId: "task-2",
      completedSubtaskIds: [],
      photoIds: [],
    });
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ id: "task-2" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    expect(await syncTaskQueue()).toBe(0);
    expect(pendingTaskCount()).toBe(0);
  });
});
