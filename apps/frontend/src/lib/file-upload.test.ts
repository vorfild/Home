import { beforeEach, describe, expect, it, vi } from "vitest";

import { rememberCsrf, uploadFile } from "./api";

describe("private file upload", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    rememberCsrf("csrf-test-token");
  });

  it("sends raw bytes with filename, mime and csrf", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          id: "file-1",
          entity_type: "task_instance",
          entity_id: "task-1",
          stored_mime: "image/webp",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    const file = new File([new Uint8Array([1, 2, 3])], "семья.png", { type: "image/png" });
    await uploadFile(file, "task_instance", "task-1", "photo", true);

    const [, options] = fetchMock.mock.calls[0];
    const headers = new Headers(options?.headers);
    expect(options?.body).toBe(file);
    expect(headers.get("Content-Type")).toBe("image/png");
    expect(headers.get("X-Filename")).toBe(encodeURIComponent("семья.png"));
    expect(headers.get("X-CSRF-Token")).toBe("csrf-test-token");
  });
});
