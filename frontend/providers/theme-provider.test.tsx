import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { ThemeProvider, useTheme } from "@/providers/theme-provider";

function ThemeProbe() {
  const { theme, toggleTheme } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <button type="button" onClick={toggleTheme}>
        toggle
      </button>
    </div>
  );
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  document.documentElement.style.colorScheme = "";
});

describe("ThemeProvider", () => {
  it("applies light by default when nothing is persisted", async () => {
    await act(async () => {
      render(
        <ThemeProvider>
          <ThemeProbe />
        </ThemeProvider>,
      );
    });
    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });

  it("toggles to dark and persists the choice", async () => {
    await act(async () => {
      render(
        <ThemeProvider>
          <ThemeProbe />
        </ThemeProvider>,
      );
    });

    await act(async () => {
      fireEvent.click(screen.getByText("toggle"));
    });

    expect(screen.getByTestId("theme").textContent).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem("nexusagent.theme")).toBe("dark");
  });

  it("restores a persisted dark theme on mount", async () => {
    localStorage.setItem("nexusagent.theme", "dark");
    await act(async () => {
      render(
        <ThemeProvider>
          <ThemeProbe />
        </ThemeProvider>,
      );
    });
    expect(screen.getByTestId("theme").textContent).toBe("dark");
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });
});
