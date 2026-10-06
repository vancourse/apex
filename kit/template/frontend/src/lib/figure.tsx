import { CONCEPTS, type Concept } from "../gen/concepts";

// The ONLY place a number is formatted for display (eslint `local/figure-only`).
const MONEY = new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const COUNT = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export function formatFigure(concept: Concept, value: number): string {
  const unit: string = CONCEPTS[concept].unit;
  return unit === "cents" ? MONEY.format(value / 100) : COUNT.format(value);
}

/** A money amount or count. `concept` must be a row in concepts.toml -- anything else is a type error. */
export function Figure({ concept, value }: { concept: Concept; value: number }) {
  return (
    <span className="figure" data-concept={concept}>
      {formatFigure(concept, value)}
    </span>
  );
}
