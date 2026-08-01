import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { App } from "./App";

describe("Domovoy application shell", () => {
  it("renders the primary family navigation", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: /Добрый вечер, Алексей/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Добавить дело" })).toBeInTheDocument();
    expect(screen.getAllByText("Кладовая").length).toBeGreaterThan(0);
  });

  it("adds a quick task to the visible list", () => {
    render(<App />);

    fireEvent.change(screen.getByPlaceholderText("Что нужно сделать?"), {
      target: { value: "Проверить почту" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Добавить быстрое дело" }));

    expect(screen.getByText("Проверить почту")).toBeInTheDocument();
  });
});
