import { describe, it, expect } from "vitest";
import { cn } from "@/lib/utils";

describe("cn (className merge)", () => {
  it("joins class names", () => {
    expect(cn("a", "b")).toBe("a b");
  });

  it("merges conflicting Tailwind classes (last wins)", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("ignores falsy values", () => {
    expect(cn("a", false, null, undefined, "b")).toBe("a b");
  });

  it("resolves conditional classes via clsx", () => {
    expect(cn("base", true && "on", false && "off")).toBe("base on");
  });
});
