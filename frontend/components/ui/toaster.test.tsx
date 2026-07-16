import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { Toaster } from "@/components/ui/toaster";
import { useNotificationStore } from "@/store/notification.store";

const initial = { toasts: [] as ReturnType<typeof useNotificationStore.getState>["toasts"] };

describe("Toaster", () => {
  beforeEach(() => {
    useNotificationStore.setState(initial);
  });

  it("renders nothing when there are no toasts", () => {
    const { container } = render(<Toaster />);
    expect(container.querySelector('[role="status"]')).toBeNull();
  });

  it("renders a success toast with its title and message", () => {
    useNotificationStore.getState().success("Saved", "All good");
    render(<Toaster />);
    expect(screen.getByText("Saved")).toBeInTheDocument();
    expect(screen.getByText("All good")).toBeInTheDocument();
  });

  it("renders an error toast", () => {
    useNotificationStore.getState().error("Failed", "bad upload");
    render(<Toaster />);
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("bad upload")).toBeInTheDocument();
  });

  it("dismisses a toast via the close button", () => {
    useNotificationStore.getState().info("Dismiss me");
    render(<Toaster />);
    expect(screen.getByText("Dismiss me")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Dismiss notification"));
    expect(useNotificationStore.getState().toasts).toHaveLength(0);
  });
});
