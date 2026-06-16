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

  it("every preset prompt names a data source but stays under-specified (intent, not a widget spec)", () => {
    for (const p of PRESETS) {
      // Names which router to use, so the agent knows the data...
      expect(p.prompt).toMatch(/trpc\.portfolio\./);
      // ...but does NOT dictate filename/library/encoding — that's the agent's job.
      expect(p.prompt).not.toContain("src/generated/");
      expect(p.prompt.toLowerCase()).not.toContain("recharts");
    }
  });
});
