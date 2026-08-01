import { afterEach, expect, it, vi } from "vitest";

import { pendingShoppingCount, queueShopping, syncShoppingQueue } from "./shopping-offline";

afterEach(() => {
  localStorage.clear();
  vi.restoreAllMocks();
});

it("keeps an offline add operation until the server confirms it", async () => {
  queueShopping({
    kind: "add",
    id: "operation-0001",
    listId: "list-1",
    payload: { name: "Молоко" },
  });
  expect(pendingShoppingCount()).toBe(1);
  vi.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: true,
    status: 201,
    json: () => Promise.resolve({ id: "item-1" }),
  } as Response);

  expect(await syncShoppingQueue()).toBe(0);
  expect(pendingShoppingCount()).toBe(0);
  expect(globalThis.fetch).toHaveBeenCalledWith(
    "/api/v1/shopping/lists/list-1/items",
    expect.objectContaining({ method: "POST" }),
  );
});

it("retains an operation when synchronization fails", async () => {
  queueShopping({
    kind: "toggle",
    id: "operation-0002",
    itemId: "item-2",
    purchased: true,
  });
  vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("offline"));

  expect(await syncShoppingQueue()).toBe(1);
  expect(pendingShoppingCount()).toBe(1);
});
