// @vitest-environment jsdom
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ViewErrorBoundary } from "@/components/error-boundary";

function Bomb(): never {
  throw new Error("generated view exploded");
}

describe("ViewErrorBoundary (broken view isolated to its tab)", () => {
  it("renders children when nothing throws", () => {
    render(
      <ViewErrorBoundary viewTitle="Ok View">
        <div data-testid="alive">fine</div>
      </ViewErrorBoundary>,
    );
    expect(screen.getByTestId("alive")).toBeDefined();
  });

  it("catches a throwing child and shows the recovery fallback", () => {
    const silence = vi.spyOn(console, "error").mockImplementation(() => {});
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    render(
      <ViewErrorBoundary viewTitle="Broken View">
        <Bomb />
      </ViewErrorBoundary>,
    );
    const fallback = screen.getByTestId("view-error-fallback");
    expect(fallback.textContent).toContain("렌더 실패");
    expect(fallback.textContent).toContain("Broken View");
    expect(fallback.textContent).toContain("generated view exploded");
    expect(fallback.textContent).toContain("채팅으로 수정");
    silence.mockRestore();
    warn.mockRestore();
  });
});
