import { api, jsonBody, ShoppingItem, ShoppingList } from "./api";

const CACHE_KEY = "domovoy.shopping.cache";
const QUEUE_KEY = "domovoy.shopping.queue";

type AddOperation = {
  kind: "add";
  id: string;
  listId: string;
  payload: Record<string, unknown>;
};

type ToggleOperation = {
  kind: "toggle";
  id: string;
  itemId: string;
  purchased: boolean;
};

export type ShoppingOperation = AddOperation | ToggleOperation;

export function cachedShopping(): ShoppingList[] {
  try {
    return JSON.parse(localStorage.getItem(CACHE_KEY) ?? "[]") as ShoppingList[];
  } catch {
    return [];
  }
}

export function cacheShopping(lists: ShoppingList[]) {
  localStorage.setItem(CACHE_KEY, JSON.stringify(lists));
}

function operations(): ShoppingOperation[] {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) ?? "[]") as ShoppingOperation[];
  } catch {
    return [];
  }
}

export function pendingShoppingCount(): number {
  return operations().length;
}

export function queueShopping(operation: ShoppingOperation) {
  localStorage.setItem(QUEUE_KEY, JSON.stringify([...operations(), operation]));
}

export async function syncShoppingQueue(): Promise<number> {
  const pending = operations();
  const remaining: ShoppingOperation[] = [];
  for (const operation of pending) {
    try {
      if (operation.kind === "add") {
        await api<ShoppingItem>(`/shopping/lists/${operation.listId}/items`, {
          method: "POST",
          ...jsonBody({ ...operation.payload, client_operation_id: operation.id }),
        });
      } else {
        await api<ShoppingItem>(`/shopping/items/${operation.itemId}`, {
          method: "PATCH",
          ...jsonBody({ purchased: operation.purchased }),
        });
      }
    } catch {
      remaining.push(operation);
    }
  }
  localStorage.setItem(QUEUE_KEY, JSON.stringify(remaining));
  return remaining.length;
}
