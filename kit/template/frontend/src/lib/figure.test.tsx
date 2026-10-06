import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Figure, formatFigure } from "./figure";

describe("Figure", () => {
  it("formats cents as money", () => {
    expect(formatFigure("month_total", 123456)).toBe("1,234.56");
    expect(formatFigure("entry_amount", -50)).toBe("-0.50");
  });

  it("renders the concept it formats", () => {
    const { container } = render(<Figure concept="month_total" value={6024} />);
    expect(container.querySelector('[data-concept="month_total"]')?.textContent).toBe("60.24");
  });

  it("refuses an unregistered concept at compile time", () => {
    // @ts-expect-error -- "not_a_concept" is not a row in concepts.toml; typecheck fails if this compiles
    const element = <Figure concept="not_a_concept" value={1} />;
    expect(element).toBeTruthy();
  });
});
