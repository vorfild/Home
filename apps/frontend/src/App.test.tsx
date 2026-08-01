import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

const user = {
  id: "user-1",
  name: "Алексей",
  login: "alexey",
  role: "admin",
  color: "#5E7FA3",
  avatar_path: null,
  must_change_password: false,
  is_active: true,
  active_absence: null,
};

function response(status: number, body: unknown) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as Response);
}

afterEach(() => vi.restoreAllMocks());

describe("Domovoy identity flow", () => {
  it("opens the first-run wizard on a clean installation", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(() => response(200, { setup_required: true }));

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Настроим ваш дом" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Язык и время" })).toBeInTheDocument();
  });

  it("shows the protected family screen for an authenticated user", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const path = String(input);
      if (path.endsWith("/setup/status")) return response(200, { setup_required: false });
      if (path.endsWith("/tablet/status")) return response(200, { trusted: false, name: null });
      if (path.endsWith("/auth/me")) return response(200, { user, csrf_token: "csrf" });
      if (path.endsWith("/family/members")) return response(200, [user]);
      if (path.includes("/tasks/today")) return response(200, []);
      if (path.endsWith("/shopping/today")) return response(200, []);
      if (path.endsWith("/tasks"))
        return response(201, {
          id: "task-1",
          definition_id: "definition-1",
          title: "Проверить почту",
          description: null,
          room: null,
          category: "другое",
          due_at: new Date().toISOString(),
          estimated_minutes: null,
          priority: "normal",
          assignment_mode: "fixed",
          assignee_ids: [user.id],
          queue_user_ids: [],
          current_queue_user_id: user.id,
          next_queue_user_id: null,
          subtasks: [],
          repeat: { kind: "none" },
          requires_photo: false,
          requires_adult_review: false,
          status: "open",
          completed_by_id: null,
          completed_at: null,
          review_comment: null,
        });
      return response(404, { detail: "not found" });
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Семья" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Алексей" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Добавить человека" })).toBeInTheDocument();
  });

  it("shows login when setup is complete and no session exists", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const path = String(input);
      if (path.endsWith("/setup/status")) return response(200, { setup_required: false });
      if (path.endsWith("/tablet/status")) return response(200, { trusted: false, name: null });
      if (path.endsWith("/auth/me")) return response(401, { detail: "Требуется вход" });
      return response(404, { detail: "not found" });
    });

    render(<App />);

    expect(await screen.findByRole("heading", { name: "С возвращением" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Войти" })).toBeInTheDocument();
  });

  it("keeps the stage-one Today shell available behind authentication", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation((input) => {
      const path = String(input);
      if (path.endsWith("/setup/status")) return response(200, { setup_required: false });
      if (path.endsWith("/tablet/status")) return response(200, { trusted: false, name: null });
      if (path.endsWith("/auth/me")) return response(200, { user, csrf_token: "csrf" });
      if (path.endsWith("/family/members")) return response(200, [user]);
      if (path.includes("/tasks/today")) return response(200, []);
      if (path.endsWith("/shopping/today")) return response(200, []);
      if (path.endsWith("/tasks"))
        return response(201, {
          id: "task-1",
          definition_id: "definition-1",
          title: "Проверить почту",
          description: null,
          room: null,
          category: "другое",
          due_at: new Date().toISOString(),
          estimated_minutes: null,
          priority: "normal",
          assignment_mode: "fixed",
          assignee_ids: [user.id],
          queue_user_ids: [],
          current_queue_user_id: user.id,
          next_queue_user_id: null,
          subtasks: [],
          repeat: { kind: "none" },
          requires_photo: false,
          requires_adult_review: false,
          status: "open",
          completed_by_id: null,
          completed_at: null,
          review_comment: null,
        });
      return response(404, { detail: "not found" });
    });
    render(<App />);
    await screen.findByRole("heading", { name: "Семья" });

    fireEvent.click(screen.getAllByRole("button", { name: "Сегодня" })[0]);
    await waitFor(() =>
      expect(screen.getByPlaceholderText("Что нужно сделать?")).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByPlaceholderText("Что нужно сделать?"), {
      target: { value: "Проверить почту" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Добавить быстрое дело" }));

    expect(await screen.findByText("Проверить почту")).toBeInTheDocument();
  });
});
