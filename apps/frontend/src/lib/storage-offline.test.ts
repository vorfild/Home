import { afterEach, expect, it } from "vitest";

import { StorageContents } from "./api";
import { cachedStorageSection, cacheStorageSection } from "./storage-offline";

afterEach(() => localStorage.clear());

it("keeps recently opened storage contents for offline read-only access", () => {
  const contents: StorageContents = {
    node: {
      id: "box-1",
      parent_id: null,
      name: "Коробка",
      node_type: "коробка",
      sort_order: 0,
      path: [{ id: "box-1", name: "Коробка" }],
      has_qr: true,
    },
    children: [],
    items: [],
  };

  cacheStorageSection("box-1", contents);

  expect(cachedStorageSection("box-1")?.node?.name).toBe("Коробка");
  expect(cachedStorageSection("unknown")).toBeNull();
});
