// @vitest-environment node
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { missingElements, render, scanControls } from "./gen-controls.mjs";

const read = (name) => JSON.parse(readFileSync(new URL(`../${name}`, import.meta.url), "utf8"));

describe("controls.json", () => {
  it("is current with the data-control attributes in src/screens", () => {
    const committed = readFileSync(new URL("../controls.json", import.meta.url), "utf8").replace(/\r\n/g, "\n");
    expect(committed).toBe(render(scanControls()));
  });

  it("contains every element of the screen of record (elements.json)", () => {
    expect(missingElements(scanControls(), read("elements.json"))).toEqual([]);
  });

  it("names an element the code does not render (planted)", () => {
    const planted = [...read("elements.json"), { screen: "summary", id: "summary.export_csv" }];
    expect(missingElements(scanControls(), planted)).toEqual([{ screen: "summary", id: "summary.export_csv" }]);
  });
});
