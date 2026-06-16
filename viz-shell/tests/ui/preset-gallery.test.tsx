// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PRESETS, PresetGallery } from "@/components/explore/preset-gallery";

afterEach(cleanup); // unmount between tests so testids don't accumulate

describe("PresetGallery (vibeOS: chip = seed prompt, not a widget)", () => {
  it("renders one chip per preset", () => {
    render(<PresetGallery onPick={() => {}} />);
    for (const p of PRESETS) {
      expect(screen.getByTestId(`preset-${p.label}`)).toBeDefined();
    }
  });

  it("clicking a chip emits that preset's prompt", () => {
    const onPick = vi.fn();
    render(<PresetGallery onPick={onPick} />);
    fireEvent.click(screen.getByTestId(`preset-${PRESETS[0].label}`));
    expect(onPick).toHaveBeenCalledWith(PRESETS[0].prompt);
  });

  it("every preset prompt targets src/generated/ (boundary-respecting)", () => {
    for (const p of PRESETS) {
      expect(p.prompt).toContain("src/generated/");
      expect(p.prompt).toMatch(/trpc\.portfolio\./);
    }
  });
});
