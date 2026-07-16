import { describe, it, expect, beforeEach } from "vitest";
import { useNotificationStore } from "@/store/notification.store";

const initial = { toasts: [] as ReturnType<typeof useNotificationStore.getState>["toasts"] };

describe("notification store (UI state)", () => {
  beforeEach(() => {
    useNotificationStore.setState(initial);
  });

  it("adds a toast via addToast and returns its id", () => {
    const id = useNotificationStore.getState().addToast({
      type: "info",
      title: "Heads up",
      message: "Something happened",
    });
    const { toasts } = useNotificationStore.getState();
    expect(toasts).toHaveLength(1);
    expect(toasts[0].id).toBe(id);
    expect(toasts[0].title).toBe("Heads up");
    expect(toasts[0].type).toBe("info");
  });

  it("convenience helpers push typed toasts", () => {
    useNotificationStore.getState().success("Saved");
    useNotificationStore.getState().error("Failed", "boom");
    const { toasts } = useNotificationStore.getState();
    expect(toasts.map((t) => t.type)).toEqual(["success", "error"]);
    expect(toasts[1].message).toBe("boom");
  });

  it("removes a toast by id", () => {
    const id = useNotificationStore.getState().info("one");
    useNotificationStore.getState().info("two");
    useNotificationStore.getState().removeToast(id);
    const { toasts } = useNotificationStore.getState();
    expect(toasts).toHaveLength(1);
    expect(toasts[0].title).toBe("two");
  });

  it("clears all toasts", () => {
    useNotificationStore.getState().success("a");
    useNotificationStore.getState().error("b");
    useNotificationStore.getState().clear();
    expect(useNotificationStore.getState().toasts).toHaveLength(0);
  });
});
